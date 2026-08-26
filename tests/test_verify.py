"""
Tests for dicomfix.verify, the independent rescale check.

The point of these tests is not that the verifier passes on good plans -- the rest of
the suite already exercises that, since the check runs on every rescale. The point is
that it *fails* on bad ones. A safety check that never fires is worse than none,
because it manufactures confidence.

Each test below corrupts a plan in one specific way and asserts the verifier catches it.
"""
import ast
from pathlib import Path

import pytest

from dicomfix.dicomutil import MU_MIN, DicomUtil
from dicomfix.verify import (
    DEFAULT_TOLERANCE,
    RescaleVerificationError,
    snapshot,
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


class TestTolerance:
    def test_error_just_inside_tolerance_passes(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        rb = referenced_beam(du)
        rb.BeamMeterset = float(rb.BeamMeterset) * (1.0 + DEFAULT_TOLERANCE * 0.5)
        verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_error_outside_tolerance_fails(self, du):
        before = snapshot(du.dicom)
        du.apply_rescale_factor(2.0)
        rb = referenced_beam(du)
        rb.BeamMeterset = float(rb.BeamMeterset) * (1.0 + DEFAULT_TOLERANCE * 10.0)
        with pytest.raises(RescaleVerificationError):
            verify_rescale(before, du.dicom, 2.0, mu_min=MU_MIN)

    def test_default_tolerance_is_one_per_mille(self):
        assert DEFAULT_TOLERANCE == pytest.approx(1.0e-3)


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
