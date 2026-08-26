# dicomfix

[![CI](https://github.com/nbassler/dicomfix/actions/workflows/ci.yml/badge.svg)](https://github.com/nbassler/dicomfix/actions/workflows/ci.yml)
[![Automated tests](https://github.com/nbassler/dicomfix/actions/workflows/python-app.yml/badge.svg)](https://github.com/nbassler/dicomfix/actions/workflows/python-app.yml)
[![Build Binaries](https://github.com/nbassler/dicomfix/actions/workflows/build-binaries.yml/badge.svg)](https://github.com/nbassler/dicomfix/actions/workflows/build-binaries.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Script for manipulating dicom plans


```console
$ dicomfix -h
usage: dicomfix [-h] [-w WEIGHTS] [-o OUTPUT] [-e EXPORT_RACEHORSE] [-a] [-dt] [-ic] [-i] [-ia] [-tr4] [-rs]
                [-p PRINT_SPOTS] [-g GANTRY_ANGLES] [-d DUPLICATE_FIELDS] [-rd RESCALE_DOSE]
                [-rf RESCALE_FACTOR] [-rm] [-tp TABLE_POSITION] [-tt] [-sp SNOUT_POSITION]
                [-tm TREATMENT_MACHINE] [-pl PLAN_LABEL] [-pn PATIENT_NAME] [-rn REVIEWER_NAME]
                [-rh RANGE_SHIFTER] [-rp REPAINTING] [-v] [-V]
                [inputfile]

Modify ECLIPSE DICOM proton therapy treatment plans.

positional arguments:
  inputfile             Input DICOM filename

options:
  -h, --help            show this help message and exit
  -w, --weights WEIGHTS
                        Path to weights CSV file
  -o, --output OUTPUT   Path to output DICOM file
  -e, --export_racehorse EXPORT_RACEHORSE
                        Basename for spot list, in Varian RACEHORSE csv-format.
  -a, --approve         Set plan to APPROVED
  -dt, --date           Set RT date to now
  -ic, --intent_curative
                        Set plan intent to CURATIVE
  -i, --inspect         Print a summary of the DICOM file and exit
  -ia, --inspect_all    Print all tags in the DICOM file and exit
  -tr4, --wizard_tr4    Prepare plan for TR4: sets approval, gantry, snout, and treatment machine
  -rs, --fix_raystation
                        Make RayStation plans compatible with Varian proton systems
  -p, --print_spots PRINT_SPOTS
                        Number of random spots to print for comparison
  -g, --gantry_angles GANTRY_ANGLES
                        List of comma-separated gantry angles
  -d, --duplicate_fields DUPLICATE_FIELDS
                        Duplicate all fields in the plan n times
  -rd, --rescale_dose RESCALE_DOSE
                        New rescaled dose [Gy(RBE)]
  -rf, --rescale_factor RESCALE_FACTOR
                        Multiply plan MUs by this factor
  -rm, --rescale_minimize
                        Minimize plan so smallest spot is 1 MU. Overrides the -rd and -rf options.
  -tp, --table_position TABLE_POSITION
                        New table position vertical,longitudinal,lateral [cm]. Use like tp="0,10.5,-5"
                        (important to include the equation mark and quotes)
  -tt, --tolerance_table
                        Add a default IonToleranceTableSequence to the plan. Existing values will be
                        overwritten with a default set.
  -sp, --snout_position SNOUT_POSITION
                        Set new snout position [cm]
  -tm, --treatment_machine TREATMENT_MACHINE
                        Treatment Machine Name
  -pl, --plan_label PLAN_LABEL
                        Set plan label
  -pn, --patient_name PATIENT_NAME
                        Set patient name
  -rn, --reviewer_name REVIEWER_NAME
                        Set reviewer name
  -rh, --range_shifter RANGE_SHIFTER
                        Set range shifter (None, RS2 or RS5) are the only valid options
  -rp, --repainting REPAINTING
                        Repaint each layer multiple times without changing MU.
  -v, --verbosity       Give more output. Option is additive, can be used up to 3 times
  -V, --version         show program's version number and exit
```


## Installation

For development, install in editable mode so source edits take effect immediately:

```console
$ cd ~/Projects/dicomfix
$ pip install -e ".[dev]"    # omit [dev] to skip the test and lint tools
$ dicomfix -h
```

To make `dicomfix` available in every shell without activating a virtualenv:

```console
$ uv tool install --editable ~/Projects/dicomfix
```

## Graphical interface

A Qt front-end covers the common operations: rescaling, field duplication, range shifter,
treatment machine, gantry angle, table position and snout position.

The GUI needs the `gui` extra, which `dev` already includes:

```console
$ pip install -e ".[gui]"     # or ".[dev]", which pulls in gui and web
$ dicomfix-gui                # optionally: dicomfix-gui path/to/plan.dcm
```

On Windows, download `dicomfix-gui.exe` from the
[releases page](https://github.com/nbassler/dicomfix/releases) — no Python installation
needed.

Open a plan with **File → Open**, adjust the controls, then press **Export**. Edits are
queued rather than applied as you go, so nothing is written until you export.

The status bar shows the equivalent `dicomfix` command line for whatever you have queued.
The GUI applies edits by running that exact command through the same code path as the CLI,
so a plan exported from the GUI is byte-for-byte identical to the same plan produced on the
command line — copy the command into a script when you need the operation to be
reproducible.

Controls are grouped by what they affect. **Plan (applies to all fields)** holds everything
dicomfix writes to every field at once — table position, snout, treatment machine, range
shifter. **Per field** holds the field selector and the gantry angle, which is the only
value dicomfix sets per field; `Copy to all fields` gives every field the gantry shown.

Note that DICOM stores the table position per field even though dicomfix writes one value
to all of them. If a plan's fields have different table positions, the GUI warns before
exporting, because the others would be overwritten.

The couch angle is displayed but greyed out: dicomfix has no way to write
`PatientSupportAngle`. `Retract Nozzle` sets the snout to its fully retracted position,
42.1 cm.
