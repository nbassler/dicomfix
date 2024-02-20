# dicomfix
Script for manipulating dicom plans


```
$ python3 dicomfix/main.py -h
usage: main.py [-h] [-w WEIGHTS] [-o OUTPUT] [-e EXPORT_RACEHORSE] [-a] [-dt] [-ic] [-i] [-tr4] [-p PRINT_SPOTS] [-g GANTRY_ANGLES] [-d DUPLICATE_FIELDS] [-rd RESCALE_DOSE] [-rf RESCALE_FACTOR]
               [-tp TABLE_POSITION] [-sp SNOUT_POSITION] [-tm TREATMENT_MACHINE] [-pl PLAN_LABEL] [-pn PATIENT_NAME] [-rn REVIEWER_NAME] [-v]
               inputfile

Modify ECLIPSE DICOM proton therapy treatment plans.

positional arguments:
  inputfile             input filename

options:
  -h, --help            show this help message and exit
  -w WEIGHTS, --weights WEIGHTS
                        Path to weights CSV file
  -o OUTPUT, --output OUTPUT
                        Path to output DICOM file
  -e EXPORT_RACEHORSE, --export_racehorse EXPORT_RACEHORSE
                        Baseneame for spot list, in Varian RACEHORSE csv-format.
  -a, --approve         Set plan to APPROVED
  -dt, --date           Set RT date to now
  -ic, --intent_curative
                        Set plan intent to CURATIVE
  -i, --inspect         Print contents of dicom file exit
  -tr4, --wizard_tr4    prepare plan for TR4, this sets aproval, gantry, snout and treatment machine
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
  -tp TABLE_POSITION, --table_position TABLE_POSITION
                        New table position vertical,longitudinal,lateral [cm]. Negative values should be in quotes and leading space.
  -sp SNOUT_POSITION, --snout_position SNOUT_POSITION
                        Set new snout position
  -tm TREATMENT_MACHINE, --treatment_machine TREATMENT_MACHINE
                        Treatment Machine Name
  -pl PLAN_LABEL, --plan_label PLAN_LABEL
                        Set plan label
  -pn PATIENT_NAME, --patient_name PATIENT_NAME
                        Set patient name
  -rn REVIEWER_NAME, --reviewer_name REVIEWER_NAME
                        Set reviewer name
  -v, --verbosity       give more output. Option is additive, and can be used up to 3 times
```
