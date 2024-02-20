import sys
import argparse
import logging

from dicom_handler import DicomFix

logger = logging.getLogger(__name__)


def read_weights(csv_file_path):
    """Read CSV file with new weights for each energy layer"""
    weights = []
    with open(csv_file_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            weights.append(float(line))
    return weights


def main(args=None):
    """Option parsing and main routine."""

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description='Modify ECLIPSE DICOM proton therapy treatment plans.')
    parser.add_argument('inputfile', help='input filename', type=str)

    parser.add_argument('-w', '--weights', required=False, help='Path to weights CSV file', default=None)
    parser.add_argument('-o', '--output', required=False, default="output.dcm", help='Path to output DICOM file')
    parser.add_argument('-e', '--export_racehorse', required=False, default=None,
                        help='Baseneame for spot list, in Varian RACEHORSE csv-format.')

    parser.add_argument('-a', '--approve', action='store_true', default=False, help='Set plan to APPROVED')
    parser.add_argument('-dt', '--date', action='store_true', default=False, help='Set RT date to now')
    parser.add_argument('-ic', '--intent_curative', action='store_true', default=False,
                        help='Set plan intent to CURATIVE')
    parser.add_argument('-i', '--inspect', action='store_true', default=False, help='Print contents of dicom file exit')
    parser.add_argument('-tr4', '--wizard_tr4', action='store_true', default=False,
                        help='prepare plan for TR4, this sets aproval, gantry, snout and treatment machine')
    parser.add_argument('-p', '--print_spots', type=int, default=None,
                        help='Number of random spots to print for comparison')
    parser.add_argument('-g', '--gantry_angles', type=str, default=None, help='List of comma-separated gantry angles')
    parser.add_argument('-d', '--duplicate_fields', type=int, default=None,
                        help='Duplicate all fields in the plan n times')
    parser.add_argument('-rd', '--rescale_dose', type=float, default=None, help='New rescaled dose [Gy(RBE)]')
    parser.add_argument('-rf', '--rescale_factor', type=float, default=None, help='Multiply plan MUs by this factor')
    parser.add_argument('-tp', '--table_position', type=str, default=None,
                        help='New table position vertical,longitudinal,lateral [cm]. ' +
                             'Negative values should be in quotes and leading space.')
    parser.add_argument('-sp', '--snout_position', type=float, default=None, help='Set new snout position')
    parser.add_argument('-tm', '--treatment_machine', type=str, default=None, help='Treatment Machine Name')
    parser.add_argument('-pl', '--plan_label', type=str, default=None, help='Set plan label')
    parser.add_argument('-pn', '--patient_name', type=str, default=None, help='Set patient name')
    parser.add_argument('-rn', '--reviewer_name', type=str, default=None, help='Set reviewer name')

    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='give more output. Option is additive, and can be used up to 3 times')

    parsed_args = parser.parse_args(args)

    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    # convert types for a few input arguments
    gantry_angles = None
    if parsed_args.gantry_angles:
        gantry_angles = tuple(float(x) for x in parsed_args.gantry_angles.split(","))

    table_position = None
    if parsed_args.table_position:
        table_position = tuple(float(x) for x in parsed_args.table_position.split(","))

    weights = None
    if parsed_args.weights:
        # csv_weights = read_weights_from_csv(args.weights)
        weights = read_weights(parsed_args.weights)

    df = DicomFix(parsed_args.inputfile)

    if parsed_args.inspect:
        df.inspect()

    df.copy(weights, parsed_args.approve, parsed_args.intent_curative, parsed_args.date,
            parsed_args.print_spots, gantry_angles,
            parsed_args.duplicate_fields, parsed_args.rescale_dose, parsed_args.rescale_factor,
            table_position, parsed_args.snout_position,
            parsed_args.treatment_machine, parsed_args.plan_label, parsed_args.patient_name,
            parsed_args.reviewer_name,
            parsed_args.wizard_tr4)

    df.save(parsed_args.output)

    if parsed_args.export_racehorse:
        df.export_racehorse()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
