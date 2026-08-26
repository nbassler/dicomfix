"""
Unit tests for dicomfix.dicomutil.DicomUtil

Tests exercise individual methods directly on the sample DICOM plan,
without going through the CLI layer.
"""
import datetime
import pytest
from pathlib import Path

from dicomfix.dicomutil import DicomUtil, MU_MIN
from dicomfix.dicomexport import DicomExport


PLAN_FILE = Path('res', 'Plan5.5.dcm')


@pytest.fixture
def du():
    """Fresh DicomUtil instance for every test."""
    return DicomUtil(str(PLAN_FILE))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoad:
    def test_dicom_object_is_not_none(self, du):
        assert du.dicom is not None

    def test_total_spots_is_positive(self, du):
        assert du.total_number_of_spots > 0

    def test_spots_discarded_starts_at_zero(self, du):
        assert du.spots_discarded == 0

    def test_old_dicom_is_independent_copy(self, du):
        original_dose = du.old_dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        du.apply_rescale_factor(2.0)
        assert du.old_dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose == original_dose


# ---------------------------------------------------------------------------
# Metadata setters
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_approve_plan_sets_approved(self, du):
        du.approve_plan()
        assert du.dicom.ApprovalStatus == "APPROVED"

    def test_set_intent_curative(self, du):
        du.set_intent_to_curative()
        assert du.dicom.PlanIntent == "CURATIVE"

    def test_set_patient_name(self, du):
        du.set_patient_name("Test^Patient")
        assert str(du.dicom.PatientName) == "Test^Patient"

    def test_set_reviewer_name(self, du):
        du.set_reviewer_name("Dr. Smith")
        assert du.dicom.ReviewerName == "Dr. Smith"

    def test_set_plan_label(self, du):
        du.set_plan_label("MyPlanLabel")
        assert du.dicom.RTPlanLabel == "MyPlanLabel"

    def test_set_current_date_matches_today(self, du):
        du.set_current_date()
        today = datetime.datetime.now().strftime("%Y%m%d")
        assert du.dicom.RTPlanDate == today

    def test_set_current_date_sets_time(self, du):
        du.set_current_date()
        assert du.dicom.RTPlanTime is not None
        assert len(du.dicom.RTPlanTime) > 0

    def test_set_treatment_machine_all_fields(self, du):
        du.set_treatment_machine("TR4")
        for ib in du.dicom.IonBeamSequence:
            assert ib.TreatmentMachineName == "TR4"

    def test_set_treatment_machine_custom_name(self, du):
        du.set_treatment_machine("CUSTOM_MACHINE")
        for ib in du.dicom.IonBeamSequence:
            assert ib.TreatmentMachineName == "CUSTOM_MACHINE"


# ---------------------------------------------------------------------------
# Positioning
# ---------------------------------------------------------------------------

class TestPositioning:
    def test_set_gantry_angles_single_field(self, du):
        nf = len(du.dicom.IonBeamSequence)
        angles = tuple(90.0 for _ in range(nf))
        du.set_gantry_angles(angles)
        for ib in du.dicom.IonBeamSequence:
            assert ib.IonControlPointSequence[0].GantryAngle == 90.0

    def test_set_gantry_angles_wrong_count_raises(self, du):
        # Pass far too many angles to guarantee mismatch
        with pytest.raises(ValueError):
            du.set_gantry_angles(tuple(90.0 for _ in range(100)))

    def test_set_snout_position(self, du):
        du.set_snout_position(421.0)
        for ib in du.dicom.IonBeamSequence:
            assert ib.IonControlPointSequence[0].SnoutPosition == pytest.approx(421.0)

    def test_set_table_position_values(self, du):
        du.set_table_position((10.0, 20.0, -5.0))
        for ib in du.dicom.IonBeamSequence:
            icp = ib.IonControlPointSequence[0]
            assert icp.TableTopVerticalPosition == pytest.approx(10.0)
            assert icp.TableTopLongitudinalPosition == pytest.approx(20.0)
            assert icp.TableTopLateralPosition == pytest.approx(-5.0)

    def test_set_table_position_wrong_count_raises(self, du):
        with pytest.raises(ValueError):
            du.set_table_position((10.0, 20.0))  # needs exactly 3

    def test_set_table_position_zero(self, du):
        du.set_table_position((0.0, 0.0, 0.0))
        for ib in du.dicom.IonBeamSequence:
            icp = ib.IonControlPointSequence[0]
            assert icp.TableTopVerticalPosition == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Range shifter
# ---------------------------------------------------------------------------

class TestRangeShifter:
    def test_set_range_shifter_rs2cm_id(self, du):
        du.set_range_shifter("RS_2CM")
        for ib in du.dicom.IonBeamSequence:
            assert ib.RangeShifterSequence[0].RangeShifterID == "RS_2CM"

    def test_set_range_shifter_rs2cm_count(self, du):
        du.set_range_shifter("RS_2CM")
        for ib in du.dicom.IonBeamSequence:
            assert ib.NumberOfRangeShifters == 1

    def test_set_range_shifter_rs5cm(self, du):
        du.set_range_shifter("RS_5CM")
        for ib in du.dicom.IonBeamSequence:
            assert ib.RangeShifterSequence[0].RangeShifterID == "RS_5CM"

    def test_set_range_shifter_invalid_raises(self, du):
        with pytest.raises(ValueError):
            du.set_range_shifter("RS_3CM")

    # None, the "NONE" sentinel and the web UI's plain "None" string must all remove it.
    @pytest.mark.parametrize("removal_value", [None, "NONE", "None", "none"])
    def test_remove_range_shifter(self, du, removal_value):
        du.set_range_shifter("RS_2CM")       # add first
        du.set_range_shifter(removal_value)  # then remove
        for ib in du.dicom.IonBeamSequence:
            assert not hasattr(ib, "RangeShifterSequence")
            assert ib.NumberOfRangeShifters == 0
            # No control point may keep a reference to the removed range shifter
            for ics in ib.IonControlPointSequence:
                assert not hasattr(ics, "RangeShifterSettingsSequence")

    def test_rs2cm_water_equivalent_thickness(self, du):
        du.set_range_shifter("RS_2CM")
        for ib in du.dicom.IonBeamSequence:
            rsss = ib.IonControlPointSequence[0].RangeShifterSettingsSequence[0]
            assert rsss.RangeShifterWaterEquivalentThickness == pytest.approx(22.8)

    def test_rs5cm_water_equivalent_thickness(self, du):
        du.set_range_shifter("RS_5CM")
        for ib in du.dicom.IonBeamSequence:
            rsss = ib.IonControlPointSequence[0].RangeShifterSettingsSequence[0]
            assert rsss.RangeShifterWaterEquivalentThickness == pytest.approx(57.0)


# ---------------------------------------------------------------------------
# Tolerance table
# ---------------------------------------------------------------------------

class TestToleranceTable:
    def test_adds_sequence(self, du):
        du.add_table_tolerance_sequence()
        assert hasattr(du.dicom, "IonToleranceTableSequence")

    def test_label_is_t1(self, du):
        du.add_table_tolerance_sequence()
        assert du.dicom.IonToleranceTableSequence[0].ToleranceTableLabel == "T1"

    def test_gantry_angle_tolerance(self, du):
        du.add_table_tolerance_sequence()
        assert du.dicom.IonToleranceTableSequence[0].GantryAngleTolerance == pytest.approx(0.5)

    def test_snout_position_tolerance(self, du):
        du.add_table_tolerance_sequence()
        assert du.dicom.IonToleranceTableSequence[0].SnoutPositionTolerance == pytest.approx(5.0)

    def test_table_number_is_1(self, du):
        du.add_table_tolerance_sequence()
        assert du.dicom.IonToleranceTableSequence[0].ToleranceTableNumber == 1


# ---------------------------------------------------------------------------
# TR4 wizard
# ---------------------------------------------------------------------------

class TestWizardTr4:
    def test_approval_status_approved(self, du):
        du.set_wizard_tr4()
        assert du.dicom.ApprovalStatus == "APPROVED"

    def test_treatment_machine_tr4(self, du):
        du.set_wizard_tr4()
        for ib in du.dicom.IonBeamSequence:
            assert ib.TreatmentMachineName == "TR4"

    def test_gantry_angle_90(self, du):
        du.set_wizard_tr4()
        for ib in du.dicom.IonBeamSequence:
            assert ib.IonControlPointSequence[0].GantryAngle == pytest.approx(90.0)

    def test_snout_position_421(self, du):
        du.set_wizard_tr4()
        for ib in du.dicom.IonBeamSequence:
            assert ib.IonControlPointSequence[0].SnoutPosition == pytest.approx(421.0)


# ---------------------------------------------------------------------------
# Rescaling
# ---------------------------------------------------------------------------

class TestRescaling:
    def test_rescale_factor_doubles_beam_meterset(self, du):
        orig = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset
        du.apply_rescale_factor(2.0)
        new = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset
        assert new == pytest.approx(orig * 2.0, rel=1e-4)

    def test_rescale_factor_doubles_beam_dose(self, du):
        orig = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        du.apply_rescale_factor(2.0)
        new = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        assert new == pytest.approx(orig * 2.0, rel=1e-4)

    def test_rescale_factor_halves_beam_meterset(self, du):
        orig = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset
        du.apply_rescale_factor(0.5)
        new = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset
        assert new == pytest.approx(orig * 0.5, rel=1e-4)

    def test_rescale_dose_sets_target_dose(self, du):
        target = 10.0
        du.rescale_dose(target)
        for j in range(len(du.dicom.IonBeamSequence)):
            new_dose = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose
            assert new_dose == pytest.approx(target, rel=1e-4)

    def test_rescale_dose_5_5_unchanged(self, du):
        """Rescaling to the original dose should leave values unchanged."""
        orig = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        du.rescale_dose(orig)
        new = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        assert new == pytest.approx(orig, rel=1e-4)

    def test_minimize_plan_no_spot_below_mu_min(self, du):
        du.minimize_plan()
        for j, ib in enumerate(du.dicom.IonBeamSequence):
            beam_meterset = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / ib.FinalCumulativeMetersetWeight
            for icp in ib.IonControlPointSequence:
                ms = icp.ScanSpotMetersetWeights
                weights = list(ms) if hasattr(ms, '__iter__') else [ms]
                for w in weights:
                    if float(w) > 0.0:
                        assert float(w) * meterset_per_weight >= MU_MIN - 1e-6

    def test_layer_factors_wrong_count_raises(self, du):
        n_layers = int(du.dicom.IonBeamSequence[0].NumberOfControlPoints / 2)
        wrong_factors = [1.0] * (n_layers + 1)
        with pytest.raises(Exception):
            du.apply_rescale_factor(1.0, layer_factors=wrong_factors)

    def test_final_cumulative_weight_unchanged_after_rescale(self, du):
        # FinalCumulativeMetersetWeight is relative; only BeamMeterset scales.
        orig_weight = du.dicom.IonBeamSequence[0].FinalCumulativeMetersetWeight
        du.apply_rescale_factor(2.0)
        new_weight = du.dicom.IonBeamSequence[0].FinalCumulativeMetersetWeight
        assert new_weight == pytest.approx(orig_weight)


# ---------------------------------------------------------------------------
# Field duplication
# ---------------------------------------------------------------------------

class TestDuplicateFields:
    def test_doubles_field_count(self, du):
        orig = du.dicom.FractionGroupSequence[0].NumberOfBeams
        du.duplicate_fields(2)
        assert du.dicom.FractionGroupSequence[0].NumberOfBeams == orig * 2

    def test_triples_field_count(self, du):
        orig = du.dicom.FractionGroupSequence[0].NumberOfBeams
        du.duplicate_fields(3)
        assert du.dicom.FractionGroupSequence[0].NumberOfBeams == orig * 3

    def test_beam_numbers_are_sequential(self, du):
        du.duplicate_fields(2)
        for i, ib in enumerate(du.dicom.IonBeamSequence):
            assert ib.BeamNumber == i + 1

    def test_referenced_beam_numbers_match(self, du):
        du.duplicate_fields(2)
        fgs = du.dicom.FractionGroupSequence[0]
        for i, rbs in enumerate(fgs.ReferencedBeamSequence):
            assert rbs.ReferencedBeamNumber == i + 1

    def test_beam_names_contain_copy_id(self, du):
        du.duplicate_fields(2)
        beam_names = [ib.BeamName for ib in du.dicom.IonBeamSequence]
        assert any("(1/2)" in name for name in beam_names)
        assert any("(2/2)" in name for name in beam_names)


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

class TestInspect:
    def test_returns_string(self, du):
        assert isinstance(du.inspect(), str)

    def test_contains_patient_name(self, du):
        assert "Patient name" in du.inspect()

    def test_contains_approval_status(self, du):
        assert "Approval status" in du.inspect()

    def test_contains_beam_meterset(self, du):
        assert "Beam Meterset" in du.inspect()

    def test_contains_energy_layer(self, du):
        assert "Energy Layer" in du.inspect()

    def test_contains_treatment_machine(self, du):
        assert "Treatment Machine Name" in du.inspect()

    def test_reflects_patient_name_change(self, du):
        du.set_patient_name("ChangedName")
        assert "ChangedName" in du.inspect()

    def test_reflects_approval_change(self, du):
        du.approve_plan()
        assert "APPROVED" in du.inspect()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_racehorse_creates_csv_files(self, du, tmp_path):
        base = str(tmp_path / "export")
        DicomExport.export_racehorse(du.dicom, base)
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) > 0

    def test_export_racehorse_csv_has_header(self, du, tmp_path):
        base = str(tmp_path / "export")
        DicomExport.export_racehorse(du.dicom, base)
        csv_files = list(tmp_path.glob("*.csv"))
        content = csv_files[0].read_text()
        assert "#HEADER" in content
        assert "#VALUES" in content

    def test_export_racehorse_filename_contains_mev(self, du, tmp_path):
        base = str(tmp_path / "export")
        DicomExport.export_racehorse(du.dicom, base)
        csv_files = list(tmp_path.glob("*.csv"))
        assert any("MeV" in f.name for f in csv_files)

    def test_export_unknown_format_raises(self, du, tmp_path):
        with pytest.raises(ValueError):
            DicomExport.export(du.dicom, str(tmp_path / "export"), export_format="unknown")

    def test_export_via_main_api(self, du, tmp_path):
        base = str(tmp_path / "export")
        DicomExport.export(du.dicom, base, export_format="racehorse")
        assert len(list(tmp_path.glob("*.csv"))) > 0
