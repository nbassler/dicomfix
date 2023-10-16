import logging
import os

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QAbstractItemView
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

class MainWindowQtView:
    def __init__(self):
        self.ui = UiMainWindow()
        print(dir(self.ui.listView))
        self.file_list_model = QStringListModel()
        self.ui.listView.setModel(self.file_list_model)
        self.ui.listView.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.test_property = 1

    def show(self):
        self.ui.show()

    def exit(self):
        self.ui.close()

    def open_dicom_files(self, path="${HOME}"):
        fnames = QFileDialog.getOpenFileNames(
            self.ui,
            "Open File",
            path,
            "Dicom plans (RP*.dcm RM*.dcm);;All files (*)"
        )
        return(fnames)

    def show_info(self, name, content):
        from PyQt6.QtWidgets import QMessageBox
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