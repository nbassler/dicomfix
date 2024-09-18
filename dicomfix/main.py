import sys
import logging
from dicomfix.dicomutil import DicomUtil  # Use the new DicomUtil class
from dicomfix.config_parser import parse_arguments
from dicomfix.config import Config
from dicomfix.dicomexport import DicomExport

logger = logging.getLogger(__name__)


def main(args=None):
    """
    Main routine for handling DICOM manipulation in the dicomfix tool.

    This function parses command-line arguments, applies modifications to the DICOM plan using
    the DicomUtil class, and saves the modified DICOM file. It also supports exporting the plan
    in Varian RACEHORSE format if requested.

    Args:
        args (list of str, optional): Command-line arguments. Defaults to None, which means
                                      arguments will be taken from sys.argv.
    """
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
    logger.debug(f"Reading input file: '{config.inputfile}'")
    dp = DicomUtil(config.inputfile)

    # Handle inspect option
    if config.inspect:
        logger.info(dp.inspect())
        exit(0)

    # Apply all modifications to the plan using the config object
    dp.modify(config)

    # Save the modified DICOM plan
    dp.save(config.output)

    # Export RACEHORSE file if requested
    if config.export_racehorse:
        DicomExport.export(dp.dicom, config.export_racehorse, "racehorse")


if __name__ == '__main__':
    sys.exit(main())
