import sys
import logging
from dicomfix.dicom_handler import DicomFix
from dicomfix.config_parser import parse_arguments
from dicomfix.config import Config  # Import the new Config class

logger = logging.getLogger(__name__)


def main(args=None):
    """Main routine for handling the DICOM manipulation."""

    if args is None:
        args = sys.argv[1:]

    # Parse the command-line arguments
    parsed_args = parse_arguments(args)

    # Create a configuration object
    config = Config(parsed_args)

    # Set up logging based on verbosity
    if config.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif config.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    # Instantiate DicomFix with the input file
    df = DicomFix(config.inputfile)

    # Handle inspect option
    if config.inspect:
        df.inspect()

    # Apply modifications to the plan using the config object
    df.copy(config.weights, config.approve, config.intent_curative, config.date,
            config.print_spots, config.gantry_angles,
            config.duplicate_fields, config.rescale_dose, config.rescale_factor,
            config.table_position, config.snout_position,
            config.treatment_machine, config.plan_label, config.patient_name,
            config.reviewer_name,
            config.wizard_tr4,
            config.rescale_minimize)

    # Save the modified DICOM plan
    df.save(config.output)

    # Export RACEHORSE file if requested
    if config.export_racehorse:
        df.export_racehorse()


if __name__ == '__main__':
    sys.exit(main())
