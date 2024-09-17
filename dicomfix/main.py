import sys
import logging
from dicomfix.dicomutil import DicomUtil  # Use the new DicomUtil class
from dicomfix.config_parser import parse_arguments
from dicomfix.config import Config

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

    # Instantiate DicomUtil with the input file
    dp = DicomUtil(config.inputfile)

    # Handle inspect option
    if config.inspect:
        dp.inspect()

    # Apply all modifications to the plan using the config object
    dp.modify(config)

    # Save the modified DICOM plan
    dp.save(config.output)

    # Export RACEHORSE file if requested
    if config.export_racehorse:
        dp.export_racehorse()


if __name__ == '__main__':
    sys.exit(main())
