"""Entry point for the dicomfix Qt GUI."""

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from dicomfix.__version__ import __version__
from dicomfix.gui.window import MainWindow

logger = logging.getLogger(__name__)


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="dicomfix-gui", description="Graphical front-end for dicomfix.")
    parser.add_argument('plan', nargs='?', help="DICOM plan to open on startup")
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help="increase output verbosity")
    parser.add_argument('-V', '--version', action='version',
                        version=f'dicomfix-gui {__version__}')
    parsed_args = parser.parse_args(args)

    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    app = QApplication(sys.argv)
    window = MainWindow()
    if parsed_args.plan:
        window.load_plan(parsed_args.plan)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
