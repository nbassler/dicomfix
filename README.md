# dicomfix
Script for manipulating dicom plans


```
$ python3 dicomfix/main.py -h
usage: main.py [-h] [-w WEIGHTS] [-o OUTPUT] [-e EXPORT_RACEHORSE] [-a] [-dt] [-ic] [-i] [-ia] [-tr4] [-rs]
               [-p PRINT_SPOTS] [-g GANTRY_ANGLES] [-d DUPLICATE_FIELDS] [-rd RESCALE_DOSE] [-rf RESCALE_FACTOR]
               [-rm] [-tp TABLE_POSITION] [-sp SNOUT_POSITION] [-tm TREATMENT_MACHINE] [-pl PLAN_LABEL]
               [-pn PATIENT_NAME] [-rn REVIEWER_NAME] [-v] [-V] [inputfile]

Modify ECLIPSE DICOM proton therapy treatment plans.

positional arguments:
  inputfile             Input DICOM filename

options:
  -h, --help            show this help message and exit
  -w WEIGHTS, --weights WEIGHTS
                        Path to weights CSV file
  -o OUTPUT, --output OUTPUT
                        Path to output DICOM file
  -e EXPORT_RACEHORSE, --export_racehorse EXPORT_RACEHORSE
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
  -p PRINT_SPOTS, --print_spots PRINT_SPOTS
                        Number of random spots to print for comparison
  -g GANTRY_ANGLES, --gantry_angles GANTRY_ANGLES
                        List of comma-separated gantry angles
  -d DUPLICATE_FIELDS, --duplicate_fields DUPLICATE_FIELDS
                        Duplicate all fields in the plan n times
  -rd RESCALE_DOSE, --rescale_dose RESCALE_DOSE
                        New rescaled dose [Gy(RBE)]
  -rf RESCALE_FACTOR, --rescale_factor RESCALE_FACTOR
                        Multiply plan MUs by this factor
  -rm, --rescale_minimize
                        Minimize plan so smallest spot is 1 MU. Overrides the -rd and -rf options.
  -tp TABLE_POSITION, --table_position TABLE_POSITION
                        New table position vertical,longitudinal,lateral [cm]. Negative values should be in quotes and leading space.
  -sp SNOUT_POSITION, --snout_position SNOUT_POSITION
                        Set new snout position [cm]
  -tm TREATMENT_MACHINE, --treatment_machine TREATMENT_MACHINE
                        Treatment Machine Name
  -pl PLAN_LABEL, --plan_label PLAN_LABEL
                        Set plan label
  -pn PATIENT_NAME, --patient_name PATIENT_NAME
                        Set patient name
  -rn REVIEWER_NAME, --reviewer_name REVIEWER_NAME
                        Set reviewer name
  -v, --verbosity       Give more output. Option is additive, can be used up to 3 times
  -V, --version         show program's version number and exit
```


To run locally in venv
```
~/Projects/dicomfix$ pip install -e .
~/Projects/dicomfix$ python dicomfix/main.py
```


The export tool:
```
PYTHONPATH=. python3 dicomfix/export.py -b res/DCPT_beam_model__v2.csv -v -N1000000 -t ../2022_DCPT_LET/data/resources/plans/plan02_mono/RN.1.2.246.352.71.5.37402163639.178320.20221207095327.dcm ../temp/fofo.txt"