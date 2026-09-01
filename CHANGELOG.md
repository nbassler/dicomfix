# Changelog

All notable changes to dicomfix are documented here. Releases before 1.1.0 are on the
[GitHub releases page](https://github.com/nbassler/dicomfix/releases).

## [1.1.0] - unreleased

### ⚠ Action required

- **Range shifter water-equivalent thickness was inverted before this release.** `-rh=RS2`
  wrote 57.0 mm and `-rh=RS5` wrote 22.8 mm; the correct values are 22.8 and 57.0. Plans
  generated with 1.0.0 or earlier using those options should be regenerated.

### Added

- **A working graphical interface** (`dicomfix-gui`), covering rescaling, field
  duplication, range shifter, treatment machine, gantry angle, table and snout position
  (#41). Edits are queued and applied on export. Ships as a standalone Windows executable.
  It builds a dicomfix command line and runs it through the same code path as the CLI, so
  its output is byte-for-byte identical to the equivalent command.
- **`-rl` / `--repeat_layers N` repeats a field's energy layer sequence in place** (#48),
  for depth dose curve scanning: the detector steps one position between repetitions, so
  a whole curve can be measured in a single delivery instead of one beam request per
  point. The layer sequence is repeated as a whole (`L1 L2 L3 L1 L2 L3 ...`), not layer
  by layer, which is what `-rp` already does at spot level. MU per spot is unchanged, so
  `BeamMeterset`, `FinalCumulativeMetersetWeight` and `BeamDose` all grow by a factor N.
  Applied after every other option, since `-tr4`, `-g`, `-tp` and `-sp` only write to the
  first control point. The synthetic delay layers between repetitions are still to come.
- **Independent verification of every rescale.** After `-rf`, `-rd`, `-rm` or `-w`, the
  plan's delivered monitor units are recomputed from its DICOM tags by code that shares
  nothing with the rescaling logic. On a mismatch dicomfix raises and writes nothing.
- **Console entry points.** `pip install dicomfix` previously installed no command at all;
  `dicomfix` and `dicomfix-gui` are now declared.
- **Dose rescaling reports what it did** without needing `-v`: dose found, dose requested,
  factor applied, and meterset before and after.

### Changed

- `TargetPrescriptionDose` now scales with `BeamDose`. **Output differs from 1.0.0 for any
  plan carrying a prescription dose.** That tag is only read back on re-import, so
  delivery was unaffected.
- `-rd` refuses multi-field plans instead of crashing; `BeamDose` is per field, so a target
  dose is ambiguous there. Use `-rf`.
- `-rf` refuses zero and negative factors. `-rf=-1.0` previously wrote a plan with negative
  monitor units.
- The `gui` extra installs `pyqt6` rather than the stale `pyqt6-tools`, and `dev` now
  includes `gui` and `web` so it can run the whole test suite.
- Linting moved from flake8 to ruff.

### Fixed

- `-rh=None` was silently ignored, leaving the range shifter in the output plan (#43)
- `-i` crashed on plans with no table position set, which includes RayStation exports (#37)
- `-rd` crashed on plans with two or more fields (#45)
- Rescaling twice in one session raised `TypeError`, breaking the Streamlit UI (#45)
- Rescaling crashed with `AttributeError: NominalBeamEnergy` on plans whose control
  points omit that tag where the energy does not change, which DICOM allows
- Range shifter removal left dangling settings in the control points
- `dicomfix.gui` and `dicomfix.web` were not actually packaged
