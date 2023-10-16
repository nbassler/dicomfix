import logging
import os

from PyQt6 import QtWidgets, uic

current_directory = os.path.dirname(os.path.realpath(__file__))

logger = logging.getLogger(__name__)

class UiMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(UiMainWindow, self).__init__()
        ui_path = os.path.join(current_directory, 'main_window.ui')
        uic.loadUi(ui_path, self)
        self.setWindowTitle("DicomFix")


class MainWindowQtView(object):
    def __init__(self):
        self.ui = UiMainWindow()
        self.test_property = 1
        self._initialize()

    def show(self):
        self.ui.show()

    def exit(self):
        self.ui.close()


    def _initialize(self):
        ''' Attach all callbacks '''
        self.open_dicom_callback = self.on_open_dicom

    def browse_folder_path(self, name, path=None):
        """
        :return full file path, or empty string
        """
        dialog = QFileDialog(self.ui, name, path)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOptions(QFileDialog.ShowDirsOnly)
        dialog.exec_()
        selected_path = os.path.join(dialog.directory().path(), '')
        if dialog.result() == QFileDialog.Accepted:
            return selected_path
        return ""


    def show_info(self, name, content):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self.ui, name, content)

    # connect callbacks to UI here. These will only be run during setup.
    @property  # getter
    def open_dicom_callback(self):
        print("open_dicom_callback")
        return None

    @open_dicom_callback.setter  # setter
    def open_dicom_callback(self, callback):
        print("func open_dicom_callback")
        self.ui.actionOpen.triggered.connect(callback)


    # all callbacks here
    def on_open_dicom(self):
        print("foobar")