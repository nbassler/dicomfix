"""
Tests for dicomfix.verify, the independent rescale check.

The point of these tests is not that the verifier passes on good plans -- the rest of
the suite already exercises that, since the check runs on every rescale. The point is
that it *fails* on bad ones. A safety check that never fires is worse than none,
because it manufactures confidence.

Each test below corrupts a plan in one specific way and asserts the verifier catches it.
"""
import ast
import copy
from pathlib import Path

import pytest

from dicomfix.dicomutil import MU_MIN, DicomUtil
from dicomfix.verify import (
    GEOMETRY_TOLERANCE,
    METERSET_TOLERANCE,
    UNIFORMITY_TOLERANCE,
    PlanVerificationError,
    RescaleVerificationError,
    snapshot,
    verify_layer_repeat,
    verify_rescale,
)

PLAN_FILE = Path('res', 'Plan5.5.dcm')


@pytest.fixture
def du():
    return DicomUtil(str(PLAN_FILE))


def first_beam(du):
    return du.dicom.IonBeamSequence[0]


def referenced_beam(du):
    return du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]


class TestPassesOnGoodPlans:
    @pytest.mark.parametrize("factor", [0.5, 1.0, 2.0, 13.7])
    def test_honest_rescale_passes(self, du, factor):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(factor)
        verify_rescale(before, du.dicom, factor, mu_min=MU_MIN)

    def test_passes_when_spots_eliminated(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(0.05)          # discards spots
        assert du.spots_discarded > 0
        verify_rescale(before, du.dicom, 0.05, mu_min=MU_MIN)


class TestCatchesCorruption:
    """Each case injects one fault and asserts the verifier refuses the plan."""

    def test_catches_wrong_beam_meterset(self, du):
        """Caught as a total-meterset mismatch, not an internal inconsistency.

        Per-spot MU is derived from BeamMeterset, so inflating it scales every spot with
        it and the plan stays self-consistent. What gives it away is the comparison
        against the requested factor.
        """
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        referenced_beam(du).BeamMeterset = float(referenced_beam(du).BeamMeterset) * 1.05
        with pytest.raises(RescaleVerificationError, match="total meterset"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_wrong_beam_dose(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        referenced_beam(du).BeamDose = float(referenced_beam(du).BeamDose) * 1.05
        with pytest.raises(RescaleVerificationError, match="BeamDose"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_wrong_prescription_dose(self, du):
        du.dicom.DoseReferenceSequence[0].TargetPrescriptionDose = 5.5
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        du.dicom.DoseReferenceSequence[0].TargetPrescriptionDose = 999.0
        with pytest.raises(RescaleVerificationError, match="TargetPrescriptionDose"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_moved_spot(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        pos = list(icp.ScanSpotPositionMap)
        pos[0] = float(pos[0]) + 5.0                  # nudge one spot by 5 mm
        icp.ScanSpotPositionMap = pos
        with pytest.raises(RescaleVerificationError, match="positions"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_sub_dose_tolerance_spot_shift(self, du):
        """A shift too small for the dose tolerance must still be caught.

        Rescaling never touches positions, so any movement is a bug regardless of size.
        This perturbation is well inside METERSET_TOLERANCE and would have passed while
        the geometry checks shared it.
        """
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        pos = [float(p) for p in icp.ScanSpotPositionMap]
        moved = next(i for i, p in enumerate(pos) if abs(p) > 1.0)
        pos[moved] *= (1.0 + METERSET_TOLERANCE * 0.5)   # half the dose tolerance
        icp.ScanSpotPositionMap = pos
        with pytest.raises(RescaleVerificationError, match="positions"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_sub_dose_tolerance_energy_change(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        icp.NominalBeamEnergy = float(icp.NominalBeamEnergy) * (1.0 + METERSET_TOLERANCE * 0.5)
        with pytest.raises(RescaleVerificationError, match="energies"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_changed_energy(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        icp.NominalBeamEnergy = float(icp.NominalBeamEnergy) + 10.0
        with pytest.raises(RescaleVerificationError, match="energies"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_uneven_spot_scaling(self, du):
        """The subtle one: totals still add up, but one spot got its own factor."""
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        weights = [float(w) for w in icp.ScanSpotMetersetWeights]
        biggest = max(range(len(weights)), key=lambda i: weights[i])
        smallest = min(range(len(weights)), key=lambda i: weights[i] if weights[i] > 0 else 1e30)
        # move meterset between two spots, leaving the beam total untouched
        moved = weights[biggest] * 0.10
        weights[biggest] -= moved
        weights[smallest] += moved
        icp.ScanSpotMetersetWeights = weights
        with pytest.raises(RescaleVerificationError, match="unevenly|reshaped"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_uneven_scaling_below_meterset_tolerance(self, du):
        """Unevenness far too small to move the total must still be caught.

        This is what the separate UNIFORMITY_TOLERANCE buys: DS rounding shifts a whole
        beam together, so the spread stays near machine epsilon and can be policed much
        more tightly than the magnitude. Here one spot is perturbed by a tenth of
        METERSET_TOLERANCE, invisible in the total but a reshaped distribution.
        """
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        weights = [float(w) for w in icp.ScanSpotMetersetWeights]
        target = max(range(len(weights)), key=lambda i: weights[i])
        weights[target] *= (1.0 + METERSET_TOLERANCE * 0.1)
        icp.ScanSpotMetersetWeights = weights
        with pytest.raises(RescaleVerificationError, match="unevenly|reshaped"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_spots_losing_meterset_to_others(self, du):
        """Some survivors lose MU while others gain it, keeping the beam total intact.

        The 'lost meterset' check must fire on its own here. Testing max(ratios) would
        let the gainers mask the losers and leave only the evenness check complaining.
        """
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        weights = [float(w) for w in icp.ScanSpotMetersetWeights]
        live = [i for i, w in enumerate(weights) if w > 0]
        half = len(live) // 2
        # halve the first half, and give exactly that MU to the second half
        moved = sum(weights[i] * 0.5 for i in live[:half])
        for i in live[:half]:
            weights[i] *= 0.5
        for i in live[half:]:
            weights[i] += moved / len(live[half:])
        icp.ScanSpotMetersetWeights = weights

        with pytest.raises(RescaleVerificationError) as excinfo:
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)
        assert "lost meterset" in str(excinfo.value)

    def test_catches_wrong_factor_applied(self, du):
        """Plan is internally consistent, but scaled by 2.0 when 3.0 was requested."""
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        with pytest.raises(RescaleVerificationError, match="total meterset"):
            verify_rescale(before, du.dicom, 3.0, mu_min=MU_MIN)

    def test_catches_negative_meterset(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        referenced_beam(du).BeamMeterset = -float(referenced_beam(du).BeamMeterset)
        with pytest.raises(RescaleVerificationError, match="negative"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_catches_undeliverable_surviving_spot(self, du):
        """A spot left below MU_MIN would be undeliverable dust."""
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        icp = first_beam(du).IonControlPointSequence[0]
        weights = [float(w) for w in icp.ScanSpotMetersetWeights]
        nonzero = next(i for i, w in enumerate(weights) if w > 0)
        weights[nonzero] = 1e-9                       # tiny but not zero
        icp.ScanSpotMetersetWeights = weights
        with pytest.raises(RescaleVerificationError, match="below"):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)


class TestOptionalEnergyTag:
    """NominalBeamEnergy is type 1C: it may be omitted where the energy does not change."""

    def test_snapshot_carries_energy_forward(self, du):
        icps = first_beam(du).IonControlPointSequence
        expected = float(icps[1].NominalBeamEnergy)
        del icps[1].NominalBeamEnergy
        assert snapshot(du.dicom)["beams"][0]["energies"][1] == pytest.approx(expected)

    def test_rescale_of_plan_without_repeated_energy_tags(self, du):
        """Reading the tag directly raised AttributeError on plans written this way."""
        for icp in first_beam(du).IonControlPointSequence[1:]:
            del icp.NominalBeamEnergy
        du.apply_rescale_factor(2.0)           # verifies internally

    def test_repeat_layers_of_plan_without_repeated_energy_tags(self, du):
        for icp in first_beam(du).IonControlPointSequence[1:]:
            del icp.NominalBeamEnergy
        du.repeat_layers(3)                    # verifies internally

    def test_missing_energy_on_first_control_point_is_malformed(self, du):
        del first_beam(du).IonControlPointSequence[0].NominalBeamEnergy
        with pytest.raises(ValueError, match="Malformed plan"):
            snapshot(du.dicom)


class TestMalformedPlans:
    """A malformed plan must be named as such, not surface as a bare IndexError."""

    def test_more_ion_beams_than_referenced_beams(self, du):
        d = du.dicom
        d.IonBeamSequence.append(copy.deepcopy(d.IonBeamSequence[0]))
        d.IonBeamSequence[1].BeamNumber = 2
        with pytest.raises(ValueError, match="Malformed plan"):
            snapshot(d)

    def test_more_referenced_beams_than_ion_beams(self, du):
        rbs = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence
        rbs.append(copy.deepcopy(rbs[0]))
        rbs[1].ReferencedBeamNumber = 2
        with pytest.raises(ValueError, match="Malformed plan"):
            snapshot(du.dicom)

    def test_mismatch_reports_both_lengths(self, du):
        d = du.dicom
        d.IonBeamSequence.append(copy.deepcopy(d.IonBeamSequence[0]))
        with pytest.raises(ValueError, match=r"2 field\(s\).*ReferencedBeamSequence has 1"):
            snapshot(d)

    def test_rescale_of_malformed_plan_names_the_problem(self, du):
        """The message must reach the caller of apply_rescale_factor, not an IndexError."""
        d = du.dicom
        d.IonBeamSequence.append(copy.deepcopy(d.IonBeamSequence[0]))
        with pytest.raises(ValueError, match="Malformed plan"):
            du.apply_rescale_factor(2.0)


class TestTolerance:
    def test_error_just_inside_tolerance_passes(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        rb = referenced_beam(du)
        rb.BeamMeterset = float(rb.BeamMeterset) * (1.0 + METERSET_TOLERANCE * 0.5)
        verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_error_outside_tolerance_fails(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        rb = referenced_beam(du)
        rb.BeamMeterset = float(rb.BeamMeterset) * (1.0 + METERSET_TOLERANCE * 10.0)
        with pytest.raises(RescaleVerificationError):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_meterset_tolerance_is_ten_ppm(self):
        assert METERSET_TOLERANCE == pytest.approx(1.0e-5)

    def test_tolerances_are_ordered_by_how_much_noise_each_absorbs(self):
        """Magnitude absorbs DS rounding; spread does not; geometry has no noise at all."""
        assert GEOMETRY_TOLERANCE < UNIFORMITY_TOLERANCE < METERSET_TOLERANCE

    @pytest.mark.parametrize("factor", [0.05, 0.5, 2.0, 1000.0])
    def test_uniformity_holds_with_large_margin(self, du, factor):
        """The premise behind UNIFORMITY_TOLERANCE: real spread is machine epsilon."""
        before = snapshot(du.dicom)
        du.apply_rescale_factor(factor)
        after = snapshot(du.dicom)
        for b, a in zip(before["beams"], after["beams"]):
            ratios = [x / (y * factor) for x, y in zip(a["spot_mu"], b["spot_mu"])
                      if x > 1e-12 and y > 1e-12]
            assert max(ratios) - min(ratios) < UNIFORMITY_TOLERANCE / 1000.0

    def test_geometry_tolerance_is_tighter_than_meterset_tolerance(self):
        """Positions and energies are never rescaled, so they get near-exact treatment.

        METERSET_TOLERANCE has to absorb DS decimal-string rounding; geometry does not,
        because those values pass through untouched.
        """
        assert GEOMETRY_TOLERANCE < METERSET_TOLERANCE
        assert GEOMETRY_TOLERANCE <= 1.0e-12

    @pytest.mark.parametrize("factor", [0.05, 0.5, 2.0, 1000.0])
    def test_geometry_is_bit_identical_after_rescale(self, du, factor):
        """The premise behind GEOMETRY_TOLERANCE: rescaling leaves these untouched."""
        before = snapshot(du.dicom)
        du.apply_rescale_factor(factor)
        after = snapshot(du.dicom)
        for b, a in zip(before["beams"], after["beams"]):
            assert a["positions"] == b["positions"]
            assert a["energies"] == b["energies"]


class TestLayerRepeat:
    """Same principle as above: each case breaks one property of a repeated plan."""

    @pytest.mark.parametrize("repeats", [2, 3, 25])
    def test_honest_repetition_passes(self, du, repeats):
        before = snapshot(du.dicom)
        du.repeat_layers(repeats)
        verify_layer_repeat(before, du.dicom, repeats)

    def test_catches_wrong_repetition_count(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        with pytest.raises(PlanVerificationError, match="spot count"):
            verify_layer_repeat(before, du.dicom, 3)

    def test_catches_perturbed_spot_meterset(self, du):
        """A repetition which does not deliver the original MU is not a repetition."""
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        icp = first_beam(du).IonControlPointSequence[0]
        weights = [float(w) for w in icp.ScanSpotMetersetWeights]
        weights[0] *= 1.1
        icp.ScanSpotMetersetWeights = weights
        with pytest.raises(PlanVerificationError, match="original meterset"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_unscaled_beam_meterset(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        referenced_beam(du).BeamMeterset = before["beams"][0]["beam_meterset"]
        with pytest.raises(PlanVerificationError, match="BeamMeterset"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_unscaled_beam_dose(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        referenced_beam(du).BeamDose = before["beams"][0]["beam_dose"]
        with pytest.raises(PlanVerificationError, match="BeamDose"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_moved_spot(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        icp = first_beam(du).IonControlPointSequence[0]
        positions = [float(p) for p in icp.ScanSpotPositionMap]
        positions[0] += 5.0
        icp.ScanSpotPositionMap = positions
        with pytest.raises(PlanVerificationError, match="positions"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_stale_number_of_control_points(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        first_beam(du).NumberOfControlPoints = 16
        with pytest.raises(PlanVerificationError, match="NumberOfControlPoints"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_unrenumbered_control_point_indices(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        first_beam(du).IonControlPointSequence[-1].ControlPointIndex = 0
        with pytest.raises(PlanVerificationError, match="indices"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_non_monotonic_cumulative_weight(self, du):
        """What a naive expansion produces: cumulative weights restarting each repetition."""
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        icps = first_beam(du).IonControlPointSequence
        icps[len(icps) // 2].CumulativeMetersetWeight = 0.0
        with pytest.raises(PlanVerificationError, match="monotonically increasing"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_cumulative_weight_short_of_final(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        ib = first_beam(du)
        ib.FinalCumulativeMetersetWeight = float(ib.FinalCumulativeMetersetWeight) * 1.5
        with pytest.raises(PlanVerificationError, match="FinalCumulativeMetersetWeight"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_catches_dose_reference_coefficient_not_reaching_one(self, du):
        before = snapshot(du.dicom)
        du.repeat_layers(2)
        icps = first_beam(du).IonControlPointSequence
        icps[-1].ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient = 0.5
        with pytest.raises(PlanVerificationError, match="dose reference coefficient"):
            verify_layer_repeat(before, du.dicom, 2)

    def test_rescale_error_is_a_plan_error(self):
        """GUI and callers catch the base class, so this relationship has to hold."""
        assert issubclass(RescaleVerificationError, PlanVerificationError)


class TestIndependence:
    def test_verify_does_not_import_dicomutil(self):
        """The check is only meaningful if it shares no code with what it checks.

        Parsed rather than grepped, so the module's own prose about dicomutil does not
        make this pass or fail spuriously.
        """
        tree = ast.parse(Path('dicomfix', 'verify.py').read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(f"{node.module}.{a.name}" for a in node.names)
        assert not any("dicomutil" in name for name in imported), \
            f"verify.py must not depend on the code it verifies, found: {sorted(imported)}"

    def test_verify_does_not_modify_the_plan(self, du):
        du.apply_rescale_factor(2.0)
        before = snapshot(du.dicom)
        verify_rescale(before, du.dicom, 1.0, mu_min=MU_MIN)
        assert snapshot(du.dicom) == before
