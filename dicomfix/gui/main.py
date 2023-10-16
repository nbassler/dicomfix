import sys
import logging
import argparse

from PyQt6.QtWidgets import QApplication

from view import MainWindowQtView
from model import MainModel
from controller import MainController

_version_ = "0.0.1"

logger = logging.getLogger(__name__)


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', action='count', help="increase output verbosity", default=0)
    parser.add_argument('-V', '--version', action='version', version=_version_)
    args = parser.parse_args(sys.argv[1:])

    # set logging level
    if args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif args.verbosity > 1:
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
    sys.exit(main(sys.argv[1:]))
