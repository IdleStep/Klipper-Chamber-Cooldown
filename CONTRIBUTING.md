# Contributing

Thank you for helping. Small, focused changes are easiest to review.

## Before you open a pull request

The tests use the shared harness from Klipper-Hardware-Controls. Check it out as
`hardware-controls` beside this README, then:

```sh
git clone https://github.com/IdleStep/Klipper-Hardware-Controls hardware-controls
pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

The tests:

- The simulator tests are split by topic: `tests/test_hardware_roles.py`, `test_profiles.py`,
  `test_materials.py`, `test_start.py`, `test_status_and_report.py`, `test_reset.py`,
  `test_phases.py`, `test_stops.py` and `test_idle_timeout_tracking.py`. Run one with
  `python -m unittest discover -s tests -p test_phases.py`. `tests/test_templates.py` holds what
  they share: the simulated printer and its helpers.
- `tests/test_config_lint.py` checks the config files.
- `tests/test_klippy.py` runs `tests/klippy/*.gcode` in real Klipper and Kalico without
  hardware. It is skipped unless `KLIPPER_DIR`, `KLIPPY_DICT` and `KLIPPY_PYTHON` are set;
  the CI workflow shows how to build them.

CI also runs the suite against Hardware Controls 2.0.0. None of this replaces a real thermal
run on a printer.

Before you open the pull request:

- Follow [Hardware Controls' docs/STYLE.md](https://github.com/IdleStep/Klipper-Hardware-Controls/blob/main/docs/STYLE.md).
- A changed message changes its test and, if it is in
  [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), its line there in the same commit.
- Add an entry to the CHANGELOG under "Unreleased".
- Safety first: when the cooldown cannot continue it says so and leaves the heaters and
  fans as the user set them, or turns the heaters off when it cannot know the
  temperatures. Anything else needs a reason in the pull request.

## Versions

The version follows the cooldown API, as the CHANGELOG explains. Releases are annotated
tags named `vMAJOR.MINOR.PATCH`; Moonraker's `channel: stable` follows them.
