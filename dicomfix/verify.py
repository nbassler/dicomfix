"""
Independent verification of rescaling operations.

This module is a deliberate second opinion. After dicomutil rescales a plan, the
functions here recompute what the plan now delivers straight from its DICOM tags,
using their own arithmetic, and check that it matches what was asked for.

Two rules keep this useful, and both matter more than they look:

1. **Nothing here may import from dicomfix.dicomutil.** If this module reused the
   helpers that performed the rescale, a bug in those helpers would be invisible to
   it and the check would confirm nothing. The duplication is the point.

2. **Nothing here may modify the plan.** This module only reads.

The quantity checked is monitor units per spot, because that is what the machine
delivers. A plan can carry a perfectly correct BeamMeterset while the per-spot
distribution underneath it is wrong.

Default tolerance is 0.1% relative. Measured deviation on a real plan, including a
save/reload round-trip, is ~6e-10, so this leaves a very wide margin against false
alarms while still catching any error big enough to matter.
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 1.0e-3  # 0.1% relative


class RescaleVerificationError(Exception):
    """Raised when a rescaled plan does not match what was requested.

    This means the plan in memory is not trustworthy and must not be delivered.
    """


def _spot_weights(icp):
    """Scan spot meterset weights of one control point, always as a list of float."""
    weights = icp.ScanSpotMetersetWeights
    if icp.NumberOfScanSpotPositions == 1:
        return [float(weights)]
    return [float(w) for w in weights]


def snapshot(dicom):
    """
    Capture what a plan delivers, computed from its DICOM tags alone.

    Args:
        dicom (pydicom.Dataset): The plan to measure. It is not modified.

    Returns:
        dict: Per-beam measurements suitable for passing to verify_rescale().
    """
    beams = []
    for j, ib in enumerate(dicom.IonBeamSequence):
        rb = dicom.FractionGroupSequence[0].ReferencedBeamSequence[j]
        final_weight = float(ib.FinalCumulativeMetersetWeight)
        beam_meterset = float(rb.BeamMeterset)
        # MU delivered by a spot = its weight, scaled by the beam's MU per unit weight.
        meterset_per_weight = beam_meterset / final_weight if final_weight else 0.0

        spot_mu, positions, energies = [], [], []
        for icp in ib.IonControlPointSequence:
            spot_mu += [w * meterset_per_weight for w in _spot_weights(icp)]
            positions += [float(p) for p in icp.ScanSpotPositionMap]
            energies.append(float(icp.NominalBeamEnergy))

        beams.append({
            "spot_mu": spot_mu,
            "positions": positions,
            "energies": energies,
            "beam_meterset": beam_meterset,
            "beam_dose": float(rb.BeamDose) if "BeamDose" in rb else None,
        })

    prescriptions = [float(dr.TargetPrescriptionDose)
                     for dr in dicom.get("DoseReferenceSequence", [])
                     if "TargetPrescriptionDose" in dr]

    return {"beams": beams, "prescriptions": prescriptions}


def _check(ok, failures, message):
    if not ok:
        failures.append(message)


def _close(a, b, tolerance):
    """Relative comparison, falling back to absolute near zero."""
    scale = max(abs(a), abs(b))
    if scale < 1.0e-12:
        return abs(a - b) < 1.0e-12
    return abs(a - b) / scale <= tolerance


def _integrity_failures(dicom, before, mu_min, tolerance):
    """Checks that must hold after any rescale, uniform factor or per-layer alike."""
    after = snapshot(dicom)
    failures = []

    _check(len(after["beams"]) == len(before["beams"]), failures,
           f"field count changed: {len(before['beams'])} -> {len(after['beams'])}")

    for j, (b, a) in enumerate(zip(before["beams"], after["beams"])):
        where = f"field {j}"

        _check(len(a["spot_mu"]) == len(b["spot_mu"]), failures,
               f"{where}: spot count changed: {len(b['spot_mu'])} -> {len(a['spot_mu'])}")
        _check(len(a["positions"]) == len(b["positions"])
               and all(_close(x, y, tolerance) for x, y in zip(a["positions"], b["positions"])),
               failures, f"{where}: spot positions were modified by rescaling")
        _check(len(a["energies"]) == len(b["energies"])
               and all(_close(x, y, tolerance) for x, y in zip(a["energies"], b["energies"])),
               failures, f"{where}: beam energies were modified by rescaling")
        _check(all(mu >= 0.0 for mu in a["spot_mu"]), failures,
               f"{where}: plan contains negative spot meterset")

        # Declared BeamMeterset must agree with the spots underneath it, or the plan lies
        # about what it delivers.
        got_total = sum(a["spot_mu"])
        _check(_close(got_total, a["beam_meterset"], tolerance), failures,
               f"{where}: BeamMeterset {a['beam_meterset']:.6f} MU disagrees with the "
               f"sum of its spots, {got_total:.6f} MU")

        if mu_min is not None:
            too_small = [mu for mu in a["spot_mu"] if 0.0 < mu < mu_min * (1.0 - tolerance)]
            _check(not too_small, failures,
                   f"{where}: {len(too_small)} spot(s) below {mu_min} MU survived rescaling")

    return after, failures


def _scaling_failures(before, after, rescale_factor, tolerance):
    """Checks specific to a single uniform rescale factor."""
    failures = []

    for j, (b, a) in enumerate(zip(before["beams"], after["beams"])):
        where = f"field {j}"

        # Plan total must match the request, discards included.
        want_total = sum(b["spot_mu"]) * rescale_factor
        got_total = sum(a["spot_mu"])
        _check(_close(got_total, want_total, tolerance), failures,
               f"{where}: total meterset {got_total:.6f} MU, expected {want_total:.6f} MU")

        # Every surviving spot must be off the requested scaling by the same ratio.
        ratios = [x / (y * rescale_factor)
                  for x, y in zip(a["spot_mu"], b["spot_mu"])
                  if x > 1.0e-12 and y > 1.0e-12]
        if ratios:
            spread = max(ratios) - min(ratios)
            _check(spread <= tolerance, failures,
                   f"{where}: surviving spots were rescaled unevenly "
                   f"(ratio spread {spread:.3e}), the delivered pattern has been reshaped")
            _check(max(ratios) >= 1.0 - tolerance, failures,
                   f"{where}: surviving spots lost meterset (ratio {min(ratios):.6f})")

        if b["beam_dose"] is not None and a["beam_dose"] is not None:
            want = b["beam_dose"] * rescale_factor
            _check(_close(a["beam_dose"], want, tolerance), failures,
                   f"{where}: BeamDose {a['beam_dose']:.6f}, expected {want:.6f} Gy(RBE)")

    _check(len(after["prescriptions"]) == len(before["prescriptions"]), failures,
           "number of target prescription doses changed")
    for i, (b_dose, a_dose) in enumerate(zip(before["prescriptions"], after["prescriptions"])):
        want = b_dose * rescale_factor
        _check(_close(a_dose, want, tolerance), failures,
               f"dose reference {i}: TargetPrescriptionDose {a_dose:.6f}, "
               f"expected {want:.6f} Gy(RBE)")

    return failures


def verify_rescale(before, dicom, rescale_factor=None, mu_min=None, tolerance=DEFAULT_TOLERANCE):
    """
    Check that a rescaled plan delivers what was requested.

    Recomputes the plan's delivered MU from its tags and compares against the
    pre-rescale snapshot. Spots dropped for falling below mu_min are accounted for:
    their MU is redistributed over the survivors, so the plan total is checked
    exactly while surviving spots are required to share one common ratio (a varying
    ratio would mean the delivered pattern was reshaped).

    Args:
        before (dict): Result of snapshot() taken before the rescale.
        dicom (pydicom.Dataset): The plan after rescaling. It is not modified.
        rescale_factor (float, optional): The uniform factor that was requested. Pass
            None when per-layer factors were used, since no single factor applies then;
            the integrity checks still run.
        mu_min (float, optional): Minimum deliverable MU. When given, surviving spots
            are checked to be at or above it.
        tolerance (float): Relative tolerance. Defaults to 0.1%.

    Raises:
        RescaleVerificationError: If any check fails. The message lists every failure.
    """
    after, failures = _integrity_failures(dicom, before, mu_min, tolerance)

    if rescale_factor is not None:
        failures += _scaling_failures(before, after, rescale_factor, tolerance)

    if failures:
        raise RescaleVerificationError(
            f"Rescale verification FAILED for factor {rescale_factor} "
            f"(tolerance {tolerance:.1e}). This plan must not be delivered:\n  - "
            + "\n  - ".join(failures))

    scope = "integrity only (per-layer factors)" if rescale_factor is None else \
        f"factor {rescale_factor:.6f}"
    logger.info(f"Rescale verified independently: {scope}, "
                f"tolerance {tolerance:.1e}, all checks passed.")
