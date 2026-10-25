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

The real-firmware tests (`tests/test_klippy.py`) run in CI against Klipper and Kalico; see
the workflow for how to run them locally.

- Follow [Hardware Controls' docs/STYLE.md](https://github.com/IdleStep/Klipper-Hardware-Controls/blob/main/docs/STYLE.md).
- A changed message changes its test and, if it is in the troubleshooting table, its README
  line in the same commit.
- Add an entry to the CHANGELOG under "Unreleased".
- Safety first: when the cooldown cannot continue it says so and leaves the heaters and
  fans as the user set them, or turns the heaters off when it cannot know the
  temperatures. Anything else needs a reason in the pull request.

## Versions

The version follows the cooldown API, as the CHANGELOG explains. Releases are annotated
tags named `vMAJOR.MINOR.PATCH`; Moonraker's `channel: stable` follows them.
