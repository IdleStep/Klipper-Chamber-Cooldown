"""Shared setup for the cooldown behavior tests in the Hardware Controls simulator.

The tests are in the other test_*.py files, one topic each. Run them all with:
    python -m unittest discover -s tests -v
Needs Klipper-Hardware-Controls checked out beside this repository (its tests/klipper_sim.py is
the simulator) and Jinja2 3.1.6. HARDWARE_CONTROLS_PATH says where that checkout is. It is not
HARDWARE_CONTROLS_ROOT, which klipper_sim reads to load the package configs from another checkout.
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HARDWARE_CONTROLS = pathlib.Path(
    os.environ.get('HARDWARE_CONTROLS_PATH') or ROOT.parent / 'Klipper-Hardware-Controls').resolve()
if not (HARDWARE_CONTROLS / 'tests' / 'klipper_sim.py').is_file():
    raise RuntimeError('Klipper-Hardware-Controls not found at %s. Clone it beside this '
                       'repository or set HARDWARE_CONTROLS_PATH (see CONTRIBUTING.md).'
                       % HARDWARE_CONTROLS)
# Appended, not prepended: Hardware Controls has test modules with the same names.
sys.path.append(str(HARDWARE_CONTROLS / 'tests'))

import klipper_sim  # noqa: E402
from klipper_sim import State, wrap  # noqa: E402,F401

COOLDOWN_MODULES = ['profiles', 'materials', 'engine']
# The Hardware Controls modules cooldown needs; cooldown.cfg's header lists the same three.
REQUIRED_HARDWARE_MODULES = ['hardware_names', 'fans', 'chamber']
HARDWARE_VARS = 'gcode_macro _HARDWARE_VARS'
VARS = 'gcode_macro _COOLDOWN_VARS'
SETTINGS = 'gcode_macro _COOLDOWN_SETTINGS'
PROFILES = 'gcode_macro _COOLDOWN_PROFILES'
MATERIALS = 'gcode_macro _COOLDOWN_MATERIALS'
CHAMBER = 'heater_generic chamber'
BED = 'heater_bed'
EXHAUST_FAN = 'fan_generic exhaust_fan'
EXTERNAL_PC = 'fan_generic external_pc'
BED_FANS = 'fan_generic bed_fans'
PART_FAN = 'fan'


class Printer(klipper_sim.Printer):
    """Simulated printer with Hardware Controls and, optionally, cooldown loaded."""

    def __init__(self, hardware=True, cooldown=True, tracking=False):
        # Only the modules cooldown needs, so a release that lacks a newer one (hardware_check
        # came in 3.3.0) can still be tested.
        super().__init__(hardware=False)
        if hardware:
            for name in REQUIRED_HARDWARE_MODULES:
                self.load(klipper_sim.module_path(name))
            self.load(klipper_sim.HARDWARE_NAMES)
        # Hardware Controls 2.0.0's PART_COOLING reads the part fan's section of the configuration.
        self.state['configfile'].settings.setdefault('fan', State())
        if cooldown:
            for name in COOLDOWN_MODULES:
                self.load(ROOT / (name + '.cfg'))
        if tracking:
            self.load(ROOT / 'idle_timeout_tracking.cfg')

    def execute(self, line):
        # idle_timeout_tracking.cfg renames the built-in command to this one.
        if line.split()[0].upper() == 'SET_IDLE_TIMEOUT_BASE':
            self.commands.append(line)
            args = dict(token.split('=', 1) for token in line.split()[1:] if '=' in token)
            try:
                seconds = float(args['TIMEOUT'])
            except (KeyError, ValueError):
                return  # Klipper would report the bad or missing value
            if seconds > 0:
                self.idle_timeout = seconds
            return
        super().execute(line)


def hardware_takes_several_devices():
    """Whether the Hardware Controls under test splits a comma-separated role (3.4.0 and later).
    Older releases read it as one name that matches nothing."""
    printer = Printer(cooldown=False)
    printer.state['fan_generic vent'] = wrap({'speed': 0.})
    printer.state[HARDWARE_VARS].exhaust_fan = 'exhaust_fan, vent'
    printer.run('EXHAUST_FAN', SPEED=0.5)
    return printer.state['fan_generic vent'].speed == 0.5


# Marks the tests of roles that name several devices. CI runs the suite against Hardware
# Controls 2.0.0 too, and against its main before a release that adds the feature is merged.
needs_several_devices = unittest.skipUnless(
    hardware_takes_several_devices(), 'needs Hardware Controls 3.4.0 or later')


class CooldownTestCase(unittest.TestCase):
    """Helpers shared by the test classes below."""

    def run_until(self, printer, phase, limit=2400):
        trace = []
        for _ in range(limit):
            printer.run('_COOLDOWN_LOOP')
            cv = printer.state[VARS]
            trace.append((cv.phase, cv.phase_loops,
                          printer.state[CHAMBER].target if CHAMBER in printer.state else 0))
            if cv.phase in (0, phase):
                break
        return trace

    def custom_profile(self, printer, **changes):
        table = printer.state[PROFILES].profiles
        profile = dict(table['HOLD_60M_COOL_EX'], **changes)
        for key in [key for key, value in changes.items() if value is Ellipsis]:
            del profile[key]  # Ellipsis removes the key
        table['CUSTOM'] = wrap(profile)

    def responses(self, printer):
        return [command for command in printer.commands if command.startswith('RESPOND')]

    def responses_containing(self, printer, text):
        return [response for response in self.responses(printer) if text in response]

    def responded(self, printer, text):
        return bool(self.responses_containing(printer, text))

    def commands_containing(self, printer, text, start=0):
        return [command for command in printer.commands[start:] if text in command]

    def sent(self, printer, prefix, start=0):
        return any(command.startswith(prefix) for command in printer.commands[start:])

    def banner_numbers(self, printer):
        return [command.split('MSG="Cooldown phase ')[1][:3]
                for command in printer.commands
                if 'Cooldown phase' in command]

    def sensor_printer(self, **reading):
        """A printer whose chamber has only a temperature sensor."""
        printer = Printer()
        printer.state.pop(CHAMBER)
        printer.state['temperature_sensor enclosure'] = wrap(reading)
        printer.state[HARDWARE_VARS].chamber_heater = ''
        printer.state[HARDWARE_VARS].chamber_sensor = 'temperature_sensor enclosure'
        return printer

    def fan_minimum_printer(self, speed, **minimums):
        """Immediate-exhaust profile at `speed`.

        `minimums` maps a fan name to its fan_generic settings.
        """
        printer = Printer()
        printer.state[BED_FANS] = wrap({'speed': 0.})
        for name, fan_settings in minimums.items():
            printer.state['configfile'].settings['fan_generic ' + name] = wrap(fan_settings)
        self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                            cooldown_ramp_step_c=0, cooldown_ramp_step_seconds=0,
                            exhaust_fan_speed=speed)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.run_until(printer, 5)
        return printer
