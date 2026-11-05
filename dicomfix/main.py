import logging
import shlex
import sys

from dicomfix.__version__ import __version__
from dicomfix.config import Config
from dicomfix.config_parser import parse_arguments
from dicomfix.dicomutil import DicomUtil

logger = logging.getLogger(__name__)


def main(args=None):
    """
    Main routine for handling DICOM manipulation in the dicomfix tool.

    This function parses command-line arguments, applies modifications to the DICOM plan using
    the DicomUtil class, and saves the modified DICOM file.

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

    # First thing in the log, so a log saved with -v 2> file records what wrote the plan,
    # and how. Quoted, so the logged command can be pasted back into a shell.
    logger.info(f"dicomfix {__version__}")
    logger.info(f"Command: {shlex.join(['dicomfix', *args])}")

    if config.inputfile is None:
        logger.error("No input file provided. Exiting.")
        logger.error("Use 'dicomfix -h' for help.")
        sys.exit(1)

    # Instantiate DicomUtil with the input file
    logger.debug(f"Reading input file: '{config.inputfile}'")
    dp = DicomUtil(config.inputfile)

    # Handle inspect option
    if config.inspect:
        print(dp.inspect())
        sys.exit(0)

    # Handle inspect_all option
    if config.inspect_all:
        print(dp.inspect_all())
        sys.exit(0)

    # Apply all modifications to the plan using the config object
    dp.modify(config)

    # Save the modified DICOM plan
    dp.save(config.output)


if __name__ == '__main__':
    sys.exit(main())
