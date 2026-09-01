"""
CLI integration tests for dicomfix.main

Each test exercises one (or a few) CLI option(s) that are not covered by
test_process.py, verifying both that the command runs and that the resulting
DICOM file reflects the requested change.
"""
import subprocess
from pathlib import Path

import pytest

import dicomfix.main
from dicomfix.dicomutil import DicomUtil

PLAN_FILE = Path('res', 'Plan5.5.dcm')


def inspect_output(dcm_path):
    """Return the inspect output for a saved DICOM file."""
    result = subprocess.run(
        ["python", "-m", "dicomfix.main", str(dcm_path), "-i"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Plan metadata
# ---------------------------------------------------------------------------

def test_approve(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-a', '-o', str(out)])
    assert "APPROVED" in inspect_output(out)


def test_intent_curative(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-ic', '-o', str(out)])
    du = DicomUtil(str(out))
    assert du.dicom.PlanIntent == "CURATIVE"


def test_set_patient_name(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-pn', 'John Doe', '-o', str(out)])
    assert "John Doe" in inspect_output(out)


def test_set_plan_label(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-pl', 'MyLabel', '-o', str(out)])
    assert "MyLabel" in inspect_output(out)


def test_set_reviewer_name(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rn', 'Dr. Smith', '-o', str(out)])
    du = DicomUtil(str(out))
    assert du.dicom.ReviewerName == "Dr. Smith"


def test_set_treatment_machine(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-tm', 'TR4', '-o', str(out)])
    assert "TR4" in inspect_output(out)


def test_set_date(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-dt', '-o', str(out)])
    assert out.is_file()


# ---------------------------------------------------------------------------
# Dose / MU rescaling
# ---------------------------------------------------------------------------

def test_rescale_dose_to_10(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rd=10.0', '-o', str(out)])
    assert "Beam Dose                : 10.00 Gy(RBE)" in inspect_output(out)


def test_rescale_minimize_produces_valid_file(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rm', '-o', str(out)])
    assert out.is_file()
    assert out.stat().st_size > 0


def test_rescale_minimize_no_spot_below_1mu(tmp_path):
    from dicomfix.dicomutil import MU_MIN
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rm', '-o', str(out)])
    du = DicomUtil(str(out))
    for j, ib in enumerate(du.dicom.IonBeamSequence):
        beam_meterset = du.dicom.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
        mspw = beam_meterset / ib.FinalCumulativeMetersetWeight
        for icp in ib.IonControlPointSequence:
            ms = icp.ScanSpotMetersetWeights
            weights = list(ms) if hasattr(ms, '__iter__') else [ms]
            for w in weights:
                if float(w) > 0.0:
                    assert float(w) * mspw >= MU_MIN - 1e-6


# ---------------------------------------------------------------------------
# Positioning
# ---------------------------------------------------------------------------

def test_snout_position(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-sp=42.1', '-o', str(out)])
    assert "Snout Position" in inspect_output(out)
    du = DicomUtil(str(out))
    for ib in du.dicom.IonBeamSequence:
        assert ib.IonControlPointSequence[0].SnoutPosition == pytest.approx(421.0)


def test_table_position(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-tp=1.0,2.0,-0.5', '-o', str(out)])
    du = DicomUtil(str(out))
    icp = du.dicom.IonBeamSequence[0].IonControlPointSequence[0]
    assert icp.TableTopVerticalPosition == pytest.approx(10.0)
    assert icp.TableTopLongitudinalPosition == pytest.approx(20.0)
    assert icp.TableTopLateralPosition == pytest.approx(-5.0)


def test_gantry_angle_single_field(tmp_path):
    out = tmp_path / "out.dcm"
    # Determine field count so we pass the right number of angles
    du_in = DicomUtil(str(PLAN_FILE))
    nf = len(du_in.dicom.IonBeamSequence)
    angles_str = ",".join(["90.0"] * nf)
    dicomfix.main.main([str(PLAN_FILE), f'-g={angles_str}', '-o', str(out)])
    du = DicomUtil(str(out))
    for ib in du.dicom.IonBeamSequence:
        assert ib.IonControlPointSequence[0].GantryAngle == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Range shifter
# ---------------------------------------------------------------------------

def test_range_shifter_rs2(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rh=RS2', '-o', str(out)])
    du = DicomUtil(str(out))
    for ib in du.dicom.IonBeamSequence:
        assert ib.RangeShifterSequence[0].RangeShifterID == "RS_2CM"


def test_range_shifter_rs5(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rh=RS5', '-o', str(out)])
    du = DicomUtil(str(out))
    for ib in du.dicom.IonBeamSequence:
        assert ib.RangeShifterSequence[0].RangeShifterID == "RS_5CM"


def test_range_shifter_none(tmp_path):
    """-rh=None must actually strip the range shifter (issue #43)."""
    # PLAN_FILE has no range shifter to begin with, so add one first.
    with_rs = tmp_path / "with_rs.dcm"
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rh=RS2', '-o', str(with_rs)])
    dicomfix.main.main([str(with_rs), '-rh=None', '-o', str(out)])
    du = DicomUtil(str(out))
    for ib in du.dicom.IonBeamSequence:
        assert not hasattr(ib, "RangeShifterSequence")
        assert ib.NumberOfRangeShifters == 0
        for ics in ib.IonControlPointSequence:
            assert not hasattr(ics, "RangeShifterSettingsSequence")


# ---------------------------------------------------------------------------
# Field manipulation
# ---------------------------------------------------------------------------

def test_duplicate_fields_doubles_count(tmp_path):
    out = tmp_path / "out.dcm"
    orig_count = DicomUtil(str(PLAN_FILE)).dicom.FractionGroupSequence[0].NumberOfBeams
    dicomfix.main.main([str(PLAN_FILE), '-d=2', '-o', str(out)])
    du = DicomUtil(str(out))
    assert du.dicom.FractionGroupSequence[0].NumberOfBeams == orig_count * 2


# ---------------------------------------------------------------------------
# Layer spot repetition
# ---------------------------------------------------------------------------

def test_repeat_layer_extends_the_spot_list(tmp_path):
    out = tmp_path / "out.dcm"
    ib_in = DicomUtil(str(PLAN_FILE)).dicom.IonBeamSequence[0]
    spots = ib_in.IonControlPointSequence[0].NumberOfScanSpotPositions
    dicomfix.main.main([str(PLAN_FILE), '-rl=3', '-rld=20', '-o', str(out)])
    ib = DicomUtil(str(out)).dicom.IonBeamSequence[0]
    assert ib.IonControlPointSequence[0].NumberOfScanSpotPositions == spots * 3 + 2
    # The layer structure is what keeps the plan deliverable, so it must be untouched.
    assert ib.NumberOfControlPoints == ib_in.NumberOfControlPoints
    assert [float(icp.NominalBeamEnergy) for icp in ib.IonControlPointSequence] == \
           [float(icp.NominalBeamEnergy) for icp in ib_in.IonControlPointSequence]


def test_repeat_layer_meterset(tmp_path):
    out = tmp_path / "out.dcm"
    d_in = DicomUtil(str(PLAN_FILE)).dicom
    orig_mu = float(d_in.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)
    layers = len(d_in.IonBeamSequence[0].IonControlPointSequence) // 2
    dicomfix.main.main([str(PLAN_FILE), '-rl=3', '-rld=20', '-o', str(out)])
    rb = DicomUtil(str(out)).dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
    assert float(rb.BeamMeterset) == pytest.approx(orig_mu * 3 + layers * 2 * 20.0)


def test_repeat_layer_after_rescale(tmp_path):
    """-rf must scale one pass, then -rl repeats it: MU x2 x3, not x2 twice."""
    out = tmp_path / "out.dcm"
    orig_mu = float(DicomUtil(str(PLAN_FILE)).dicom
                    .FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)
    dicomfix.main.main([str(PLAN_FILE), '-rf=2', '-rl=3', '-o', str(out)])
    rb = DicomUtil(str(out)).dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
    assert float(rb.BeamMeterset) == pytest.approx(orig_mu * 6)


@pytest.mark.parametrize("delay", ['-rld=20', '-rld=0'])
def test_delay_without_repeat_layer_is_refused(tmp_path, delay):
    """Including -rld=0: an invalid delay, but the option was still given without -rl."""
    out = tmp_path / "out.dcm"
    with pytest.raises(ValueError, match="repeat_layer"):
        dicomfix.main.main([str(PLAN_FILE), delay, '-o', str(out)])


def test_minimize_current_appends_one_mu_spot(tmp_path):
    from dicomfix.dicomutil import MU_MIN, OFF_AXIS_SPOT_POSITION
    out = tmp_path / "out.dcm"
    d_in = DicomUtil(str(PLAN_FILE)).dicom
    spots = d_in.IonBeamSequence[0].IonControlPointSequence[0].NumberOfScanSpotPositions
    layers = len(d_in.IonBeamSequence[0].IonControlPointSequence) // 2
    orig_mu = float(d_in.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset)

    dicomfix.main.main([str(PLAN_FILE), '-mc', '-o', str(out)])
    d = DicomUtil(str(out)).dicom
    icp = d.IonBeamSequence[0].IonControlPointSequence[0]
    assert icp.NumberOfScanSpotPositions == spots + 1
    assert list(icp.ScanSpotPositionMap)[-2:] == list(OFF_AXIS_SPOT_POSITION)
    rb = d.FractionGroupSequence[0].ReferencedBeamSequence[0]
    assert float(rb.BeamMeterset) == pytest.approx(orig_mu + layers * MU_MIN)


def test_minimize_current_with_repeat_layer(tmp_path):
    """One dummy spot per layer, not one per pass."""
    out = tmp_path / "out.dcm"
    spots = DicomUtil(str(PLAN_FILE)).dicom.IonBeamSequence[0] \
        .IonControlPointSequence[0].NumberOfScanSpotPositions
    dicomfix.main.main([str(PLAN_FILE), '-rl=3', '-rld=20', '-mc', '-o', str(out)])
    icp = DicomUtil(str(out)).dicom.IonBeamSequence[0].IonControlPointSequence[0]
    assert icp.NumberOfScanSpotPositions == spots * 3 + 2 + 1


def test_repeat_layer_with_repainting_is_refused(tmp_path):
    """One divides the layer MU, the other multiplies it."""
    out = tmp_path / "out.dcm"
    with pytest.raises(ValueError, match="repainting"):
        dicomfix.main.main([str(PLAN_FILE), '-rl=3', '-rp=2', '-o', str(out)])


# ---------------------------------------------------------------------------
# Tolerance table
# ---------------------------------------------------------------------------

def test_tolerance_table_added(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-tt', '-o', str(out)])
    du = DicomUtil(str(out))
    assert hasattr(du.dicom, "IonToleranceTableSequence")
    assert du.dicom.IonToleranceTableSequence[0].ToleranceTableLabel == "T1"


# ---------------------------------------------------------------------------
# RayStation fix
# ---------------------------------------------------------------------------

def test_fix_raystation_sets_manufacturer(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rs', '-o', str(out)])
    du = DicomUtil(str(out))
    assert du.dicom.Manufacturer == "Varian Medical System Particle Therapy"


def test_fix_raystation_manufacturer_in_inspect(tmp_path):
    out = tmp_path / "out.dcm"
    dicomfix.main.main([str(PLAN_FILE), '-rs', '-o', str(out)])
    assert "Varian Medical System Particle Therapy" in inspect_output(out)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_racehorse_creates_csv(tmp_path):
    out_dcm = tmp_path / "out.dcm"
    export_base = str(tmp_path / "spots")
    dicomfix.main.main([str(PLAN_FILE), '-e', export_base, '-o', str(out_dcm)])
    csv_files = list(tmp_path.glob("*.csv"))
    assert len(csv_files) > 0


def test_export_racehorse_csv_content(tmp_path):
    out_dcm = tmp_path / "out.dcm"
    export_base = str(tmp_path / "spots")
    dicomfix.main.main([str(PLAN_FILE), '-e', export_base, '-o', str(out_dcm)])
    csv_files = list(tmp_path.glob("*.csv"))
    content = csv_files[0].read_text()
    assert "#HEADER" in content
    assert "Index;Position x;Position y;Dose" in content
