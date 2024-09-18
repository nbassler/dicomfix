import argparse


def parse_arguments(args=None):
    """
    Parse command-line arguments and return them.
    """
    parser = argparse.ArgumentParser(description='Modify ECLIPSE DICOM proton therapy treatment plans.')

    parser.add_argument('inputfile', help='Input DICOM filename', type=str)

    parser.add_argument('-w', '--weights', help='Path to weights CSV file', default=None)
    parser.add_argument('-o', '--output', default="output.dcm", help='Path to output DICOM file')
    parser.add_argument('-e', '--export_racehorse', default=None,
                        help='Basename for spot list, in Varian RACEHORSE csv-format.')

    parser.add_argument('-a', '--approve', action='store_true', default=False, help='Set plan to APPROVED')
    parser.add_argument('-dt', '--date', action='store_true', default=False, help='Set RT date to now')
    parser.add_argument('-ic', '--intent_curative', action='store_true', default=False,
                        help='Set plan intent to CURATIVE')
    parser.add_argument('-i', '--inspect', action='store_true', default=False, help='Print contents of DICOM file and exit')
    parser.add_argument('-tr4', '--wizard_tr4', action='store_true', default=False,
                        help='Prepare plan for TR4: sets approval, gantry, snout, and treatment machine')

    parser.add_argument('-rs', '--fix_raystation', action='store_true', default=False,
                        help='Make RayStation plans compatible with Varian proton systems')

    parser.add_argument('-p', '--print_spots', type=int, default=None,
                        help='Number of random spots to print for comparison')
    parser.add_argument('-g', '--gantry_angles', type=str, default=None,
                        help='List of comma-separated gantry angles')
    parser.add_argument('-d', '--duplicate_fields', type=int, default=None,
                        help='Duplicate all fields in the plan n times')
    parser.add_argument('-rd', '--rescale_dose', type=float, default=None,
                        help='New rescaled dose [Gy(RBE)]')
    parser.add_argument('-rf', '--rescale_factor', type=float, default=None,
                        help='Multiply plan MUs by this factor')
    parser.add_argument('-rm', '--rescale_minimize', action='store_true', default=False,
                        help='Minimize plan so smallest spot is 1 MU. Overrides the -rd and -rf options.')

    parser.add_argument('-tp', '--table_position', type=str, default=None,
                        help='New table position vertical,longitudinal,lateral [cm]. ' +
                             'Negative values should be in quotes and leading space.')
    parser.add_argument('-sp', '--snout_position', type=float, default=None,
                        help='Set new snout position [cm]')
    parser.add_argument('-tm', '--treatment_machine', type=str, default=None,
                        help='Treatment Machine Name')
    parser.add_argument('-pl', '--plan_label', type=str, default=None,
                        help='Set plan label')
    parser.add_argument('-pn', '--patient_name', type=str, default=None,
                        help='Set patient name')
    parser.add_argument('-rn', '--reviewer_name', type=str, default=None,
                        help='Set reviewer name')

    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='Give more output. Option is additive, can be used up to 3 times')

    return parser.parse_args(args)
