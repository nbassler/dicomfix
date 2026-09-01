# Changelog

All notable changes to dicomfix are documented here. Releases before 1.1.0 are on the
[GitHub releases page](https://github.com/nbassler/dicomfix/releases).

## [1.1.0] - unreleased

### ⚠ Action required

- **Range shifter water-equivalent thickness was inverted before this release.** `-rh=RS2`
  wrote 57.0 mm and `-rh=RS5` wrote 22.8 mm; the correct values are 22.8 and 57.0. Plans
  generated with 1.0.0 or earlier using those options should be regenerated.

### Added

- **`-rl` / `--repeat_layer N` repeats the spot list of every energy layer in place**
  (#48), for depth dose curve scanning: a stepper actuator advances the detector between
  passes, so a whole curve is measured in a single delivery instead of one beam request
  per point. Every pass keeps the original weights, so each detector position receives
  what the plan gave and the field delivers N times its MU; this is the opposite of `-rp`,
  which divides. **No control points are added**, deliberately: the delivery system
  requires a field's energy layers to be strictly decreasing, so the layer structure and
  its energies are left exactly as they were. dicomfix now also warns when a plan's layers
  do not decrease, whatever option is in use.
- **`-rld` / `--repeat_layer_delay MU` shims a delay spot into each gap between passes**
  (#48), N−1 per layer, at x = 140 mm, y = 190 mm — the position the TR3/TR4 spot
  measurement plan uses for the same purpose. The magnets have to sweep out there and
  back, which buys the actuator the time it needs. Requires `-rl`. `BeamMeterset` grows
  with the delay MU but `BeamDose` stays at N × original, since that dose lands far out in
  the field rather than at the dose reference point, so such a plan no longer carries one
  Gy-per-MU ratio; dicomfix reports this when it inserts the spots.
- **`-mc` / `--minimize_current` appends a 1 MU dummy spot to every energy layer** (#30).
  The cyclotron picks its current from what a layer has to deliver, so a layer holding one
  spot at the smallest deliverable meterset has to be delivered at the lowest current the
  machine can produce. The dummy spot goes at x = 140 mm, y = 190 mm, off axis, because
  its dose is real and should not land on what is being measured. `BeamMeterset` grows by
  1 MU per layer while `BeamDose` stays put, for the same reason. Independent of every
  other option; with `-rl` it is added once per layer rather than once per pass.
- **`-ds` / `--dump_spot "x,y"` moves the dump area** those added spots are placed in,
  given in cm like the other coordinate options. It applies to the dummy spot and the
  delay spot alike, since both exist to put their dose somewhere that is not the target.
  A position outside the 30 x 40 cm maximum field is refused rather than written into an
  undeliverable plan.
- **A working graphical interface** (`dicomfix-gui`), covering rescaling, field
  duplication, range shifter, treatment machine, gantry angle, table and snout position
  (#41). Edits are queued and applied on export. Ships as a standalone Windows executable.
  It builds a dicomfix command line and runs it through the same code path as the CLI, so
  its output is byte-for-byte identical to the equivalent command.
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
- Rescaling crashed with `AttributeError: NominalBeamEnergy` on plans whose control points
  omit that tag where the energy does not change, which DICOM allows
- Range shifter removal left dangling settings in the control points
- `dicomfix.gui` and `dicomfix.web` were not actually packaged
