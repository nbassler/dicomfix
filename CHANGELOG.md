# Changelog

All notable changes to dicomfix are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Releases
before 1.1.0 are listed on the
[GitHub releases page](https://github.com/nbassler/dicomfix/releases).

## [1.1.0] - unreleased

### ⚠ Action required

- **Range shifter water-equivalent thickness was inverted before this release.** `-rh=RS2`
  wrote 57.0 mm and `-rh=RS5` wrote 22.8 mm; the correct values are 22.8 mm and 57.0 mm.
  Any plan generated with dicomfix 1.0.0 or earlier using `-rh=RS2` or `-rh=RS5` carries the
  wrong `RangeShifterWaterEquivalentThickness` and should be regenerated. Plans that did not
  set a range shifter are unaffected.

### Added

- **Independent verification of every rescale** (`dicomfix/verify.py`). After any `-rf`,
  `-rd`, `-rm` or `-w`, the plan's delivered monitor units are recomputed from its DICOM
  tags by code that shares nothing with the rescaling logic, and compared against what was
  requested. A mismatch raises `RescaleVerificationError` and the plan is not written.
  Checks cover per-spot meterset, plan total, `BeamMeterset` self-consistency, `BeamDose`,
  `TargetPrescriptionDose`, spot positions, beam energies, negative meterset and
  undeliverable surviving spots.
- **A `dicomfix` console entry point.** `pip install dicomfix` previously installed no
  command at all; `[project.scripts]` now provides one.
- **Loud dose-rescale reporting**, shown without needing `-v`: the dose found in the plan,
  the dose requested, the factor derived from them, and the beam meterset before and after.
  The dose already in a plan may have drifted from earlier manipulation, and the factor is
  derived from it, so this is reported rather than assumed.
- CI status badges and a Dependabot configuration (#42).

### Changed

- `TargetPrescriptionDose` (300A,0026) now scales together with `BeamDose` in all rescale
  modes. Previously a rescaled plan stated its original prescription while delivering a
  different dose. **Output files differ from 1.0.0 for any plan that carries a prescription
  dose.**
- `-rd` now refuses plans with more than one field, with an explanation, instead of
  crashing. `BeamDose` is per field, so a target dose is ambiguous on a multi-field plan;
  use `-rf` to apply an explicit factor there.
- `-rf` and `apply_rescale_factor()` now reject zero and negative factors. `-rf=-1.0`
  previously wrote a complete DICOM file containing negative monitor units.
- The `gui` extra installs `pyqt6` instead of `pyqt6-tools`, which is Qt Designer tooling
  that pins an old PyQt6 and often fails to install on current Python.
- The `dev` extra now includes the web dependency, so `pip install -e ".[dev]"` can run the
  whole test suite. It previously could not.
- `dicomfix.gui` and `dicomfix.web` are now actually packaged; a non-editable install
  shipped neither, and `main_window.ui` was not declared as package data.
- Linting moved from flake8 to ruff, configured in `pyproject.toml`.

### Fixed

- **`-rh=None` was silently ignored** (#43). The option parsed to Python `None`, which was
  indistinguishable from the flag not being given, so the range shifter stayed in the output
  plan and nothing was logged.
- Range shifter removal left a dangling `RangeShifterSettingsSequence` in the control
  points, referencing a range shifter that no longer existed.
- **`-rd` crashed on any plan with two or more fields** (#45), with
  `TypeError: '>' not supported between instances of 'MultiValue' and 'float'`.
- **Rescaling twice in one session raised `TypeError`** (#45). `apply_rescale_factor()` read
  spot weights as a `list` but wrote them back as a pydicom `MultiValue`, which is not a
  `list` subclass. This affected the Streamlit UI, which keeps one plan in session state and
  rescales on every edit, so a second dose entry failed.
- The Qt GUI raised `AttributeError` on any `-v` invocation: `logging.basicConfig` had been
  written as `logger.basicConfig`.
- `dicomfix.gui.main` could not be imported as a module; its imports were not
  package-relative.
- The `-tt` help text was missing a space between two concatenated strings.
- `tests/test_web_app.py` resolved its paths against the wrong directory, which had left CI
  failing.

### Notes

- The `test` and `lint` extras that briefly existed on `main` were never part of a release;
  `dev` covers both.
- Dose constraints in `DoseReferenceSequence` (`DeliveryMaximumDose`,
  `OrganAtRiskMaximumDose` and similar) are deliberately **not** rescaled. They are limits
  rather than delivered dose. Rescaling reports which ones it left alone.
