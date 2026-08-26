import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from dicomfix.gui.controller import MainController
from dicomfix.gui.model import MainModel
from dicomfix.gui.view import MainWindowQtView

_version_ = "0.0.1"

logger = logging.getLogger(__name__)


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', action='count', help="increase output verbosity", default=0)
    parser.add_argument('-V', '--version', action='version', version=_version_)
    parsed_args = parser.parse_args(args)

    # set logging level
    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    app = QApplication(sys.argv)
    view = MainWindowQtView()
    model = MainModel()
    MainController(view, model)
    view.show()

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
