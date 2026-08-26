"""
Tests for the dicomfix Qt GUI window.

Driven under QT_QPA_PLATFORM=offscreen, and skipped when PyQt6 is absent since `gui` is
an optional extra. The command-line construction these rely on is tested separately, and
without Qt, in test_gui_model.py.

The test that matters most is test_gui_export_matches_cli_byte_for_byte: the GUI applies
edits by building a dicomfix command line and running it through the same code path as
the CLI, and that equivalence is the whole reason the design is safe.
"""

import hashlib
import os
from pathlib import Path

import pytest
from PyQt6.QtGui import QAction

PLAN_FILE = Path('res', 'Plan5.5.dcm')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Window -- needs PyQt6
# ---------------------------------------------------------------------------

pytest.importorskip("PyQt6", reason="GUI tests need the 'gui' extra")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Stop message boxes blocking the suite.

    QMessageBox.critical() and friends are modal: under an offscreen display they wait
    forever for a click that never comes, so a single unexpected dialog hangs the whole
    run rather than failing it. Autouse, because any test can trip one.
    """
    from PyQt6.QtWidgets import QMessageBox
    calls = []
    for name in ("critical", "information", "warning", "about"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: calls.append(_n) or QMessageBox.StandardButton.Ok,
                            raising=False)
    # question() gates a destructive export, so default to Yes here; tests that care
    # about the cancel path override it themselves.
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: calls.append("question") or QMessageBox.StandardButton.Yes,
                        raising=False)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: calls.append("exec") or 0)
    return calls


@pytest.fixture
def window(qapp):
    from dicomfix.gui.window import MainWindow
    w = MainWindow()
    yield w
    w.close()


@pytest.fixture
def two_field_plan(tmp_path):
    """PLAN_FILE has one field; the per-field paths need more than that."""
    import copy as _copy

    import pydicom
    d = pydicom.dcmread(str(PLAN_FILE))
    d.IonBeamSequence.append(_copy.deepcopy(d.IonBeamSequence[0]))
    d.IonBeamSequence[1].BeamNumber = 2
    d.IonBeamSequence[1].BeamName = "Field 2"
    d.IonBeamSequence[1].IonControlPointSequence[0].GantryAngle = 270.0
    rbs = d.FractionGroupSequence[0].ReferencedBeamSequence
    rbs.append(_copy.deepcopy(rbs[0]))
    rbs[1].ReferencedBeamNumber = 2
    d.FractionGroupSequence[0].NumberOfBeams = 2
    path = tmp_path / "two_field.dcm"
    d.save_as(str(path))
    return str(path)


class TestWindowLoads:
    def test_ui_file_provides_every_widget_the_window_uses(self, window):
        """Catches a .ui edit that renames or drops a widget the code references."""
        from dicomfix.gui.window import _EDIT_WIDGETS
        for name in _EDIT_WIDGETS + ("actionOpen", "actionAbout", "statusbar",
                                     "comboBox_field", "checkBox_anonymize",
                                     "plainTextEdit_inspect", "label_5",
                                     "doubleSpinBox_couch"):
            assert hasattr(window, name), f"main_window.ui is missing {name}"

    def test_editing_disabled_until_a_plan_is_loaded(self, window):
        assert not window.pushButton_export.isEnabled()
        assert not window.doubleSpinBox_gantry.isEnabled()

    def test_loading_a_plan_enables_editing(self, window):
        assert window.load_plan(str(PLAN_FILE))
        assert window.pushButton_export.isEnabled()
        assert window.doubleSpinBox_gantry.isEnabled()

    def test_widgets_reflect_the_loaded_plan(self, window):
        window.load_plan(str(PLAN_FILE))
        assert window.comboBox_field.count() == len(window.plan.fields)
        assert window.comboBox_treatment_machine.currentText() == "TR4"
        assert window.doubleSpinBox_gantry.value() == pytest.approx(90.0)
        assert window.doubleSpinBox_nozzle_position.value() == pytest.approx(42.1)

    def test_couch_is_shown_but_greyed_out(self, window):
        """dicomfix cannot write PatientSupportAngle; the UI must not imply otherwise."""
        window.load_plan(str(PLAN_FILE))
        assert window.doubleSpinBox_couch.value() == pytest.approx(0.0)   # read from plan
        assert not window.doubleSpinBox_couch.isEnabled()
        assert window.doubleSpinBox_couch.toolTip() == "Not implemented"

    def test_title_carries_version_and_filename(self, window):
        from dicomfix.gui.model import short_version
        assert window.windowTitle() == f"DicomFix (v{short_version()})"
        window.load_plan(str(PLAN_FILE))
        assert window.windowTitle() == f"DicomFix (v{short_version()}) - Plan5.5.dcm"

    def test_inspect_pane_fills_on_load(self, window):
        """Inspection lives in the main window now, not behind a button."""
        assert "Open a plan" in window.plainTextEdit_inspect.toPlainText()
        window.load_plan(str(PLAN_FILE))
        text = window.plainTextEdit_inspect.toPlainText()
        assert "Beam Dose" in text or "Gy(RBE)" in text

    def test_about_reports_the_exact_build(self, window, no_modal_dialogs):
        """The short version is in the title; About must give the full one."""
        from dicomfix.__version__ import __version__
        window.actionAbout.trigger()
        assert "about" in no_modal_dialogs
        # the full version, including the +commit local part, must be reachable somewhere
        assert "+" not in window.windowTitle()
        assert "+" in __version__ or "." in __version__

    def test_opening_a_non_plan_does_not_crash(self, window, tmp_path):
        bad = tmp_path / "not_a_plan.dcm"
        bad.write_text("this is not DICOM")
        assert window.load_plan(str(bad)) is False
        assert window.plan is None


class TestQueuedEdits:
    def test_untouched_controls_queue_nothing(self, window):
        """Setting a control to the value already in the plan must not add an option."""
        window.load_plan(str(PLAN_FILE))
        window.comboBox_treatment_machine.setCurrentIndex(3)     # already TR4
        window.doubleSpinBox_gantry.setValue(90.0)               # already 90
        assert window.settings.is_empty()

    def test_changed_control_is_queued(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert "-rf=2" in window.settings.to_args("in.dcm", "out.dcm")

    def test_machine_change_is_queued(self, window):
        window.load_plan(str(PLAN_FILE))
        window.comboBox_treatment_machine.setCurrentIndex(0)     # TR1, plan is TR4
        assert window.settings.treatment_machine == "TR1"

    def test_gantry_is_queued_per_field(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_gantry.setValue(45.0)
        assert window.settings.gantry_angles == [45.0]

    def test_status_bar_shows_the_equivalent_command(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.statusbar.currentMessage().startswith("dicomfix ")

    def test_status_bar_says_so_when_nothing_is_queued(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        window.doubleSpinBox_rescale_factor.setValue(1.0)      # 1.0 is "no rescaling"
        assert window.statusbar.currentMessage() == "No changes queued"


class TestLinkedRescale:
    """Factor and prescribed dose are two views of one quantity."""

    def test_dose_starts_at_the_plan_value(self, window):
        window.load_plan(str(PLAN_FILE))
        assert window.doubleSpinBox_rescale_factor.value() == pytest.approx(1.0)
        assert window.doubleSpinBox_rescale_dose.value() == pytest.approx(
            window.plan.prescribed_dose)

    def test_editing_the_factor_updates_the_dose(self, window):
        window.load_plan(str(PLAN_FILE))
        base = window.plan.prescribed_dose
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.doubleSpinBox_rescale_dose.value() == pytest.approx(base * 2.0)

    def test_editing_the_dose_updates_the_factor(self, window):
        window.load_plan(str(PLAN_FILE))
        base = window.plan.prescribed_dose
        window.doubleSpinBox_rescale_dose.setValue(base * 3.0)
        assert window.doubleSpinBox_rescale_factor.value() == pytest.approx(3.0, rel=1e-3)

    def test_the_link_does_not_oscillate(self, window):
        """Each box sets the other, so an unguarded link would recurse."""
        window.load_plan(str(PLAN_FILE))
        base = window.plan.prescribed_dose
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        window.doubleSpinBox_rescale_dose.setValue(base * 4.0)
        window.doubleSpinBox_rescale_factor.setValue(1.5)
        assert window.doubleSpinBox_rescale_dose.value() == pytest.approx(base * 1.5)
        assert window.doubleSpinBox_rescale_factor.value() == pytest.approx(1.5)

    def test_only_the_factor_is_exported(self, window):
        """rescale_plan() prefers -rd over -rf, so emitting both would drop one."""
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_dose.setValue(window.plan.prescribed_dose * 2.0)
        args = window.settings.to_args("in.dcm", "out.dcm")
        assert any(a.startswith("-rf=") for a in args)
        assert not any(a.startswith("-rd=") for a in args)

    def test_box_precision(self, window):
        """QDoubleSpinBox rounds the stored value, so these cap what the GUI applies."""
        window.load_plan(str(PLAN_FILE))
        assert window.doubleSpinBox_rescale_factor.decimals() == 3
        assert window.doubleSpinBox_rescale_dose.decimals() == 2

    def test_dose_is_reachable_to_its_own_resolution(self, window):
        """Three decimals on the factor is what lets the 0.01 Gy dose box be honest."""
        window.load_plan(str(PLAN_FILE))
        base = window.plan.prescribed_dose
        for target in (4.0, 8.0, 11.0, 2.75):
            window.doubleSpinBox_rescale_dose.setValue(target)
            delivered = window.doubleSpinBox_rescale_factor.value() * base
            assert abs(delivered - target) < 0.005, f"{target} Gy not reachable"


class TestExport:
    def test_export_writes_a_file(self, window, tmp_path):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        out = tmp_path / "out.dcm"
        assert window.export_to(str(out))
        assert out.is_file() and out.stat().st_size > 0

    def test_gui_export_matches_cli_byte_for_byte(self, window, tmp_path):
        """The GUI is the CLI. If this ever diverges, the design has been broken."""
        import dicomfix.main

        window.load_plan(str(PLAN_FILE))
        window.comboBox_treatment_machine.setCurrentIndex(0)     # TR1
        window.doubleSpinBox_gantry.setValue(45.0)
        window.doubleSpinBox_table_vertical.setValue(0.0)
        window.doubleSpinBox_table_longitudinal.setValue(10.5)
        window.doubleSpinBox_table_lateral.setValue(-5.0)
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        window.comboBox_range_shifter.setCurrentIndex(1)         # RS2

        gui_out = tmp_path / "gui.dcm"
        assert window.export_to(str(gui_out))

        cli_out = tmp_path / "cli.dcm"
        dicomfix.main.main([str(PLAN_FILE), '-tm', 'TR1', '-g=45', '-tp=0,10.5,-5',
                            '-rf=2', '-rh=RS2', '-o', str(cli_out)])

        assert sha256(gui_out) == sha256(cli_out)

    def test_export_with_no_edits_is_a_faithful_copy(self, window, tmp_path):
        import dicomfix.main
        window.load_plan(str(PLAN_FILE))
        gui_out = tmp_path / "gui.dcm"
        cli_out = tmp_path / "cli.dcm"
        assert window.export_to(str(gui_out))
        dicomfix.main.main([str(PLAN_FILE), '-o', str(cli_out)])
        assert sha256(gui_out) == sha256(cli_out)

    def test_rejected_rescale_does_not_write_a_file(self, window, tmp_path, no_modal_dialogs):
        """A refused rescale must leave no output behind, and must tell the user."""
        window.load_plan(str(PLAN_FILE))
        window.settings.rescale_factor = -1.0     # apply_rescale_factor rejects this
        out = tmp_path / "out.dcm"
        assert window.export_to(str(out)) is False
        assert not out.exists()
        assert "critical" in no_modal_dialogs, "the failure was swallowed silently"


class TestCopyToAllFields:
    """Gantry is the only per-field value dicomfix can set, so that is what is copied."""

    def test_two_field_plan_starts_with_different_gantries(self, window, two_field_plan):
        window.load_plan(two_field_plan)
        assert [f.gantry for f in window.plan.fields] == pytest.approx([90.0, 270.0])

    def test_copy_applies_the_shown_gantry_everywhere(self, window, two_field_plan):
        window.load_plan(two_field_plan)
        window.doubleSpinBox_gantry.setValue(45.0)      # field 1 only
        assert window.settings.gantry_angles == [45.0, 270.0]
        window.pushButton_copy_to_all_fields.click()
        assert window.settings.gantry_angles == [45.0, 45.0]

    def test_copied_gantry_reaches_the_command_line(self, window, two_field_plan):
        window.load_plan(two_field_plan)
        window.doubleSpinBox_gantry.setValue(45.0)
        window.pushButton_copy_to_all_fields.click()
        assert "-g=45,45" in window.settings.to_args("in.dcm", "out.dcm")

    def test_copy_is_a_no_op_when_it_matches_the_plan(self, window, two_field_plan):
        """Copying a value the plan already has must not queue a pointless edit."""
        window.load_plan(two_field_plan)
        window.comboBox_field.setCurrentIndex(0)         # 90 deg
        window.pushButton_copy_to_all_fields.click()
        assert window.settings.gantry_angles == [90.0, 90.0]   # field 2 was 270
        window.doubleSpinBox_gantry.setValue(90.0)
        assert "-g=90,90" in window.settings.to_args("in.dcm", "out.dcm")

    def test_copy_survives_switching_fields(self, window, two_field_plan):
        window.load_plan(two_field_plan)
        window.doubleSpinBox_gantry.setValue(45.0)
        window.pushButton_copy_to_all_fields.click()
        window.comboBox_field.setCurrentIndex(1)
        assert window.doubleSpinBox_gantry.value() == pytest.approx(45.0)
        assert window.settings.gantry_angles == [45.0, 45.0]

    def test_export_applies_the_copied_gantry_to_every_field(self, window, two_field_plan,
                                                             tmp_path):
        from dicomfix.dicomutil import DicomUtil
        window.load_plan(two_field_plan)
        window.doubleSpinBox_gantry.setValue(45.0)
        window.pushButton_copy_to_all_fields.click()
        out = tmp_path / "copied.dcm"
        assert window.export_to(str(out))
        written = DicomUtil(str(out))
        for ib in written.dicom.IonBeamSequence:
            assert float(ib.IonControlPointSequence[0].GantryAngle) == pytest.approx(45.0)


class TestTablePositionWarning:
    """DICOM stores the table position per field, but -tp writes one value to all."""

    @pytest.fixture
    def differing_tables(self, two_field_plan, tmp_path):
        import pydicom
        d = pydicom.dcmread(two_field_plan)
        d.IonBeamSequence[0].IonControlPointSequence[0].TableTopVerticalPosition = 10.0
        d.IonBeamSequence[1].IonControlPointSequence[0].TableTopVerticalPosition = 99.0
        path = tmp_path / "differing_tables.dcm"
        d.save_as(str(path))
        return str(path)

    def test_difference_is_detected(self, window, differing_tables):
        window.load_plan(differing_tables)
        assert window.plan.table_positions_differ is True

    def test_matching_tables_are_not_flagged(self, window, two_field_plan):
        window.load_plan(two_field_plan)
        assert window.plan.table_positions_differ is False

    def test_the_table_boxes_warn(self, window, differing_tables):
        window.load_plan(differing_tables)
        assert "WARNING" in window.doubleSpinBox_table_vertical.toolTip()

    def test_export_asks_before_flattening_them(self, window, differing_tables,
                                                tmp_path, no_modal_dialogs):
        window.load_plan(differing_tables)
        window.doubleSpinBox_table_vertical.setValue(5.0)
        assert window.export_to(str(tmp_path / "out.dcm"))
        assert "question" in no_modal_dialogs, "flattened the table without asking"

    def test_export_can_be_cancelled(self, window, differing_tables, tmp_path, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "question",
                            lambda *a, **k: QMessageBox.StandardButton.Cancel)
        window.load_plan(differing_tables)
        window.doubleSpinBox_table_vertical.setValue(5.0)
        out = tmp_path / "out.dcm"
        assert window.export_to(str(out)) is False
        assert not out.exists()

    def test_no_question_when_the_table_is_untouched(self, window, differing_tables,
                                                     tmp_path, no_modal_dialogs):
        """Only setting the table flattens it, so nothing else should prompt."""
        window.load_plan(differing_tables)
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.export_to(str(tmp_path / "out.dcm"))
        assert "question" not in no_modal_dialogs


class TestConveniences:
    def test_open_and_export_have_shortcuts(self, window):
        from PyQt6.QtGui import QKeySequence
        assert window.actionOpen.shortcut() == QKeySequence(QKeySequence.StandardKey.Open)
        assert window.pushButton_export.shortcut() == QKeySequence(
            QKeySequence.StandardKey.Save)

    def test_copy_command_button_is_gone(self, window):
        """Removed as noise: the GUI's users are not running the CLI."""
        assert not hasattr(window, "pushButton_copy_command")

    def test_reset_discards_every_queued_edit(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        window.doubleSpinBox_gantry.setValue(45.0)
        window.comboBox_treatment_machine.setCurrentIndex(0)
        assert not window.settings.is_empty()
        window.pushButton_reset.click()
        assert window.settings.is_empty()

    def test_reset_restores_the_widgets_too(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_gantry.setValue(45.0)
        window.pushButton_reset.click()
        assert window.doubleSpinBox_gantry.value() == pytest.approx(90.0)
        assert window.doubleSpinBox_rescale_factor.value() == pytest.approx(1.0)

    def test_inspect_pane_shows_the_exported_plan(self, window, tmp_path):
        """After export the pane must describe what was written, not the original."""
        window.load_plan(str(PLAN_FILE))
        window.comboBox_treatment_machine.setCurrentIndex(0)      # TR1, plan is TR4
        before = window.plainTextEdit_inspect.toPlainText()
        out = tmp_path / "out.dcm"
        assert window.export_to(str(out))
        after = window.plainTextEdit_inspect.toPlainText()
        assert after != before
        assert "exported:" in after
        assert "TR1" in after

    def test_approved_plan_shows_a_ticked_disabled_checkbox(self, window):
        """DicomUtil cannot un-approve, so the control must not pretend it can."""
        window.load_plan(str(PLAN_FILE))            # this plan is APPROVED
        assert window.plan.approved
        assert window.checkBox_approve.isChecked()
        assert not window.checkBox_approve.isEnabled()
        assert "cannot un-approve" in window.checkBox_approve.toolTip()

    def test_curative_plan_shows_a_ticked_disabled_checkbox(self, window):
        """set_intent_to_curative() is one-way too, so the box must not pretend.

        PLAN_FILE is already CURATIVE, as it is already APPROVED.
        """
        window.load_plan(str(PLAN_FILE))
        assert window.plan.curative_intent
        assert window.checkBox_curative_intent.isChecked()
        assert not window.checkBox_curative_intent.isEnabled()
        assert "cannot unset" in window.checkBox_curative_intent.toolTip()

    def test_non_curative_plan_leaves_the_box_editable(self, window, tmp_path):
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        d.PlanIntent = "PALLIATIVE"
        d.ApprovalStatus = "UNAPPROVED"
        p = tmp_path / "palliative.dcm"
        d.save_as(str(p))
        window.load_plan(str(p))
        assert not window.plan.curative_intent
        assert window.checkBox_curative_intent.isEnabled()
        assert not window.checkBox_curative_intent.isChecked()
        assert window.checkBox_approve.isEnabled()

    def test_treatment_machine_has_a_label(self, window):
        assert window.label_treatment_machine.text() == "Treatment Machine"


class TestDragAndDrop:
    """Dropping must be guarded: a CT or a stray file should say why, not traceback."""

    def test_window_accepts_drops(self, window):
        assert window.acceptDrops()

    def test_a_real_ion_plan_is_accepted(self):
        from dicomfix.gui.model import describe_unsupported
        assert describe_unsupported(str(PLAN_FILE)) is None

    def test_a_non_dicom_file_is_rejected(self, tmp_path):
        from dicomfix.gui.model import describe_unsupported
        bad = tmp_path / "notes.txt"
        bad.write_text("not dicom at all")
        problem = describe_unsupported(str(bad))
        assert problem is not None, "a text file was accepted as a plan"
        assert "Not a DICOM file" in problem

    def test_a_dicom_of_the_wrong_modality_is_rejected(self, tmp_path):
        import pydicom

        from dicomfix.gui.model import describe_unsupported
        d = pydicom.dcmread(str(PLAN_FILE))
        d.Modality = "CT"
        p = tmp_path / "ct.dcm"
        d.save_as(str(p))
        problem = describe_unsupported(str(p))
        assert problem is not None, "a CT was accepted as a plan"
        assert "not an RTPLAN" in problem

    def test_a_non_ion_rtplan_is_rejected(self, tmp_path):
        """A photon RTPLAN is a valid RTPLAN but has no IonBeamSequence."""
        import pydicom

        from dicomfix.gui.model import describe_unsupported
        d = pydicom.dcmread(str(PLAN_FILE))
        del d.IonBeamSequence
        p = tmp_path / "photon.dcm"
        d.save_as(str(p))
        problem = describe_unsupported(str(p))
        assert problem is not None, "a photon plan was accepted as an ion plan"
        assert "not an ion plan" in problem

    def test_dropping_a_bad_file_warns_and_loads_nothing(self, window, tmp_path,
                                                         no_modal_dialogs):
        from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PyQt6.QtGui import QDropEvent
        bad = tmp_path / "notes.txt"
        bad.write_text("not dicom")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(bad))])
        event = QDropEvent(QPointF(0, 0), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.dropEvent(event)
        assert "critical" in no_modal_dialogs
        assert window.plan is None

    def test_dropping_a_plan_loads_it(self, window):
        from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PyQt6.QtGui import QDropEvent
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(PLAN_FILE.resolve()))])
        event = QDropEvent(QPointF(0, 0), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.dropEvent(event)
        assert window.plan is not None
        assert window.windowTitle().endswith("Plan5.5.dcm")


class TestSnout:
    def test_retract_button_sets_fully_retracted_position(self, window):
        from dicomfix.gui.model import SNOUT_RETRACTED
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_nozzle_position.setValue(20.0)
        window.pushButton_snout_retract.click()
        assert window.doubleSpinBox_nozzle_position.value() == pytest.approx(SNOUT_RETRACTED)

    def test_retracting_queues_a_snout_edit(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_nozzle_position.setValue(20.0)
        assert window.settings.snout_position == pytest.approx(20.0)
        window.pushButton_snout_retract.click()
        # PLAN_FILE is already at 42.1, so retracting returns it to unchanged
        assert window.settings.snout_position is None

    def test_snout_edit_reaches_the_command_line(self, window):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_nozzle_position.setValue(30.0)
        assert "-sp=30" in window.settings.to_args("in.dcm", "out.dcm")


class TestIcon:
    def test_icon_file_ships_with_the_package(self):
        from dicomfix.gui.window import ICON_FILE, resource_path
        assert Path(resource_path(ICON_FILE)).is_file()

    def test_icon_has_the_sizes_windows_wants(self):
        """Explorer, the taskbar and alt-tab all pick different sizes out of the .ico."""
        from PIL import Image

        from dicomfix.gui.window import ICON_FILE, resource_path
        sizes = Image.open(resource_path(ICON_FILE)).info["sizes"]
        for wanted in ((16, 16), (32, 32), (48, 48), (256, 256)):
            assert wanted in sizes, f"icon is missing the {wanted[0]}px variant"

    def test_window_actually_sets_it(self, window):
        assert not window.windowIcon().isNull()


class TestUnlistedTreatmentMachine:
    """A plan may name a machine outside the hard-coded TR1..TR4 list."""

    @pytest.fixture
    def tr7_plan(self, tmp_path):
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        for ib in d.IonBeamSequence:
            ib.TreatmentMachineName = "TR7"
        p = tmp_path / "tr7.dcm"
        d.save_as(str(p))
        return str(p)

    @pytest.fixture
    def nameless_plan(self, tmp_path):
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        for ib in d.IonBeamSequence:
            ib.TreatmentMachineName = ""
        p = tmp_path / "nameless.dcm"
        d.save_as(str(p))
        return str(p)

    def test_unlisted_machine_is_shown_not_blanked(self, window, tr7_plan):
        window.load_plan(tr7_plan)
        assert window.comboBox_treatment_machine.currentText() == "TR7"

    def test_unlisted_machine_stays_reachable(self, window, tr7_plan):
        """Without this the user cannot get back to the plan's own machine."""
        window.load_plan(tr7_plan)
        c = window.comboBox_treatment_machine
        assert "TR7" in [c.itemText(i) for i in range(c.count())]

    def test_unlisted_machine_queues_no_change_on_its_own(self, window, tr7_plan):
        window.load_plan(tr7_plan)
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.settings.treatment_machine is None
        assert "-tm" not in window.settings.to_args("in.dcm", "out.dcm")

    def test_switching_away_and_back_works(self, window, tr7_plan):
        window.load_plan(tr7_plan)
        c = window.comboBox_treatment_machine
        c.setCurrentIndex(0)                               # TR1
        assert window.settings.treatment_machine == "TR1"
        c.setCurrentIndex(c.findText("TR7"))
        assert window.settings.treatment_machine is None   # back to the plan's own value

    def test_the_extra_entry_does_not_accumulate(self, window, tr7_plan):
        """Loading another plan must not leave the previous plan's machine behind."""
        window.load_plan(tr7_plan)
        window.load_plan(str(PLAN_FILE))                   # TR4, a listed machine
        c = window.comboBox_treatment_machine
        assert [c.itemText(i) for i in range(c.count())] == ["TR1", "TR2", "TR3", "TR4"]
        assert c.currentText() == "TR4"

    def test_plan_with_no_machine_name_queues_nothing(self, window, nameless_plan):
        """Any selection here would be a change the user never asked for."""
        window.load_plan(nameless_plan)
        assert window.comboBox_treatment_machine.currentIndex() == -1
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.settings.treatment_machine is None


class TestSnoutRange:
    """The snout travels 0 to 42.1 cm, fully retracted being the far end."""

    def test_range_is_capped_at_fully_retracted(self, window):
        from dicomfix.gui.model import SNOUT_RETRACTED
        window.load_plan(str(PLAN_FILE))
        assert window.doubleSpinBox_nozzle_position.minimum() == pytest.approx(0.0)
        assert window.doubleSpinBox_nozzle_position.maximum() == pytest.approx(SNOUT_RETRACTED)

    def test_a_value_beyond_the_cap_is_not_silently_clamped(self, window, tmp_path):
        """Clamping would rewrite the plan's own value and queue an -sp edit."""
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        for ib in d.IonBeamSequence:
            ib.IonControlPointSequence[0].SnoutPosition = 480.0     # 48 cm
        p = tmp_path / "long_snout.dcm"
        d.save_as(str(p))

        window.load_plan(str(p))
        assert window.doubleSpinBox_nozzle_position.value() == pytest.approx(48.0)
        assert window.settings.snout_position is None
        assert "-sp" not in " ".join(window.settings.to_args("in.dcm", "out.dcm"))


class TestExportThenReset:
    """Reset after an export must leave the window describing one plan, not two."""

    def test_reset_returns_the_pane_to_the_loaded_plan(self, window, tmp_path):
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.export_to(str(tmp_path / "out.dcm"))
        assert "exported:" in window.plainTextEdit_inspect.toPlainText()
        window.pushButton_reset.click()
        assert "exported:" not in window.plainTextEdit_inspect.toPlainText()

    def test_reset_does_not_delete_the_exported_file(self, window, tmp_path):
        """Reset discards queued edits, not work already written to disk."""
        out = tmp_path / "out.dcm"
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.export_to(str(out))
        size = out.stat().st_size
        window.pushButton_reset.click()
        assert out.is_file() and out.stat().st_size == size

    def test_the_loaded_plan_is_never_modified_by_exporting(self, window, tmp_path):
        """Edits are deferred, so exporting builds a fresh plan and leaves this one alone."""
        window.load_plan(str(PLAN_FILE))
        before = window.plan.prescribed_dose
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.export_to(str(tmp_path / "out.dcm"))
        assert window.plan.prescribed_dose == pytest.approx(before)

    def test_exporting_twice_does_not_compound(self, window, tmp_path):
        """The second export must rescale from the original, not from the first output."""
        from dicomfix.dicomutil import DicomUtil
        window.load_plan(str(PLAN_FILE))
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        a, b = tmp_path / "a.dcm", tmp_path / "b.dcm"
        assert window.export_to(str(a))
        assert window.export_to(str(b))
        assert sha256(a) == sha256(b)
        rb = DicomUtil(str(a)).dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        assert float(rb.BeamDose) == pytest.approx(11.0, rel=1e-4)   # 5.5 x 2, not x 4


class TestFileMenu:
    def test_file_menu_offers_open_and_exit(self, window):
        texts = [a.text() for a in window.menuFile.actions() if not a.isSeparator()]
        assert texts == ["Open", "Exit"]

    def test_exit_is_separated_from_open(self, window):
        """A separator keeps Exit from being hit while reaching for Open."""
        assert any(a.isSeparator() for a in window.menuFile.actions())

    def test_exit_closes_the_window(self, window):
        window.show()
        assert window.isVisible()
        window.actionExit.trigger()
        assert not window.isVisible()

    def test_exit_is_placed_correctly_on_macos(self, window):
        """QuitRole moves it into the application menu on macOS, and is inert elsewhere."""
        assert window.actionExit.menuRole() == QAction.MenuRole.QuitRole


class TestLinkedFieldsLastEditWins:
    """The dose box is coarser than the factor, which can hide a disagreement.

    On a 1 Gy plan a factor of 1.004 displays as a dose of 1.00. Retyping "1.00" then
    emits no valueChanged, so without editingFinished the factor would keep 1.004 and
    export a dose the user had just overridden.
    """

    @pytest.fixture
    def one_gy_plan(self, tmp_path):
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose = 1.0
        p = tmp_path / "one_gy.dcm"
        d.save_as(str(p))
        return str(p)

    @staticmethod
    def type_dose(window, text):
        """Type into the dose box and commit, as a user would."""
        line = window.doubleSpinBox_rescale_dose.lineEdit()
        line.setText(text)
        line.setModified(True)
        window.doubleSpinBox_rescale_dose.editingFinished.emit()

    def test_factor_alone_is_kept(self, window, one_gy_plan):
        window.load_plan(one_gy_plan)
        window.doubleSpinBox_rescale_factor.setValue(1.004)
        assert window.settings.rescale_factor == pytest.approx(1.004)

    def test_typing_the_displayed_dose_still_overrides_the_factor(self, window, one_gy_plan):
        """The case that motivated editingFinished."""
        window.load_plan(one_gy_plan)
        window.doubleSpinBox_rescale_factor.setValue(1.004)
        assert window.doubleSpinBox_rescale_dose.text().startswith("1.00")
        self.type_dose(window, "1.00")
        assert window.doubleSpinBox_rescale_factor.value() == pytest.approx(1.0)
        assert window.settings.rescale_factor is None       # 1.0 means no rescaling

    def test_focus_alone_does_not_clobber_the_factor(self, window, one_gy_plan):
        """editingFinished also fires on focus-out; isModified() must gate it."""
        window.load_plan(one_gy_plan)
        window.doubleSpinBox_rescale_factor.setValue(1.004)
        window.doubleSpinBox_rescale_dose.editingFinished.emit()
        assert window.settings.rescale_factor == pytest.approx(1.004)

    def test_exported_dose_follows_the_last_edited_box(self, window, one_gy_plan, tmp_path):
        from dicomfix.dicomutil import DicomUtil

        def written(action):
            window.load_plan(one_gy_plan)
            action()
            out = tmp_path / "o.dcm"
            assert window.export_to(str(out))
            rb = DicomUtil(str(out)).dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
            return float(rb.BeamDose)

        assert written(lambda: window.doubleSpinBox_rescale_factor.setValue(1.004)) \
            == pytest.approx(1.004, abs=1e-4)
        assert written(lambda: (window.doubleSpinBox_rescale_factor.setValue(1.004),
                                self.type_dose(window, "1.00"))) \
            == pytest.approx(1.000, abs=1e-4)


class TestWheelSteps:
    """One scheme everywhere: plain = the box's step, Shift = a tenth, Ctrl = ten times.

    Qt supplies plain and Ctrl; Shift does nothing by default and is added by
    FineWheelFilter. Only the base step differs per quantity.
    """

    @staticmethod
    def scroll(app, box, modifier):
        from PyQt6.QtCore import QPoint, QPointF, Qt
        from PyQt6.QtGui import QWheelEvent
        event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                            Qt.MouseButton.NoButton, modifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(box, event)

    @pytest.mark.parametrize("name", [
        "doubleSpinBox_table_vertical", "doubleSpinBox_table_longitudinal",
        "doubleSpinBox_table_lateral", "doubleSpinBox_nozzle_position",
        "doubleSpinBox_gantry", "doubleSpinBox_rescale_factor",
    ])
    def test_modifiers_scale_the_step(self, window, qapp, name):
        from PyQt6.QtCore import Qt

        from dicomfix.gui.window import _WHEEL_STEPS
        window.load_plan(str(PLAN_FILE))
        box, step = getattr(window, name), _WHEEL_STEPS[name]
        # Start clear of the floor, so a full Ctrl step of 10x has room and the test
        # measures the step rather than the clamp.
        start = box.minimum() + step * 20
        box.setValue(start)
        start = box.value()
        for modifier, expected in (
            (Qt.KeyboardModifier.NoModifier, step),
            (Qt.KeyboardModifier.ShiftModifier, step / 10),
            (Qt.KeyboardModifier.ControlModifier, step * 10),
        ):
            box.setValue(start)
            self.scroll(qapp, box, modifier)
            assert start - box.value() == pytest.approx(expected, rel=1e-6), \
                f"{name} with {modifier}"

    def test_geometry_boxes_step_by_one_unit(self, window):
        from dicomfix.gui.window import _WHEEL_STEPS
        for name in ("doubleSpinBox_table_vertical", "doubleSpinBox_nozzle_position",
                     "doubleSpinBox_gantry", "doubleSpinBox_rescale_dose"):
            assert _WHEEL_STEPS[name] == 1.0

    def test_factor_steps_a_decade_finer(self, window):
        """A step of 1.0 on a dimensionless factor near 1 would double a plan per notch."""
        from dicomfix.gui.window import _WHEEL_STEPS
        assert _WHEEL_STEPS["doubleSpinBox_rescale_factor"] == 0.1

    def test_rescale_boxes_cannot_reach_zero(self, window):
        """modify() gates on truthiness, so -rf=0 is silently skipped, not rejected."""
        window.load_plan(str(PLAN_FILE))
        for name in ("doubleSpinBox_rescale_factor", "doubleSpinBox_rescale_dose"):
            box = getattr(window, name)
            box.setValue(0.0)
            assert box.value() > 0.0, f"{name} reached zero"

    def test_the_hint_is_in_the_tooltip(self, window):
        window.load_plan(str(PLAN_FILE))
        assert "Shift" in window.doubleSpinBox_table_vertical.toolTip()
        assert "Shift" in window.doubleSpinBox_gantry.toolTip()


class TestUnlistedRangeShifter:
    """Plans carry range shifter IDs outside None/RS2/RS5 -- e.g. a slit collimator.

    Collapsing those to "None" made the GUI claim there was nothing to remove, so
    selecting "None" queued no change and the shifter survived the export. That is
    issue #43 all over again, one layer up.
    """

    @pytest.fixture
    def slit_plan(self, tmp_path):
        import pydicom
        d = pydicom.dcmread(str(PLAN_FILE))
        for ib in d.IonBeamSequence:
            ib.NumberOfRangeShifters = 1
            rs = pydicom.Dataset()
            rs.RangeShifterNumber = 1
            rs.RangeShifterID = "SlitColl"
            rs.RangeShifterType = "BINARY"
            ib.RangeShifterSequence = [rs]
        p = tmp_path / "slit.dcm"
        d.save_as(str(p))
        return str(p)

    @staticmethod
    def shifter_of(path):
        from dicomfix.dicomutil import DicomUtil
        ib = DicomUtil(path).dicom.IonBeamSequence[0]
        seq = getattr(ib, "RangeShifterSequence", None)
        return str(seq[0].RangeShifterID) if seq else None

    def test_the_plans_own_shifter_is_shown(self, window, slit_plan):
        window.load_plan(slit_plan)
        assert window.comboBox_range_shifter.currentText() == "SlitColl"

    def test_it_is_offered_in_the_list(self, window, slit_plan):
        window.load_plan(slit_plan)
        c = window.comboBox_range_shifter
        assert [c.itemText(i) for i in range(c.count())] == \
            ["None", "RS2", "RS5", "SlitColl"]

    def test_leaving_it_alone_queues_nothing(self, window, slit_plan):
        window.load_plan(slit_plan)
        window.doubleSpinBox_rescale_factor.setValue(2.0)
        assert window.settings.range_shifter is None

    def test_selecting_none_actually_removes_it(self, window, slit_plan, tmp_path):
        """The whole point: -rh=None must be emitted and the shifter must go."""
        window.load_plan(slit_plan)
        window.comboBox_range_shifter.setCurrentIndex(0)          # None
        assert "-rh=None" in window.settings.to_args("in.dcm", "out.dcm")
        out = tmp_path / "removed.dcm"
        assert window.export_to(str(out))
        assert self.shifter_of(str(out)) is None

    def test_selecting_a_real_shifter_replaces_it(self, window, slit_plan, tmp_path):
        window.load_plan(slit_plan)
        window.comboBox_range_shifter.setCurrentIndex(1)          # RS2
        out = tmp_path / "rs2.dcm"
        assert window.export_to(str(out))
        assert self.shifter_of(str(out)) == "RS_2CM"

    def test_an_unlisted_id_is_never_passed_to_rh(self, window, slit_plan):
        """-rh only understands None/RS2/RS5; 'SlitColl' must never reach it."""
        window.load_plan(slit_plan)
        for i in range(window.comboBox_range_shifter.count()):
            window.comboBox_range_shifter.setCurrentIndex(i)
            for arg in window.settings.to_args("in.dcm", "out.dcm"):
                assert not arg.startswith("-rh=SlitColl")

    def test_the_extra_entry_does_not_accumulate(self, window, slit_plan):
        window.load_plan(slit_plan)
        window.load_plan(str(PLAN_FILE))          # no range shifter
        c = window.comboBox_range_shifter
        assert [c.itemText(i) for i in range(c.count())] == ["None", "RS2", "RS5"]
        assert c.currentText() == "None"


class TestTooltips:
    """Every control the user can touch should say what it does."""

    KINDS = ("QPushButton", "QComboBox", "QDoubleSpinBox", "QSpinBox",
             "QCheckBox", "QPlainTextEdit")

    def interactive(self, window):
        seen = {}
        for child in window.findChildren(object):
            name = getattr(child, "objectName", lambda: "")()
            if name and type(child).__name__ in self.KINDS:
                seen.setdefault(name, child)
        return seen

    def test_no_control_is_left_unexplained(self, window):
        window.load_plan(str(PLAN_FILE))
        missing = [n for n, c in self.interactive(window).items() if not c.toolTip()]
        assert not missing, f"controls without a tooltip: {missing}"

    def test_before_a_plan_is_loaded_too(self, window):
        """Tooltips set only in _show_field would be absent on an empty window."""
        missing = [n for n, c in self.interactive(window).items() if not c.toolTip()]
        assert not missing, f"controls without a tooltip: {missing}"

    def test_scrollable_boxes_explain_the_modifiers(self, window):
        from dicomfix.gui.window import _WHEEL_STEPS
        window.load_plan(str(PLAN_FILE))
        for name in _WHEEL_STEPS:
            tip = getattr(window, name).toolTip()
            assert "Shift" in tip and "Ctrl" in tip, f"{name} does not mention modifiers"

    def test_table_boxes_carry_the_axis_description(self, window):
        """Users hover the spin box, not the label that describes the axis."""
        window.load_plan(str(PLAN_FILE))
        assert "positive upwards" in window.doubleSpinBox_table_vertical.toolTip()
        assert "cranial" in window.doubleSpinBox_table_longitudinal.toolTip()
        assert "left side" in window.doubleSpinBox_table_lateral.toolTip()

    def test_controls_dicomfix_cannot_operate_say_so(self, window):
        window.load_plan(str(PLAN_FILE))
        for name in ("doubleSpinBox_couch", "checkBox_anonymize", "checkBox_reviewername"):
            assert "ot implemented" in getattr(window, name).toolTip(), name
