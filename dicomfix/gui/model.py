# File: model.py
# Purpose: Defines the application's data model, including both the data and the logic to manipulate it.

import logging

from dicomfix.dicom_handler import DicomFix

logger = logging.getLogger(__name__)


class MainModel:
    def __init__(self):

        self.settings = SettingsModel(self)
        self.dicomfix_list = None
        self.task_list = None

        self.files_loaded = None
        self.files_selected = None
        self._files_selected_last = None

        self.task_selected_last = None
        self.dicomfix_selected_last = None

    @property
    def files_selected_last(self):
        return self._files_selected_last

    @files_selected_last.setter
    def files_selected_last(self, filename):
        self._files_selected_last = filename
        self.dicomfix_selected_last = self.dfx_from_filename(filename)
        self.task_selected_last = self.task_from_filename(filename)

    def load_dicoms(self, filenames):
        """Load DICOM files and setup the field list for each Dicom file"""
        self.dicomfix_list = [DicomFix(fn) for fn in filenames]
        self.task_list = [Task(_dcm) for _dcm in self.dicomfix_list]

    def dfx_from_filename(self, path):
        """Return a pointer to DicomFix object with matching path."""
        for d in self.dicomfix_list:
            if path == d.filename:
                return d
        return None

    def task_from_filename(self, path):
        """Return a pointer to a Task object with matching path."""
        for t in self.task_list:
            if path == t.filename:
                return t
        return None

    def approve(self, val):
        print("Approve", val)


class Task:
    """List of stuff which will be done to the dicom files upon export"""
    def __init__(self, dfx):
        """Upon init, the current state of the original dicom file is loaded here"""

        self.filename = dfx.filename
        self.anonymized = False
        self.approved = False
        self.curative_intent = False

        d = dfx.dcm
        if d.ApprovalStatus == 'APPROVED':
            self.approved = True
        if d.PlanIntent == 'CURATIVE':
            self.curative_intent = True

        self.datetime = False
        self.reviewer = False

        self.fields = []
        for ion_beam in d.IonBeamSequence:
            field = Field()
            field.from_ion_beam(ion_beam)
            self.fields.append(field)

        self.treatment_machine = self.fields[-1].treatment_machine_name
        if self.treatment_machine == "TR1":
            self.treatment_machine_index = 0
        if self.treatment_machine == "TR2":
            self.treatment_machine_index = 1
        if self.treatment_machine == "TR3":
            self.treatment_machine_index = 2
        if self.treatment_machine == "TR4":
            self.treatment_machine_index = 3


class Field:
    def __init__(self):
        self.name = ""
        self.table_vertical = 0.0
        self.table_longitudinal = 0.0
        self.table_lateral = 0.0
        self.gantry = 0.0
        self.couch = 0.0
        self.snout_position = 0.0
        self.treatment_machine_name = ""
        self.treatment_machine_index = -1  # 0-3 for TR1-TR4

    def from_ion_beam(self, ion_beam):
        """Set local variables depending on given ion beam sequence"""
        self.name = ion_beam.BeamName
        self.treatment_machine_name = ion_beam.TreatmentMachineName
        # this model is in cm
        self.table_vertical = ion_beam.IonControlPointSequence[0].TableTopVerticalPosition * 0.1
        self.table_longitudinal = ion_beam.IonControlPointSequence[0].TableTopLongitudinalPosition * 0.1
        self.table_lateral = ion_beam.IonControlPointSequence[0].TableTopLateralPosition * 0.1
        self.snout_position = ion_beam.IonControlPointSequence[0].SnoutPosition * 0.1
        self.gantry = ion_beam.IonControlPointSequence[0].GantryAngle
        self.couch = ion_beam.IonControlPointSequence[0].PatientSupportAngle


class SettingsModel:
    """
    This class contains a list model parameters which need to be retained when closing dicomfix.
    """

    def __init__(self, model):
        """
        """
        pass
