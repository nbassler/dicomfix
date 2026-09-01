"""
Unit tests for dicomfix.dicomutil.DicomUtil

Tests exercise individual methods directly on the sample DICOM plan,
without going through the CLI layer.
"""
import copy
import datetime
import logging
from pathlib import Path

import pytest

from dicomfix.dicomexport import DicomExport
from dicomfix.dicomutil import DELAY_SPOT_POSITION, MU_MIN, DicomUtil

PLAN_FILE = Path('res', 'Plan5.5.dcm')


def spot_metersets(du):
    """MU actually delivered per spot, in plan order.

    MU = weight * BeamMeterset / FinalCumulativeMetersetWeight. This is what the machine
    delivers, so it is the quantity rescaling has to get right; BeamMeterset alone can be
    correct while the per-spot distribution is wrong.
    """
    d = du.dicom
    out = []
    for j, ib in enumerate(d.IonBeamSequence):
        beam_meterset = float(d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset)
        meterset_per_weight = beam_meterset / float(ib.FinalCumulativeMetersetWeight)
        for icp in ib.IonControlPointSequence:
            w = icp.ScanSpotMetersetWeights
            w = [w] if icp.NumberOfScanSpotPositions == 1 else list(w)
            out += [float(x) * meterset_per_weight for x in w]
    return out


def spot_positions(du):
    """Every spot position in plan order. Rescaling must never move a spot."""
    out = []
    for ib in du.dicom.IonBeamSequence:
        for icp in ib.IonControlPointSequence:
            out += [float(x) for x in icp.ScanSpotPositionMap]
    return out


def beam_energies(du):
    """Every control point energy. Rescaling must never change an energy."""
    return [float(icp.NominalBeamEnergy)
            for ib in du.dicom.IonBeamSequence for icp in ib.IonControlPointSequence]


def make_two_field(du):
    """Turn the single-field sample plan into a two-field one.

    PLAN_FILE has exactly one beam, which is why the multi-field bugs in issue #45
    were invisible to the suite. Duplicating the beam and its ReferencedBeamSequence
    entry gives a plan that exercises the multi-field paths.
    """
    d = du.dicom
    d.IonBeamSequence.append(copy.deepcopy(d.IonBeamSequence[0]))
    d.IonBeamSequence[1].BeamNumber = 2
    rbs = d.FractionGroupSequence[0].ReferencedBeamSequence
    rbs.append(copy.deepcopy(rbs[0]))
    rbs[1].ReferencedBeamNumber = 2
    d.FractionGroupSequence[0].NumberOfBeams = 2
    return du


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

    # --- issue #45 -------------------------------------------------------------

    def test_rescale_dose_rejects_multi_field(self, du):
        """BeamDose is per field, so a target dose is ambiguous on a multi-field plan."""
        make_two_field(du)
        with pytest.raises(ValueError, match="ambiguous"):
            du.rescale_dose(10.0)

    def test_rescale_dose_multi_field_leaves_plan_untouched(self, du):
        """The guard must reject before mutating anything."""
        make_two_field(du)
        rbs = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence
        before = [float(rb.BeamDose) for rb in rbs]
        with pytest.raises(ValueError):
            du.rescale_dose(10.0)
        assert [float(rb.BeamDose) for rb in rbs] == pytest.approx(before)

    def test_rescale_dose_rejects_missing_beam_dose(self, du):
        del du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
        with pytest.raises(ValueError, match="no BeamDose"):
            du.rescale_dose(10.0)

    def test_rescale_dose_rejects_zero_beam_dose(self, du):
        du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose = 0.0
        with pytest.raises(ValueError, match="0.0000"):
            du.rescale_dose(10.0)

    def test_rescale_dose_twice_is_reentrant(self, du):
        """apply_rescale_factor used to corrupt the weight type, breaking any second call.

        The Streamlit UI keeps one DicomUtil in session_state and rescales per edit,
        so a second rescale is a normal user action, not an edge case.
        """
        du.rescale_dose(10.0)
        du.rescale_dose(12.0)          # used to raise TypeError
        rb = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        assert float(rb.BeamDose) == pytest.approx(12.0, rel=1e-4)

    def test_rescale_factor_twice_is_reentrant(self, du):
        orig = float(du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)
        du.apply_rescale_factor(2.0)
        du.apply_rescale_factor(3.0)
        new = float(du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)
        assert new == pytest.approx(orig * 6.0, rel=1e-4)

    def test_prescription_dose_follows_beam_dose(self, du):
        """A plan whose prescription contradicts its beam dose is internally inconsistent."""
        # PLAN_FILE has no TargetPrescriptionDose, so give it one matching the beam dose.
        rb = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        du.dicom.DoseReferenceSequence[0].TargetPrescriptionDose = float(rb.BeamDose)
        du.rescale_dose(10.0)
        assert float(du.dicom.DoseReferenceSequence[0].TargetPrescriptionDose) == pytest.approx(
            float(rb.BeamDose), rel=1e-4)

    def test_prescription_dose_follows_rescale_factor(self, du):
        """-rf and -rm go through apply_rescale_factor too, so they must scale it as well."""
        dr = du.dicom.DoseReferenceSequence[0]
        dr.TargetPrescriptionDose = 5.5
        du.apply_rescale_factor(2.0)
        assert float(dr.TargetPrescriptionDose) == pytest.approx(11.0, rel=1e-4)

    def test_dose_constraints_are_not_rescaled(self, du):
        """Constraints are limits, not delivered dose, so they must be left alone."""
        dr = du.dicom.DoseReferenceSequence[0]
        original = float(dr.DeliveryMaximumDose)
        du.apply_rescale_factor(2.0)
        assert float(dr.DeliveryMaximumDose) == pytest.approx(original)

    def test_missing_prescription_dose_is_harmless(self, du):
        """PLAN_FILE has no TargetPrescriptionDose; rescaling must not invent one."""
        du.apply_rescale_factor(2.0)
        assert "TargetPrescriptionDose" not in du.dicom.DoseReferenceSequence[0]

    # --- delivery-critical invariants -----------------------------------------
    # -rf is the option used most in practice. These guard what actually reaches the
    # machine, not just the summary tags.

    @pytest.mark.parametrize("factor", [0.5, 1.5, 2.0, 10.0, 100.0])
    def test_every_spot_meterset_scales_by_factor(self, du, factor):
        """The core delivery invariant: each spot's MU scales by exactly the factor.

        Factors are chosen so no spot falls below MU_MIN; spot elimination is covered
        separately by test_surviving_spots_scale_exactly_when_spots_eliminated.
        """
        before = spot_metersets(du)
        du.apply_rescale_factor(factor)
        after = spot_metersets(du)
        assert du.spots_discarded == 0, "factor unexpectedly triggered MU_MIN elimination"
        assert len(after) == len(before)
        for got, want in zip(after, [b * factor for b in before]):
            assert got == pytest.approx(want, rel=1e-6, abs=1e-9)

    # When spots fall below MU_MIN they are zeroed, and their MU is redistributed over the
    # survivors so the plan total is preserved. The two tests below pin that behaviour down:
    # the total is exact, and the redistribution is uniform (it never distorts the pattern
    # among survivors). Note this means surviving spots deliver MORE than the requested
    # factor -- +1.0% at factor 0.1, +4.1% at 0.05, +72.8% at 0.02 on the sample plan.

    @pytest.mark.parametrize("factor", [0.05, 0.1, 0.3])
    def test_total_meterset_preserved_when_spots_eliminated(self, du, factor):
        """Plan total MU still matches the requested factor exactly, despite discards."""
        before = sum(spot_metersets(du))
        du.apply_rescale_factor(factor)
        assert du.spots_discarded > 0, "factor was expected to eliminate spots"
        assert sum(spot_metersets(du)) == pytest.approx(before * factor, rel=1e-6)

    @pytest.mark.parametrize("factor", [0.05, 0.1, 0.3])
    def test_redistribution_is_uniform_across_survivors(self, du, factor):
        """Discarded MU is spread evenly, so the pattern among survivors is undistorted.

        Every surviving spot must be off the requested scaling by the *same* ratio. A
        varying ratio would mean the delivered distribution had been reshaped.
        """
        before = spot_metersets(du)
        du.apply_rescale_factor(factor)
        after = spot_metersets(du)
        assert len(after) == len(before)
        ratios = [a / (b * factor) for a, b in zip(after, before) if a > 1e-9 and b > 1e-12]
        assert ratios, "expected some spots to survive"
        assert max(ratios) - min(ratios) == pytest.approx(0.0, abs=1e-9)
        assert min(ratios) >= 1.0  # survivors absorb the discarded MU, never lose it

    @pytest.mark.parametrize("factor", [0.5, 2.0, 7.3])
    def test_total_meterset_matches_beam_meterset(self, du, factor):
        """Sum of per-spot MU must equal the declared BeamMeterset, or the plan lies."""
        du.apply_rescale_factor(factor)
        declared = float(du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)
        assert sum(spot_metersets(du)) == pytest.approx(declared, rel=1e-6)

    @pytest.mark.parametrize("factor", [0.5, 2.0, 3.7])
    def test_relative_spot_pattern_is_preserved(self, du, factor):
        """Rescaling changes magnitude, never the shape of the delivered pattern."""
        before = spot_metersets(du)
        du.apply_rescale_factor(factor)
        after = spot_metersets(du)
        total_b, total_a = sum(before), sum(after)
        for got, want in zip([a / total_a for a in after], [b / total_b for b in before]):
            assert got == pytest.approx(want, rel=1e-6, abs=1e-12)

    @pytest.mark.parametrize("factor", [0.5, 2.0])
    def test_rescale_does_not_move_spots(self, du, factor):
        before = spot_positions(du)
        du.apply_rescale_factor(factor)
        assert spot_positions(du) == pytest.approx(before)

    @pytest.mark.parametrize("factor", [0.5, 2.0])
    def test_rescale_does_not_change_energies(self, du, factor):
        before = beam_energies(du)
        du.apply_rescale_factor(factor)
        assert beam_energies(du) == pytest.approx(before)

    def test_rescale_round_trip_restores_original(self, du):
        """f then 1/f must return the plan to where it started."""
        before = spot_metersets(du)
        du.apply_rescale_factor(4.0)
        du.apply_rescale_factor(1.0 / 4.0)
        assert spot_metersets(du) == pytest.approx(before, rel=1e-6)

    def test_rescale_by_one_is_a_no_op(self, du):
        before = spot_metersets(du)
        dose_before = float(du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose)
        du.apply_rescale_factor(1.0)
        assert spot_metersets(du) == pytest.approx(before, rel=1e-9)
        assert float(du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose) == \
            pytest.approx(dose_before)

    @pytest.mark.parametrize("factor", [0.5, 2.0, 3.0])
    def test_dose_per_mu_is_invariant(self, du, factor):
        """Gy(RBE) per MU is a property of the beamline, not of the scaling."""
        rb = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        before = float(rb.BeamDose) / float(rb.BeamMeterset)
        du.apply_rescale_factor(factor)
        assert float(rb.BeamDose) / float(rb.BeamMeterset) == pytest.approx(before, rel=1e-6)

    @pytest.mark.parametrize("bad", [0.0, -1.0, -2.5])
    def test_non_positive_factor_is_rejected(self, du, bad):
        """A zero or negative factor would write a plan with no deliverable MU."""
        with pytest.raises(ValueError, match="must be positive"):
            du.apply_rescale_factor(bad)

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_non_positive_factor_leaves_plan_untouched(self, du, bad):
        before = spot_metersets(du)
        with pytest.raises(ValueError):
            du.apply_rescale_factor(bad)
        assert spot_metersets(du) == pytest.approx(before)

    def test_negative_layer_factor_is_rejected(self, du):
        n_layers = int(du.dicom.IonBeamSequence[0].NumberOfControlPoints / 2)
        with pytest.raises(ValueError, match="must not be negative"):
            du.apply_rescale_factor(1.0, layer_factors=[-1.0] * n_layers)

    def test_no_surviving_spot_below_mu_min(self, du):
        """Spots too small to deliver must be zeroed, never left as undeliverable dust."""
        du.apply_rescale_factor(0.01)
        for mu in spot_metersets(du):
            assert mu == pytest.approx(0.0, abs=1e-9) or mu >= MU_MIN - 1e-6

    def test_discarded_spot_count_is_reported(self, du):
        assert du.spots_discarded == 0
        du.apply_rescale_factor(0.01)
        assert du.spots_discarded > 0

    def test_final_cumulative_weight_matches_last_control_point(self, du):
        """Internal bookkeeping must stay consistent or the plan is malformed."""
        du.apply_rescale_factor(2.0)
        for ib in du.dicom.IonBeamSequence:
            last = ib.IonControlPointSequence[-1].CumulativeMetersetWeight
            assert float(last) == pytest.approx(float(ib.FinalCumulativeMetersetWeight), rel=1e-6)

    def test_cumulative_dose_coefficient_runs_zero_to_one(self, du):
        """CumulativeDoseReferenceCoefficient must rise monotonically from 0 to 1."""
        du.apply_rescale_factor(2.0)
        for ib in du.dicom.IonBeamSequence:
            coeffs = [float(icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient)
                      for icp in ib.IonControlPointSequence
                      if "ReferencedDoseReferenceSequence" in icp]
            assert coeffs[0] == pytest.approx(0.0, abs=1e-9)
            assert coeffs[-1] == pytest.approx(1.0, rel=1e-6)
            assert coeffs == sorted(coeffs)

    def test_rescale_dose_and_factor_agree(self, du):
        """-rd X must be exactly equivalent to -rf (X / dose_in_plan)."""
        du_a = DicomUtil(str(PLAN_FILE))
        current = float(du_a.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose)
        du_a.rescale_dose(10.0)
        du.apply_rescale_factor(10.0 / current)
        assert spot_metersets(du_a) == pytest.approx(spot_metersets(du), rel=1e-9)

    def test_rescale_dose_reports_dose_factor_and_meterset(self, du, caplog):
        """The found dose, request, factor and meterset must be reported without -v."""
        rb = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        found, mu_before = float(rb.BeamDose), float(rb.BeamMeterset)
        with caplog.at_level(logging.WARNING, logger="dicomfix.dicomutil"):
            du.rescale_dose(10.0)
        text = caplog.text
        # warning level, so it shows at default verbosity
        assert all(r.levelno >= logging.WARNING for r in caplog.records if "Rescal" in r.message)
        assert f"{found:12.4f}" in text          # dose found in the plan
        assert f"{10.0:12.4f}" in text           # dose requested
        assert f"{10.0 / found:12.4f}" in text   # factor actually used
        assert f"{mu_before:12.4f}" in text      # meterset before
        assert f"{float(rb.BeamMeterset):12.4f}" in text  # meterset after

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
        # apply_rescale_factor raises a bare Exception; match= keeps the assertion
        # specific so an unrelated failure cannot make this test pass silently.
        with pytest.raises(Exception, match="must match number of energy layers"):
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

class TestRepeatLayerSpots:
    """Repeating the spot list inside each layer, with delay spots between passes."""

    def test_spot_count_per_control_point(self, du):
        icps = du.dicom.IonBeamSequence[0].IonControlPointSequence
        original = [icp.NumberOfScanSpotPositions for icp in icps]
        du.repeat_layer_spots(4, delay_mu=20.0)
        for icp, spots in zip(icps, original):
            assert icp.NumberOfScanSpotPositions == spots * 4 + 3

    def test_spot_count_without_delay_spots(self, du):
        icps = du.dicom.IonBeamSequence[0].IonControlPointSequence
        original = [icp.NumberOfScanSpotPositions for icp in icps]
        du.repeat_layer_spots(4)
        for icp, spots in zip(icps, original):
            assert icp.NumberOfScanSpotPositions == spots * 4

    def test_control_point_count_is_unchanged(self, du):
        """No layers are added: this is what keeps the plan deliverable."""
        ib = du.dicom.IonBeamSequence[0]
        original = ib.NumberOfControlPoints
        du.repeat_layer_spots(4, delay_mu=20.0)
        assert ib.NumberOfControlPoints == original
        assert len(ib.IonControlPointSequence) == original

    def test_energies_are_unchanged(self, du):
        """The delivery system wants strictly decreasing energies, so leave them alone."""
        original = beam_energies(du)
        du.repeat_layer_spots(4, delay_mu=20.0)
        assert beam_energies(du) == original

    def test_each_pass_delivers_the_original_meterset(self, du):
        """Full weight per pass, not divided as -rp does: every depth gets the full dose."""
        icp = du.dicom.IonBeamSequence[0].IonControlPointSequence[0]
        d = du.dicom
        ib = d.IonBeamSequence[0]
        before = float(d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset) \
            / float(ib.FinalCumulativeMetersetWeight)
        original_mu = [float(w) * before for w in icp.ScanSpotMetersetWeights]

        du.repeat_layer_spots(4, delay_mu=20.0)
        after = float(d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset) \
            / float(ib.FinalCumulativeMetersetWeight)
        spots = len(original_mu)
        got = [float(w) * after for w in icp.ScanSpotMetersetWeights]
        for repeat in range(4):
            start = repeat * (spots + 1)
            assert got[start:start + spots] == pytest.approx(original_mu)

    def test_delay_spots_sit_far_out_in_the_field(self, du):
        icps = du.dicom.IonBeamSequence[0].IonControlPointSequence
        spots = icps[0].NumberOfScanSpotPositions
        du.repeat_layer_spots(4, delay_mu=20.0)
        positions = list(icps[0].ScanSpotPositionMap)
        for repeat in range(3):
            k = (repeat + 1) * spots + repeat
            assert positions[2 * k:2 * k + 2] == list(DELAY_SPOT_POSITION)

    def test_delay_spot_delivers_the_requested_meterset(self, du):
        d = du.dicom
        ib = d.IonBeamSequence[0]
        spots = ib.IonControlPointSequence[0].NumberOfScanSpotPositions
        du.repeat_layer_spots(4, delay_mu=20.0)
        meterset_per_weight = float(d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset) \
            / float(ib.FinalCumulativeMetersetWeight)
        weights = list(ib.IonControlPointSequence[0].ScanSpotMetersetWeights)
        delivered = [float(weights[(r + 1) * spots + r]) * meterset_per_weight for r in range(3)]
        assert delivered == pytest.approx([20.0] * 3)

    def test_odd_control_point_mirrors_positions_with_zero_weights(self, du):
        du.repeat_layer_spots(4, delay_mu=20.0)
        icps = du.dicom.IonBeamSequence[0].IonControlPointSequence
        for even, odd in zip(icps[::2], icps[1::2]):
            assert list(odd.ScanSpotPositionMap) == list(even.ScanSpotPositionMap)
            assert all(float(w) == 0.0 for w in odd.ScanSpotMetersetWeights)

    def test_beam_meterset_includes_repeats_and_delay_spots(self, du):
        d = du.dicom
        rb = d.FractionGroupSequence[0].ReferencedBeamSequence[0]
        original = float(rb.BeamMeterset)
        layers = len(d.IonBeamSequence[0].IonControlPointSequence) // 2
        du.repeat_layer_spots(4, delay_mu=20.0)
        assert float(rb.BeamMeterset) == pytest.approx(original * 4 + layers * 3 * 20.0)

    def test_beam_dose_excludes_the_delay_spots(self, du):
        rb = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        original = float(rb.BeamDose)
        du.repeat_layer_spots(4, delay_mu=20.0)
        assert float(rb.BeamDose) == pytest.approx(original * 4)

    def test_cumulative_weights_increase_monotonically(self, du):
        du.repeat_layer_spots(25, delay_mu=20.0)
        weights = [float(icp.CumulativeMetersetWeight)
                   for icp in du.dicom.IonBeamSequence[0].IonControlPointSequence]
        assert weights[0] == 0.0
        assert all(b >= a for a, b in zip(weights, weights[1:]))

    def test_cumulative_weights_fit_in_a_decimal_string(self, du):
        """DS allows 16 characters, and a float repr of a long sum overruns it."""
        du.repeat_layer_spots(25, delay_mu=20.0)
        for icp in du.dicom.IonBeamSequence[0].IonControlPointSequence:
            assert len(str(icp.CumulativeMetersetWeight)) <= 16

    def test_cumulative_weight_reaches_final(self, du):
        du.repeat_layer_spots(25, delay_mu=20.0)
        ib = du.dicom.IonBeamSequence[0]
        last = ib.IonControlPointSequence[-1]
        total = float(last.CumulativeMetersetWeight) + sum(float(w) for w in last.ScanSpotMetersetWeights)
        assert total == pytest.approx(float(ib.FinalCumulativeMetersetWeight))

    def test_dose_reference_coefficient_runs_zero_to_one(self, du):
        du.repeat_layer_spots(4, delay_mu=20.0)
        coefficients = [float(icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient)
                        for icp in du.dicom.IonBeamSequence[0].IonControlPointSequence]
        assert coefficients[0] == 0.0
        assert coefficients[-1] == pytest.approx(1.0)
        assert all(b >= a for a, b in zip(coefficients, coefficients[1:]))

    def test_multi_field_plan(self, du):
        make_two_field(du)
        original = [ib.IonControlPointSequence[0].NumberOfScanSpotPositions
                    for ib in du.dicom.IonBeamSequence]
        du.repeat_layer_spots(3, delay_mu=20.0)
        for ib, spots in zip(du.dicom.IonBeamSequence, original):
            assert ib.IonControlPointSequence[0].NumberOfScanSpotPositions == spots * 3 + 2

    def test_one_pass_is_a_no_op(self, du):
        before = (spot_metersets(du), spot_positions(du))
        du.repeat_layer_spots(1, delay_mu=20.0)
        assert (spot_metersets(du), spot_positions(du)) == before

    @pytest.mark.parametrize("n", [0, -1, 2.5, "3", None])
    def test_invalid_repeat_count_raises(self, du, n):
        with pytest.raises(ValueError):
            du.repeat_layer_spots(n)

    @pytest.mark.parametrize("delay_mu", [0.0, -5.0, MU_MIN / 2.0])
    def test_delay_below_minimum_raises(self, du, delay_mu):
        """A spot under MU_MIN would be discarded, silently removing the delay."""
        with pytest.raises(ValueError):
            du.repeat_layer_spots(4, delay_mu=delay_mu)

    def test_field_without_total_weight_is_named_not_a_zero_division(self, du):
        du.dicom.IonBeamSequence[0].FinalCumulativeMetersetWeight = 0.0
        with pytest.raises(ValueError, match="FinalCumulativeMetersetWeight"):
            du.repeat_layer_spots(4)

    def test_warns_when_energies_do_not_decrease(self, du, caplog):
        """The constraint which makes a plan undeliverable, reported before the console."""
        icps = du.dicom.IonBeamSequence[0].IonControlPointSequence
        icps[2].NominalBeamEnergy = float(icps[0].NominalBeamEnergy) + 10.0
        with caplog.at_level(logging.WARNING):
            du.repeat_layer_spots(2)
        assert "do not decrease" in caplog.text


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
