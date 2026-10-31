; The chamber heater role lists a name that matches nothing before the real heater: the cooldown
; skips it and turns the real heater off.
CHAMBER TEMP=55
SET_GCODE_VARIABLE MACRO=_COOLDOWN_SETTINGS VARIABLE=chamber_cooled_temp VALUE=-50
START_COOLDOWN PROFILE=IMMEDIATE_EX
ASSERT_VAR MACRO=_COOLDOWN_VARS VARIABLE=phase VALUE=1
TEST_COOLDOWN_TICK
TEST_COOLDOWN_TICK
ASSERT_VAR MACRO=_COOLDOWN_VARS VARIABLE=phase VALUE=3
ASSERT_HEATER HEATER=heater_generic:chamber TARGET=0
; The exhaust role lists two fans and a name that matches nothing. Both fans get the speed, and
; bed_fans, which the test printer's other roles leave off here, is untouched.
TEST_COOLDOWN_TICK
TEST_COOLDOWN_TICK
ASSERT_VAR MACRO=_COOLDOWN_VARS VARIABLE=phase VALUE=5
ASSERT_FAN FAN=exhaust_fan SPEED=1
ASSERT_FAN FAN=external_pc SPEED=1
ASSERT_FAN FAN=bed_fans SPEED=-1
COOLDOWN_RESET
ASSERT_VAR MACRO=_COOLDOWN_VARS VARIABLE=phase VALUE=0
