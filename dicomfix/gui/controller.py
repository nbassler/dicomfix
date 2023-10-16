# File: controller.py
# Purpose: ties the viewer to the model

import logging

logger = logging.getLogger(__name__)


class MainController:
    """Controls interactions between the model and view."""
    def __init__(self, view, model):
        self.view = view
        self.model = model
        self.connect_signals()
        self.ui_active = True

    def connect_signals(self):
        self.view.open_dicom_callback = self.on_open_dicom
        self.view.selection_changed_callback = self.on_files_selected
        self.view.approved_state_changed_callback = self.on_approved_state_changed
        self.view.treatment_machine_changed_callback = self.on_treatment_machine_changed

    def on_open_dicom(self):
        print("Open DICOM triggered from controller.")
        files = self.view.open_dicom_files()
        self.model.load_dicoms(files[0])
        self.model.files_loaded = files[0]
        self.view.file_list_model.setStringList(files[0])

    def on_files_selected(self, selected, deselected):
        # Get all selected items
        indexes = self.view.ui.listView.selectionModel().selectedIndexes()

        # Extract the text (filename) of each selected item
        selected_files = [self.view.file_list_model.data(index) for index in indexes]
        self.model.files_selected = selected_files

        # update the last selected file pointer, which will be used to update the view
        if len(selected_files) > 0:
            self.model.files_selected_last = selected_files[-1]
        else:
            self.model.files_selected_last = None  # will also update dfx_selected_last and task_selected_last in model

        logger.debug(f"Selected files: {selected_files}")
        logger.debug(f"last: {self.model.files_selected_last}")

        self.update_ui()

    def on_approved_state_changed(self, is_checked):
        self.model.approve(is_checked)  # update model

    def on_treatment_machine_changed(self, tm_string):
        self.model.treatment_machine(tm_string)  # update model

    def update_ui(self):
        """Update all elements """
        ui = self.view.ui
        st = self.model.task_selected_last  # current state

        if st:
            if not self.ui_active:  # minimize activation only when it was previously deactivated
                self.ui_active = True
                self.activate_ui(self.ui_active)

            ui.checkBox_anonymize.setChecked(st.anonymized)
            ui.checkBox_approve.setChecked(st.approved)
            ui.checkBox_curative_intent.setChecked(st.curative_intent)
            ui.checkBox_newdatetime.setChecked(st.datetime)
            ui.checkBox_reviewername.setChecked(st.reviewer)
            # ui.comboBox_treatment_machine.setIndex(st.treatment_machine)

            for field in st.fields:
                ui.doubleSpinBox_table_vertical.setValue(field.table_vertical)
                ui.doubleSpinBox_table_longitudinal.setValue(field.table_longitudinal)
                ui.doubleSpinBox_table_lateral.setValue(field.table_lateral)
                ui.doubleSpinBox_gantry.setValue(field.gantry)
                ui.doubleSpinBox_couch.setValue(field.couch)
                ui.doubleSpinBox_nozzle_position.setValue(field.snout_position)
        else:  # in case st is not defined, that is, no files are selected in file list window
            self.ui_active = False
            self.activate_ui(self.ui_active)

    def activate_ui(self, active=True):
        """ Activation of the UI panel below the file list window"""
        ui = self.view.ui
        ui.checkBox_anonymize.setEnabled(active)
        ui.checkBox_approve.setEnabled(active)
        ui.checkBox_curative_intent.setEnabled(active)
        ui.checkBox_newdatetime.setEnabled(active)
        ui.checkBox_reviewername.setEnabled(active)
        ui.comboBox_treatment_machine.setEnabled(active)
        ui.comboBox_field.setEnabled(active)
        ui.doubleSpinBox_table_vertical.setEnabled(active)
        ui.doubleSpinBox_table_longitudinal.setEnabled(active)
        ui.doubleSpinBox_table_lateral.setEnabled(active)
        ui.doubleSpinBox_gantry.setEnabled(active)
        ui.doubleSpinBox_couch.setEnabled(active)
        ui.doubleSpinBox_nozzle_position.setEnabled(active)
        ui.pushButton_inspect_plan.setEnabled(active)
        ui.pushButton_export.setEnabled(active)
