import os
import logging

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QFileDialog, QAbstractItemView
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QStringListModel

current_directory = os.path.dirname(os.path.realpath(__file__))

logger = logging.getLogger(__name__)


class UiMainWindow(QMainWindow):
    def __init__(self):
        super(UiMainWindow, self).__init__()
        ui_path = os.path.join(current_directory, 'main_window.ui')
        uic.loadUi(ui_path, self)
        self.setWindowTitle("DicomFix")
        self._selection_changed_callback = None
        self._treatment_machine_changed_callback = None


class MainWindowQtView:
    def __init__(self):
        self.ui = UiMainWindow()

        # Setup file list model
        self.file_list_model = QStringListModel()
        self.ui.listView.setModel(self.file_list_model)
        self.ui.listView.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        self.test_property = 1  # debug and testing

    def show(self):
        self.ui.show()

    def exit(self):
        self.ui.close()

    def open_dicom_files(self, path="${HOME}"):
        fnames = QFileDialog.getOpenFileNames(
            self.ui,
            "Open File",
            path,
            "Dicom plans (*.dcm);;All files (*)"
        )
        return fnames

    def show_info(self, name, content):
        QMessageBox.information(self.ui, name, content)

    # define callbacks here
    @property  # getter
    def open_dicom_callback(self):
        return self._open_dicom_callback

    @open_dicom_callback.setter
    def open_dicom_callback(self, callback):
        self.ui.actionOpen.triggered.connect(callback)
        self._open_dicom_callback = callback

    @property  # getter
    def selection_changed_callback(self):
        return self._selection_changed_callback

    @selection_changed_callback.setter
    def selection_changed_callback(self, callback):
        self.ui.listView.selectionModel().selectionChanged.connect(callback)
        self._selection_changed_callback = callback

    @property  # getter
    def approve_callback(self):
        return self._approved_callback

    @approve_callback.setter
    def approve_changed_callback(self, callback):
        self.ui.checkBox.stateChanged(callback)
        self._approve_changed_callback = callback

    @property
    def treatment_machine_changed_callback(self):
        return self._treatment_machine_changed_callback

    @treatment_machine_changed_callback.setter
    def treatment_machine_changed_callback(self, callback):
        self.ui.comboBox_treatment_machine.currentIndexChanged.connect(callback)
