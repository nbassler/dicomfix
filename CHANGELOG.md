# Changelog

All notable changes to dicomfix are documented here. Releases before 1.1.0 are on the
[GitHub releases page](https://github.com/nbassler/dicomfix/releases).

## [1.1.0] - unreleased

### ⚠ Action required

- **Range shifter water-equivalent thickness was inverted before this release.** `-rh=RS2`
  wrote 57.0 mm and `-rh=RS5` wrote 22.8 mm; the correct values are 22.8 and 57.0. Plans
  generated with 1.0.0 or earlier using those options should be regenerated.

### Added

- `-rl` / `--repeat_layer N` — repeat every energy layer's spot list in place, for depth
  dose curve scanning. Plan MU and dose grow by N; no control points are added (#48).
- `-rld` / `--repeat_layer_delay MU` — delay spot between passes, so a stepper has time to
  move. Requires `-rl`. `BeamDose` does not include the delay MU (#48).
- `-mc` / `--minimize_current` — appends a 1 MU dummy spot to every layer, pinning the
  cyclotron to its lowest beam current (#30).
- `-ds` / `--dump_spot "x,y"` — where the spots added by `-mc` and `-rld` go, in cm.
  Default 14,19; outside the maximum field is refused.
- A graphical interface, `dicomfix-gui` (#41). Edits are queued and applied on export, by
  running the equivalent CLI command, so its output is identical.
- Independent verification of every rescale: on a mismatch dicomfix raises and writes
  nothing.
- Console entry points `dicomfix` and `dicomfix-gui`, which `pip install` previously did
  not create.
- A warning whenever a plan's layer energies do not decrease, whatever option is in use.
- Dose rescaling reports what it did without needing `-v`.

### Changed

- **`TargetPrescriptionDose` now scales with `BeamDose`. Output differs from 1.0.0 for any
  plan carrying a prescription dose.** Delivery was unaffected — the tag is only read back
  on re-import.
- **Windows release assets are now zip archives** (#52): `dicomfix-windows-x86_64.zip` and
  `dicomfix-gui-windows-x86_64.zip`. Unpack and run the executable from the extracted
  folder, keeping that folder together. Built with `--onedir`, because `--onefile` was
  flagged as malware on download.
- `-pl`, `-tm`, `-pn` and `-rn` refuse text longer than the DICOM value representation
  allows, rather than writing a plan the console rejects.
- `-rd` refuses multi-field plans instead of crashing; use `-rf`.
- `-rf` refuses zero and negative factors.
- The `gui` extra installs `pyqt6` rather than the stale `pyqt6-tools`; `dev` now includes
  `gui` and `web`.
- Linting moved from flake8 to ruff.
- **The Windows release assets are now zip archives, not bare executables** (#52):
  `dicomfix-windows-x86_64.zip` and `dicomfix-gui-windows-x86_64.zip` in place of
  `dicomfix.exe` and `dicomfix-gui.exe`. Unpack and run the executable from the extracted
  folder, and keep that folder together — it loads what it needs from the `_internal`
  directory beside it. The binaries are built with PyInstaller's `--onedir` rather than
  `--onefile`, because the onefile bootloader unpacks itself into `%TEMP%` and executes
  from there, which Windows Defender flagged as a trojan and refused to download. Windows
  still warns that the publisher is unknown, since the binaries are unsigned, but the
  warning can be overridden. The Linux archives are unchanged in name and now unpack to a
  directory rather than a single file.

### Removed

- `-e` / `--export_racehorse` and the `DicomExport` module (#31). Exporting belongs to
  [dicomexport](https://github.com/nbassler/dicomexport), which already carries these
  exporters. Reading a weights CSV with `-w` is unaffected.

### Fixed

- The GUI inspect pane now uses a fixed-width font on Windows
- `-rh=None` was silently ignored, leaving the range shifter in the output plan (#43)
- `-i` crashed on plans with no table position set, which includes RayStation exports (#37)
- `-rd` crashed on plans with two or more fields (#45)
- Rescaling twice in one session raised `TypeError`, breaking the Streamlit UI (#45)
- Rescaling crashed with `AttributeError: NominalBeamEnergy` on plans whose control points
  omit that tag, which DICOM allows
- Range shifter removal left dangling settings in the control points
- `dicomfix.gui` and `dicomfix.web` were not actually packaged
