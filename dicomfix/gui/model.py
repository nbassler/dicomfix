# File: model.py
# Purpose: Defines the application's data model, including both the data and the logic to manipulate it.

import logging

from dicomfix.dicom_handler import DicomFix

logger = logging.getLogger(__name__)


class MainModel:
    def __init__(self):

        self.settings = SettingsModel(self)
        self.dicomfix_list = None
        self.files_loaded = None
        self.files_selected = None
        self.anonymize = False
        self.approve = False
        self.curative_intent = False
        self.datetime = False
        self.reviewer = ""
        self.treatment_machine = "TR1"
        self.fields = None

    def load_dicoms(self, filenames):
        self.dicomfix_list = [DicomFix(fn) for fn in filenames]


class Field:
    def __init__(self):
        self.name = ""
        self.table_up = 0.0
        self.table_cranial = 0.0
        self.table_lateral = 0.0
        self.gantry = 0.0
        self.couch = 0.0
        self.nozzle = 0.0

    def field_from_dicomfix(self):
        pass


class SettingsModel:
    """
    This class contains a list model parameters which need to be retained when closing dicomfix.
    """

    def __init__(self, model):
        """
        """
        pass
