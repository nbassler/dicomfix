"""
Main window for the dicomfix GUI.

Qt already provides the controller half of MVC through signals and slots, so this is one
QMainWindow whose methods are the slots, rather than a separate view and controller. What
stays separate is the model (dicomfix.gui.model), which imports no Qt at all and holds the
plan state and the command-line construction, so that logic is testable without PyQt6.

Edits are queued rather than applied. On export the queued settings are turned into a
dicomfix command line and run through the same parse_arguments() -> Config() ->
DicomUtil.modify() chain the CLI uses, so the GUI cannot behave differently from the CLI,
and the equivalent command can be shown to the user for provenance.
"""

from __future__ import annotations

import logging
import os
import sys

from PyQt6 import uic
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QWheelEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStatusBar,
)

from dicomfix.__version__ import __version__
from dicomfix.config import Config
from dicomfix.config_parser import parse_arguments
from dicomfix.dicomutil import DicomUtil
from dicomfix.gui.model import (
    RANGE_SHIFTERS,
    SNOUT_RETRACTED,
    TREATMENT_MACHINES,
    EditSettings,
    PlanModel,
    describe_unsupported,
    short_version,
)
from dicomfix.verify import PlanVerificationError

logger = logging.getLogger(__name__)

# Widgets that only make sense once a plan is open.
_EDIT_WIDGETS = (
    "checkBox_approve", "checkBox_curative_intent", "checkBox_newdatetime",
    "checkBox_reviewername", "checkBox_fix_raystation", "checkBox_fix_tr4",
    "comboBox_treatment_machine", "comboBox_field", "comboBox_range_shifter",
    "doubleSpinBox_table_vertical", "doubleSpinBox_table_longitudinal",
    # doubleSpinBox_couch is deliberately absent: it stays disabled even with a plan
    # open, because dicomfix cannot write PatientSupportAngle.
    "doubleSpinBox_table_lateral", "doubleSpinBox_gantry",
    "doubleSpinBox_nozzle_position", "doubleSpinBox_rescale_dose",
    "doubleSpinBox_rescale_factor", "spinBox_duplicate_fields",
    "pushButton_snout_retract", "pushButton_copy_to_all_fields",
    "pushButton_reset", "pushButton_export",
)

APP_NAME = "DicomFix"
ICON_FILE = "dicomfix.ico"

# One wheel scheme for every editable quantity: a plain notch steps by the box's own
# singleStep, Ctrl by ten times it (Qt's own behaviour, left alone), and Shift by a tenth
# (added below, since Qt ignores Shift). Only the base step differs per quantity.
#
# The factor is anchored a decade lower than the rest: it is dimensionless and sits near
# 1, so a step of 1.0 would double a plan in one notch.
# The table boxes get their tooltip rewritten per plan, so the axis description that
# lives on the paired label has to be folded back in each time. Hovering the box is what
# people actually do.
_TABLE_LABELS = {
    "doubleSpinBox_table_vertical": "label",
    "doubleSpinBox_table_longitudinal": "label_table_longitudinal",
    "doubleSpinBox_table_lateral": "label_lateral",
}

_WHEEL_STEPS = {
    "doubleSpinBox_table_vertical": 1.0,        # cm
    "doubleSpinBox_table_longitudinal": 1.0,    # cm
    "doubleSpinBox_table_lateral": 1.0,         # cm
    "doubleSpinBox_nozzle_position": 1.0,       # cm
    "doubleSpinBox_gantry": 1.0,                # degrees
    "doubleSpinBox_rescale_dose": 1.0,          # Gy(RBE)
    "doubleSpinBox_rescale_factor": 0.1,        # dimensionless
}


class FineWheelFilter(QObject):
    """Gives Shift+wheel a tenth-step on spin boxes, where Qt otherwise ignores Shift."""

    def eventFilter(self, a0, a1):
        if (isinstance(a1, QWheelEvent) and isinstance(a0, QDoubleSpinBox)
                and a1.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            notches = a1.angleDelta().y() / 120.0
            a0.setValue(a0.value() + notches * a0.singleStep() / 10.0)
            return True          # consume it, so Qt does not also apply its own step
        return False


def with_wheel_hint(tooltip, step):
    """Append the scroll-step hint to a tooltip, so it survives being rewritten."""
    hint = (f"Scroll steps by {step:g}; "
            f"Shift for {step / 10:g}, Ctrl for {step * 10:g}.")
    return f"{tooltip}\n{hint}" if tooltip else hint


def resource_path(name):
    """
    Locate a data file shipped alongside this module.

    PyInstaller's --onefile mode unpacks to a temporary directory recorded in
    sys._MEIPASS, so the path next to __file__ is not where the data lands. Without this
    the frozen build starts and then fails to find main_window.ui.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "dicomfix", "gui", name)
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), name)


class MainWindow(QMainWindow):
    """The whole GUI. Widgets are loaded onto self by uic, so they are plain attributes."""

    # uic.loadUi() attaches these at runtime, which a static type checker cannot see.
    # Annotating them without assigning gives Pylance the contract and working
    # completion, while leaving loadUi free to populate them. It also states, in one
    # place, exactly which widgets main_window.ui has to provide -- the same contract
    # tests/test_gui.py asserts at runtime.
    actionAbout: QAction
    actionExit: QAction
    actionOpen: QAction
    checkBox_anonymize: QCheckBox
    checkBox_approve: QCheckBox
    checkBox_curative_intent: QCheckBox
    checkBox_fix_raystation: QCheckBox
    checkBox_fix_tr4: QCheckBox
    checkBox_newdatetime: QCheckBox
    checkBox_reviewername: QCheckBox
    comboBox_field: QComboBox
    comboBox_range_shifter: QComboBox
    comboBox_treatment_machine: QComboBox
    doubleSpinBox_couch: QDoubleSpinBox
    doubleSpinBox_gantry: QDoubleSpinBox
    doubleSpinBox_nozzle_position: QDoubleSpinBox
    doubleSpinBox_rescale_dose: QDoubleSpinBox
    doubleSpinBox_rescale_factor: QDoubleSpinBox
    doubleSpinBox_table_lateral: QDoubleSpinBox
    doubleSpinBox_table_longitudinal: QDoubleSpinBox
    doubleSpinBox_table_vertical: QDoubleSpinBox
    label_5: QLabel
    label_treatment_machine: QLabel
    plainTextEdit_inspect: QPlainTextEdit
    pushButton_copy_to_all_fields: QPushButton
    pushButton_export: QPushButton
    pushButton_reset: QPushButton
    pushButton_snout_retract: QPushButton
    spinBox_duplicate_fields: QSpinBox
    statusbar: QStatusBar

    plan: PlanModel | None

    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("main_window.ui"), self)

        self.plan = None
        self.settings = EditSettings()
        self._loading = False        # suppresses edit signals while populating widgets
        self._linking = False        # guards the factor <-> dose link against feedback
        # Where the loaded plan's own range shifter sits in the combo. Not always its
        # RANGE_SHIFTERS index: an ID that list does not name is appended at the end.
        self._plan_shifter_index = 0
        # Held as an attribute: an event filter that goes out of scope stops filtering.
        self._fine_wheel = FineWheelFilter(self)

        self._set_title()
        self._set_icon()
        self._prepare_widgets()
        self._connect()
        self._set_editing_enabled(False)
        # Also here, not just on load: it is what writes the approve and curative
        # tooltips, and an empty window should still explain its controls.
        self._apply_scope_rules()
        self.setAcceptDrops(True)

    # -- drag and drop -------------------------------------------------------

    # The parameter is named a0 to match QWidget's signature; Qt's own naming, not ours.
    def dragEnterEvent(self, a0):
        """Accept a single local file; what it contains is checked on drop."""
        if a0 is None:
            return
        mime = a0.mimeData()
        if mime and mime.hasUrls() and len(mime.urls()) == 1 and mime.urls()[0].isLocalFile():
            a0.acceptProposedAction()

    def dropEvent(self, a0):
        """Open a dropped plan, refusing anything that is not an ion RTPLAN."""
        if a0 is None:
            return
        mime = a0.mimeData()
        if mime is None or not mime.hasUrls():
            return
        path = mime.urls()[0].toLocalFile()
        a0.acceptProposedAction()
        problem = describe_unsupported(path)
        if problem:
            QMessageBox.critical(self, "Cannot open this file",
                                 f"{os.path.basename(path)}\n\n{problem}")
            return
        self.load_plan(path)

    # -- setup ---------------------------------------------------------------

    def _set_title(self, filename=None):
        """Window title carries the app version and the open file."""
        title = f"{APP_NAME} (v{short_version()})"
        if filename:
            title += f" - {os.path.basename(filename)}"
        self.setWindowTitle(title)

    def _set_icon(self):
        """Icon for the title bar, taskbar and alt-tab.

        The frozen Windows build additionally embeds this file in the exe via
        PyInstaller's --icon, which is what Explorer shows; this call covers the running
        window on every platform.
        """
        path = resource_path(ICON_FILE)
        if os.path.exists(path):
            self.setWindowIcon(QIcon(path))
        else:
            logger.debug("window icon not found at %s", path)

    def _prepare_widgets(self):
        # dicomfix cannot write PatientSupportAngle, so the couch is shown greyed out
        # rather than offered as something that can be changed.
        self.doubleSpinBox_couch.setEnabled(False)
        self.doubleSpinBox_couch.setToolTip("Not implemented")
        self.label_5.setToolTip("Not implemented")

        # There is no anonymisation in DicomUtil; an inert checkbox is worse than none.
        self.checkBox_anonymize.setVisible(False)
        self.checkBox_reviewername.setVisible(False)

        self.plainTextEdit_inspect.setStyleSheet("font-family: monospace;")

        # Qt Designer defaults spin boxes to 0..99, too narrow for these quantities.
        self.doubleSpinBox_gantry.setRange(0.0, 360.0)
        self.doubleSpinBox_couch.setRange(-360.0, 360.0)
        for name in ("doubleSpinBox_table_vertical", "doubleSpinBox_table_longitudinal",
                     "doubleSpinBox_table_lateral"):
            getattr(self, name).setRange(-200.0, 200.0)
        # The snout travels from 0 to fully retracted; _show_field widens the top end if
        # a plan ever carries a value beyond it.
        self.doubleSpinBox_nozzle_position.setRange(0.0, SNOUT_RETRACTED)

        for name, step in _WHEEL_STEPS.items():
            box = getattr(self, name)
            box.setSingleStep(step)
            # Keep the box off zero. A zero factor or dose is not a rescale anyone
            # wants, and modify() gates on truthiness, so -rf=0 is silently skipped
            # rather than rejected. One step is the smallest value the box can show.
            if name in ("doubleSpinBox_rescale_factor", "doubleSpinBox_rescale_dose"):
                box.setMinimum(10 ** -box.decimals())
            box.installEventFilter(self._fine_wheel)
            box.setToolTip(with_wheel_hint(box.toolTip(), step))

    def _connect(self):
        self.actionOpen.triggered.connect(self.on_open)
        self.actionOpen.setShortcut(QKeySequence.StandardKey.Open)
        self.actionAbout.triggered.connect(self.on_about)
        # StandardKey.Quit is Ctrl+Q where the platform uses one; Windows relies on
        # Alt+F4, which Qt already provides.
        self.actionExit.setShortcut(QKeySequence.StandardKey.Quit)
        self.actionExit.triggered.connect(self.close)
        self.pushButton_export.setShortcut(QKeySequence.StandardKey.Save)
        self.pushButton_reset.clicked.connect(self.on_reset)
        self.comboBox_field.currentIndexChanged.connect(self.on_field_changed)
        self.pushButton_snout_retract.clicked.connect(self.on_retract_snout)
        self.pushButton_copy_to_all_fields.clicked.connect(self.on_copy_to_all_fields)
        self.pushButton_export.clicked.connect(self.on_export)

        # Rescale factor and prescribed dose are two views of one quantity, so each
        # updates the other. Only the factor is ever exported: rescale_plan() picks -rd
        # over -rf when both are given, so emitting both would silently ignore one.
        self.doubleSpinBox_rescale_factor.valueChanged.connect(self.on_factor_changed)
        self.doubleSpinBox_rescale_dose.valueChanged.connect(self.on_dose_changed)
        # valueChanged alone is not enough. The dose box is coarser than the factor, so
        # typing a dose the box is already showing emits nothing, and the factor would
        # keep a value the user has just overridden -- e.g. factor 1.004 on a 1 Gy plan
        # displays as 1.00, and retyping "1.00" would silently still export 1.004.
        # editingFinished fires regardless, and isModified() tells a keystroke from a
        # programmatic setValue, so focus alone does not clobber a deliberate factor.
        self.doubleSpinBox_rescale_dose.editingFinished.connect(self.on_dose_typed)

        self.comboBox_treatment_machine.currentIndexChanged.connect(self.on_edit_changed)
        self.comboBox_range_shifter.currentIndexChanged.connect(self.on_edit_changed)
        self.spinBox_duplicate_fields.valueChanged.connect(self.on_edit_changed)
        for name in ("doubleSpinBox_gantry", "doubleSpinBox_table_vertical",
                     "doubleSpinBox_table_longitudinal", "doubleSpinBox_table_lateral",
                     "doubleSpinBox_nozzle_position"):
            getattr(self, name).valueChanged.connect(self.on_edit_changed)
        for name in ("checkBox_approve", "checkBox_curative_intent",
                     "checkBox_newdatetime", "checkBox_fix_raystation", "checkBox_fix_tr4"):
            getattr(self, name).toggled.connect(self.on_edit_changed)

    def _set_editing_enabled(self, enabled):
        for name in _EDIT_WIDGETS:
            getattr(self, name).setEnabled(enabled)

    def _apply_scope_rules(self):
        """Disable controls whose operation dicomfix cannot perform on this plan.

        Called after _set_editing_enabled(True), which would otherwise re-enable them.
        """
        # Both of these operations are one-way: DicomUtil can set APPROVED and CURATIVE
        # but has nothing to undo them. Where the plan is already in that state the box
        # is shown ticked and disabled, rather than silently ignoring clicks.
        for widget_name, already, done, todo in (
            ("checkBox_approve", self.plan is not None and self.plan.approved,
             "This plan is already approved; dicomfix cannot un-approve it.",
             "Set the plan's approval status to APPROVED."),
            ("checkBox_curative_intent",
             self.plan is not None and self.plan.curative_intent,
             "This plan's intent is already CURATIVE; dicomfix cannot unset it.",
             "Set the plan intent to CURATIVE."),
        ):
            box = getattr(self, widget_name)
            box.setChecked(already or box.isChecked())
            box.setEnabled(not already)
            box.setToolTip(done if already else todo)

    # -- loading -------------------------------------------------------------

    def on_open(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open DICOM plan", os.path.expanduser("~"),
            "DICOM plans (*.dcm);;All files (*)")
        if not filename:
            return
        self.load_plan(filename)

    def load_plan(self, filename):
        """Open a plan and populate the widgets. Separate from on_open so tests can call it."""
        try:
            self.plan = PlanModel(filename)
        except Exception as exc:                       # unreadable file, or not an ion plan
            QMessageBox.critical(self, "Could not open plan", f"{filename}\n\n{exc}")
            return False

        self.settings = EditSettings(n_fields=len(self.plan.fields))
        self._set_title(filename)
        self._populate()
        self._refresh_inspect()
        self._set_editing_enabled(True)
        self._apply_scope_rules()
        self.statusbar.showMessage(
            f"Loaded {os.path.basename(filename)} ({len(self.plan.fields)} field(s))")
        return True

    def _refresh_inspect(self):
        """Show the plan summary, the same text the CLI's -i prints."""
        assert self.plan is not None, "a plan must be loaded"
        try:
            self.plainTextEdit_inspect.setPlainText(self.plan.inspect())
        except Exception as exc:
            self.plainTextEdit_inspect.setPlainText(f"Could not inspect this plan:\n\n{exc}")

    def _populate(self):
        """Fill every widget from the loaded plan, without queueing any edit."""
        assert self.plan is not None, "a plan must be loaded"
        self._loading = True
        try:
            self.comboBox_field.clear()
            self.comboBox_field.addItems(
                [f.name or f"Field {i + 1}" for i, f in enumerate(self.plan.fields)])
            self.comboBox_field.setCurrentIndex(0)

            self.checkBox_approve.setChecked(self.plan.approved)
            self.checkBox_curative_intent.setChecked(self.plan.curative_intent)
            for name in ("checkBox_newdatetime", "checkBox_fix_raystation",
                         "checkBox_fix_tr4"):
                getattr(self, name).setChecked(False)

            # Rebuilt each time, so a machine carried in from a previously loaded plan
            # cannot linger in the list.
            self.comboBox_treatment_machine.clear()
            self.comboBox_treatment_machine.addItems(TREATMENT_MACHINES)
            machine_index = self.plan.treatment_machine_index
            if machine_index < 0 and self.plan.treatment_machine:
                # The plan names a machine we do not list. Offer it rather than showing a
                # blank combo: blank hides which machine the plan uses, and the moment the
                # user opens the list there is no way back to the plan's own value.
                self.comboBox_treatment_machine.addItem(self.plan.treatment_machine)
                machine_index = self.comboBox_treatment_machine.count() - 1
            # Stays -1 only when the plan names no machine at all, where any selection
            # would queue a change the user did not ask for.
            self.comboBox_treatment_machine.setCurrentIndex(machine_index)

            # Same treatment as the machine combo: a plan may carry a range shifter this
            # list does not name, and collapsing it to "None" would tell the user there
            # is nothing to remove -- so selecting "None" would queue no change and the
            # shifter would survive the export. Offer the real ID instead.
            self.comboBox_range_shifter.clear()
            self.comboBox_range_shifter.addItems(RANGE_SHIFTERS)
            shifter_index = self.plan.range_shifter_index
            if shifter_index < 0:
                self.comboBox_range_shifter.addItem(self.plan.range_shifter_id)
                shifter_index = self.comboBox_range_shifter.count() - 1
            self.comboBox_range_shifter.setCurrentIndex(shifter_index)
            self._plan_shifter_index = shifter_index
            self.spinBox_duplicate_fields.setValue(1)

            # Factor 1.0 is "no rescaling", so the dose starts at the plan's own value.
            self.doubleSpinBox_rescale_factor.setValue(1.0)
            dose = self.plan.prescribed_dose
            if dose:
                self.doubleSpinBox_rescale_dose.setValue(dose)
                self.doubleSpinBox_rescale_dose.setEnabled(True)
                self.doubleSpinBox_rescale_dose.setToolTip(with_wheel_hint(
                    "Dose after rescaling. Linked to the factor above.",
                    _WHEEL_STEPS["doubleSpinBox_rescale_dose"]))
            else:
                # Nothing to scale from, so only the factor is meaningful here.
                self.doubleSpinBox_rescale_dose.setEnabled(False)
                self.doubleSpinBox_rescale_dose.setToolTip(
                    "This plan carries no prescription or beam dose to scale from, so "
                    "only the factor above can be used.")

            self._show_field(0)
        finally:
            self._loading = False

    def _show_field(self, index):
        """Show one field. Gantry is per field; table and snout are plan-wide."""
        assert self.plan is not None, "a plan must be loaded"
        field = self.plan.fields[index]
        # Two things the table boxes have to be honest about, despite sitting in the
        # per-field panel: RayStation leaves them empty (issue #37), and dicomfix's -tp
        # writes one value to every field, so editing them is never per-field.
        if not field.table_is_set:
            hint = "Not set in this plan - entering a value will set it for every field."
        elif self.plan.table_positions_differ:
            hint = ("WARNING: this plan's fields have different table positions, but "
                    "setting the table applies one value to all of them.")
        else:
            hint = "Applies to every field."
        for name, label_name in _TABLE_LABELS.items():
            axis = getattr(self, label_name).toolTip()
            getattr(self, name).setToolTip(
                with_wheel_hint(f"{axis}\n{hint}" if axis else hint, _WHEEL_STEPS[name]))

        # Widen the snout range rather than clamp: a value the spin box cannot represent
        # would be silently rewritten to the cap, queueing an -sp edit nobody asked for.
        self.doubleSpinBox_nozzle_position.setMaximum(
            max(SNOUT_RETRACTED, field.snout_position))

        self.doubleSpinBox_gantry.setValue(field.gantry)
        self.doubleSpinBox_couch.setValue(field.couch)
        self.doubleSpinBox_table_vertical.setValue(field.table_vertical)
        self.doubleSpinBox_table_longitudinal.setValue(field.table_longitudinal)
        self.doubleSpinBox_table_lateral.setValue(field.table_lateral)
        self.doubleSpinBox_nozzle_position.setValue(field.snout_position)

    def on_field_changed(self, index):
        if self._loading or self.plan is None or index < 0:
            return
        self._loading = True
        try:
            self._show_field(index)
            # Show any gantry edit already queued for this field.
            if self.settings.gantry_angles is not None:
                self.doubleSpinBox_gantry.setValue(self.settings.gantry_angles[index])
        finally:
            self._loading = False

    # -- editing -------------------------------------------------------------

    def on_factor_changed(self, factor):
        """Factor edited: show the dose it produces."""
        if self._linking or self.plan is None:
            return
        base = self.plan.prescribed_dose
        if base:
            self._linking = True
            try:
                self.doubleSpinBox_rescale_dose.setValue(base * factor)
            finally:
                self._linking = False
        self.on_edit_changed()

    def on_dose_typed(self):
        """Committed a typed dose, whether or not the displayed value changed.

        Guarantees that whichever box was edited last is the one that wins, even when the
        dose box cannot represent the difference the factor holds.
        """
        line = self.doubleSpinBox_rescale_dose.lineEdit()
        if line is None or not line.isModified():
            return          # focus passed through without an edit; leave the factor alone
        line.setModified(False)
        self.on_dose_changed(self.doubleSpinBox_rescale_dose.value())

    def on_dose_changed(self, dose):
        """Dose edited: back out the factor that reaches it."""
        if self._linking or self.plan is None:
            return
        base = self.plan.prescribed_dose
        if base:
            self._linking = True
            try:
                self.doubleSpinBox_rescale_factor.setValue(dose / base)
            finally:
                self._linking = False
        self.on_edit_changed()

    def on_edit_changed(self, *_):
        """Re-derive the queued edits from the widgets whenever one changes."""
        if self._loading or self.plan is None:
            return
        s = self.settings
        field_index = max(0, self.comboBox_field.currentIndex())
        field = self.plan.fields[field_index]

        # Only queue what actually differs from the plan, so an untouched control
        # never adds an option to the command line.
        s.approve = self.checkBox_approve.isChecked() and not self.plan.approved
        s.intent_curative = (self.checkBox_curative_intent.isChecked()
                             and not self.plan.curative_intent)
        s.date = self.checkBox_newdatetime.isChecked()
        s.fix_raystation = self.checkBox_fix_raystation.isChecked()
        s.wizard_tr4 = self.checkBox_fix_tr4.isChecked()

        machine = self.comboBox_treatment_machine.currentText()
        s.treatment_machine = machine if machine != self.plan.treatment_machine else None

        # Compared against the plan's position in this combo, not its RANGE_SHIFTERS
        # index: an unlisted ID is appended past the end of that list, so only the
        # entries the -rh option understands can ever be queued.
        rs_index = self.comboBox_range_shifter.currentIndex()
        s.range_shifter = (RANGE_SHIFTERS[rs_index]
                           if rs_index != self._plan_shifter_index else None)

        # Only the factor is exported. The dose box is the same quantity in other units,
        # and rescale_plan() would silently drop -rf if -rd were present alongside it.
        factor = self.doubleSpinBox_rescale_factor.value()
        s.rescale_dose = None
        s.rescale_factor = factor if factor != 1.0 else None

        duplicate = self.spinBox_duplicate_fields.value()
        s.duplicate_fields = duplicate if duplicate > 1 else None

        # Gantry is per field: start from the plan's angles, override the one on screen.
        plan_angles = [f.gantry for f in self.plan.fields]
        angles = list(s.gantry_angles or plan_angles)
        angles[field_index] = self.doubleSpinBox_gantry.value()
        s.gantry_angles = angles if angles != plan_angles else None

        table = (self.doubleSpinBox_table_vertical.value(),
                 self.doubleSpinBox_table_longitudinal.value(),
                 self.doubleSpinBox_table_lateral.value())
        s.table_position = table if table != (field.table_vertical,
                                              field.table_longitudinal,
                                              field.table_lateral) else None

        snout = self.doubleSpinBox_nozzle_position.value()
        s.snout_position = snout if snout != field.snout_position else None

        self._show_command()

    def _show_command(self):
        """Show the equivalent command line, so a GUI edit can be reproduced or logged."""
        if self.plan is None:
            return
        if self.settings.is_empty():
            self.statusbar.showMessage("No changes queued")
        else:
            self.statusbar.showMessage(
                self.settings.to_command(os.path.basename(self.plan.filename), "output.dcm"))

    # -- actions -------------------------------------------------------------

    def on_retract_snout(self):
        """Snap the snout to its fully retracted position, the common case for QA setups."""
        self.doubleSpinBox_nozzle_position.setValue(SNOUT_RETRACTED)

    def on_reset(self):
        """Discard queued edits and put every control back to the plan's own values."""
        if self.plan is None:
            return
        self.settings.clear()
        self._populate()
        self._apply_scope_rules()
        # After an export the pane shows the exported plan. Reset returns the controls to
        # the loaded plan, so the pane has to follow or the two describe different plans.
        self._refresh_inspect()
        self.statusbar.showMessage("Edits reset", 4000)

    def on_copy_to_all_fields(self):
        """
        Give every field the gantry angle currently shown.

        Gantry is the only per-field value dicomfix can set. Table position, snout,
        treatment machine and range shifter are already applied to all fields, so there
        is nothing else on this panel to copy.
        """
        if self.plan is None:
            return
        gantry = self.doubleSpinBox_gantry.value()
        self.settings.gantry_angles = [gantry] * len(self.plan.fields)
        self.on_edit_changed()
        n = len(self.plan.fields)
        self.statusbar.showMessage(f"Gantry {gantry:g} deg applied to all {n} field(s)", 4000)

    def on_about(self):
        """Show the exact build, including the commit the version was derived from."""
        import pydicom
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME} {short_version()}</b>"
            f"<p>Modify and inspect DICOM proton therapy treatment plans.</p>"
            f"<p><tt>{__version__}</tt><br>"
            f"<small>The part after '+' identifies the exact commit this was built from."
            f"</small></p>"
            f"<p>Python {sys.version.split()[0]}<br>"
            f"PyQt {PYQT_VERSION_STR}, Qt {QT_VERSION_STR}<br>"
            f"pydicom {pydicom.__version__}</p>"
            f"<p><a href='https://github.com/nbassler/dicomfix'>"
            f"github.com/nbassler/dicomfix</a></p>")

    def on_export(self):
        if self.plan is None:
            return
        suggested = os.path.join(os.path.dirname(self.plan.filename),
                                 "modified_" + os.path.basename(self.plan.filename))
        output, _ = QFileDialog.getSaveFileName(
            self, "Export DICOM plan", suggested, "DICOM plans (*.dcm);;All files (*)")
        if not output:
            return
        if self.export_to(output):
            QMessageBox.information(
                self, "Exported",
                f"Written to:\n{output}\n\nEquivalent command:\n"
                f"{self.settings.to_command(self.plan.filename, output)}")

    def export_to(self, output):
        """
        Apply the queued edits and write the plan. Separate from on_export so tests
        can drive it without a file dialog.

        Returns:
            bool: True if the plan was written.
        """
        if self.plan is None:
            return False

        # Setting the table replaces it on every field. If they currently differ, that
        # discards information, so ask rather than doing it quietly.
        if self.settings.table_position is not None and self.plan.table_positions_differ:
            answer = QMessageBox.question(
                self, "Table position differs between fields",
                f"This plan's {len(self.plan.fields)} fields have different table "
                f"positions.\n\nExporting will give every field the same position:\n"
                f"  vertical {self.settings.table_position[0]:g} cm, "
                f"longitudinal {self.settings.table_position[1]:g} cm, "
                f"lateral {self.settings.table_position[2]:g} cm\n\n"
                f"The other fields' positions will be lost. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                self.statusbar.showMessage("Export cancelled", 4000)
                return False

        args = self.settings.to_args(self.plan.filename, output)
        logger.info("GUI export: dicomfix %s", " ".join(args))
        try:
            try:
                # argparse exits the process on a bad argument, which would kill the GUI.
                parsed = parse_arguments(args)
            except SystemExit as exc:
                raise ValueError(f"Invalid options: {' '.join(args)}") from exc
            plan = DicomUtil(self.plan.filename)
            plan.modify(Config(parsed))
            plan.save(output)
        except PlanVerificationError as exc:
            QMessageBox.critical(self, "Plan verification failed - plan NOT written",
                                 str(exc))
            return False
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return False

        # Show what was actually written, not the plan still loaded for editing.
        try:
            self.plainTextEdit_inspect.setPlainText(
                f"--- exported: {output} ---\n\n" + PlanModel(output).inspect())
        except Exception as exc:
            logger.debug("could not inspect the exported plan: %s", exc)

        self.statusbar.showMessage(f"Exported {os.path.basename(output)}")
        return True
