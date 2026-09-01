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

Three tolerances, because the quantities differ in kind:

- METERSET_TOLERANCE (10 ppm) for the *magnitude* of what rescaling changes: total
  meterset, dose, prescription, and the per-spot level. This is the loosest of the
  three because DS decimal-string rounding lands here.
- UNIFORMITY_TOLERANCE (1e-9) for the *spread* of per-spot ratios. DS rounding moves a
  whole beam together, so it does not widen the spread, and this check stays near-exact.
- GEOMETRY_TOLERANCE (1e-12) for what rescaling must not touch at all: spot positions
  and beam energies.

All three were chosen from measurement, not taste; see the comment on each.
"""

import logging

logger = logging.getLogger(__name__)

# 10 ppm relative, for the magnitude of quantities rescaling changes: total meterset,
# BeamDose, TargetPrescriptionDose, and the per-spot level. Chosen from measurement, not
# taste: across 114 rescales on three plans (including two RayStation clinical plans)
# with factors from 0.02 to 500, the worst relative error observed was 1.6e-7, on a
# clinical plan at factor 111.6. Dose and meterset are DS (decimal string) VRs, so their
# precision comes from text formatting rather than float width, which is why the error is
# this large; the Eclipse sample plan is ~300x cleaner at 5.8e-10, so a plan's formatting
# matters more than its size. 1e-7 rejects 76 of those 114 legitimate rescales. This
# leaves ~64x margin over the noise floor while still catching anything above 0.001%,
# far below the percent-scale errors a real bug produces.
METERSET_TOLERANCE = 1.0e-5

# Applied to the *spread* of per-spot ratios rather than their magnitude. DS rounding
# shifts every spot in a beam by the same amount, so it moves the level without
# disturbing the spread: measured spread across the same sweep is 8.9e-16, machine
# epsilon. Keeping this tight preserves ~1e6 margin on the one check that detects a
# reshaped dose distribution, which totals cannot see.
UNIFORMITY_TOLERANCE = 1.0e-9

# Spot positions and beam energies are not rescaled at all, they pass through untouched,
# so any difference is a bug rather than rounding and the dose tolerance is far too loose
# for them. Measured deviation across factors from 0.05 to 1000, including a DICOM
# save/reload round-trip, is exactly zero; this is effectively an equality test with a
# margin against last-bit float noise.
GEOMETRY_TOLERANCE = 1.0e-12


class PlanVerificationError(Exception):
    """Raised when a modified plan does not match what was requested.

    This means the plan in memory is not trustworthy and must not be delivered.
    """


class RescaleVerificationError(PlanVerificationError):
    """Raised when a rescaled plan does not match what was requested."""


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

    Raises:
        ValueError: If the plan's beam sequences are inconsistent with each other.
    """
    referenced_beams = dicom.FractionGroupSequence[0].ReferencedBeamSequence

    # These two sequences are indexed in parallel here and throughout dicomutil. A
    # mismatch means the plan is malformed, and would otherwise surface as a bare
    # IndexError from whichever loop happened to reach it first.
    if len(dicom.IonBeamSequence) != len(referenced_beams):
        raise ValueError(
            f"Malformed plan: IonBeamSequence has {len(dicom.IonBeamSequence)} field(s) but "
            f"ReferencedBeamSequence has {len(referenced_beams)}. The plan cannot be verified.")

    beams = []
    for j, ib in enumerate(dicom.IonBeamSequence):
        rb = referenced_beams[j]
        final_weight = float(ib.FinalCumulativeMetersetWeight)
        beam_meterset = float(rb.BeamMeterset)
        # MU delivered by a spot = its weight, scaled by the beam's MU per unit weight.
        meterset_per_weight = beam_meterset / final_weight if final_weight else 0.0

        spot_mu, positions, energies = [], [], []
        energy = None
        for icp in ib.IonControlPointSequence:
            # NominalBeamEnergy is type 1C: a control point which does not change the
            # energy may omit it, and the previous control point's energy still applies.
            # Carrying it forward is what the machine does, and reading it directly
            # raises AttributeError on plans written that way.
            if "NominalBeamEnergy" in icp:
                energy = float(icp.NominalBeamEnergy)
            elif energy is None:
                raise ValueError(
                    f"Malformed plan: field {j} begins without a NominalBeamEnergy, so the "
                    "energy of its first control point is undefined. The plan cannot be verified.")
            spot_mu += [w * meterset_per_weight for w in _spot_weights(icp)]
            positions += [float(p) for p in icp.ScanSpotPositionMap]
            energies.append(energy)

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
        # GEOMETRY_TOLERANCE, not tolerance: rescaling must not touch these at all.
        _check(len(a["positions"]) == len(b["positions"])
               and all(_close(x, y, GEOMETRY_TOLERANCE)
                       for x, y in zip(a["positions"], b["positions"])),
               failures, f"{where}: spot positions were modified by rescaling")
        _check(len(a["energies"]) == len(b["energies"])
               and all(_close(x, y, GEOMETRY_TOLERANCE)
                       for x, y in zip(a["energies"], b["energies"])),
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
            # UNIFORMITY_TOLERANCE, not tolerance: DS rounding moves every spot in a beam
            # together, so it does not widen the spread. This check can stay near-exact.
            spread = max(ratios) - min(ratios)
            _check(spread <= UNIFORMITY_TOLERANCE, failures,
                   f"{where}: surviving spots were rescaled unevenly "
                   f"(ratio spread {spread:.3e}), the delivered pattern has been reshaped")
            # min, not max: with max, a beam where some spots lost MU and others gained
            # it would pass this check on the strength of the gainers alone. Only the
            # adjacent spread check would catch that, and these two must not depend on
            # each other -- each has to stand on its own.
            _check(min(ratios) >= 1.0 - tolerance, failures,
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


def verify_rescale(before, dicom, rescale_factor=None, mu_min=None, tolerance=METERSET_TOLERANCE):
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
        tolerance (float): Relative tolerance for rescaled quantities. Defaults to
            METERSET_TOLERANCE (1 ppm). Positions and energies always use
            GEOMETRY_TOLERANCE regardless of this.

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


def _tiled(block, gap, repeats):
    """One block per repetition, with the gap contents in each of the repeats-1 gaps."""
    out = []
    for repetition in range(repeats):
        out += block
        if repetition < repeats - 1:
            out += gap
    return out


def _sequence_failures(dicom):
    """Structural checks on the control point sequences of an expanded plan.

    Read straight off the dataset rather than from a snapshot: these are the tags which
    describe the *shape* of the sequence, and an expansion which gets the meterset right
    while leaving the sequence malformed is still undeliverable.
    """
    failures = []

    for j, ib in enumerate(dicom.IonBeamSequence):
        where = f"field {j}"
        icps = ib.IonControlPointSequence
        final_weight = float(ib.FinalCumulativeMetersetWeight)

        _check(int(ib.NumberOfControlPoints) == len(icps), failures,
               f"{where}: NumberOfControlPoints is {ib.NumberOfControlPoints} but the "
               f"sequence holds {len(icps)} control points")

        # Every check below reads the ends of the sequence. An empty one is a finding in
        # its own right, and this module has to report it rather than raise IndexError.
        if not icps:
            failures.append(f"{where}: control point sequence is empty")
            continue

        indices = [int(icp.ControlPointIndex) for icp in icps]
        _check(indices == list(range(len(icps))), failures,
               f"{where}: control point indices are not 0..{len(icps) - 1}")

        weights = [float(icp.CumulativeMetersetWeight) for icp in icps]
        _check(weights[0] == 0.0, failures,
               f"{where}: first cumulative meterset weight is {weights[0]}, expected 0")
        _check(all(b >= a for a, b in zip(weights, weights[1:])), failures,
               f"{where}: cumulative meterset weight is not monotonically increasing")
        # A plan whose own declared total disagrees with its last control point cannot be
        # expanded consistently, so this catches a bad input as well as a bad expansion.
        _check(_close(weights[-1], final_weight, METERSET_TOLERANCE), failures,
               f"{where}: last cumulative meterset weight {weights[-1]:.6f} does not reach "
               f"FinalCumulativeMetersetWeight {final_weight:.6f}")

        coefficients = [float(icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient)
                        for icp in icps if "ReferencedDoseReferenceSequence" in icp]
        if coefficients:
            _check(coefficients[0] == 0.0, failures,
                   f"{where}: first cumulative dose reference coefficient is "
                   f"{coefficients[0]}, expected 0")
            _check(_close(coefficients[-1], 1.0, METERSET_TOLERANCE), failures,
                   f"{where}: last cumulative dose reference coefficient is "
                   f"{coefficients[-1]:.6f}, expected 1")
            _check(all(b >= a for a, b in zip(coefficients, coefficients[1:])), failures,
                   f"{where}: cumulative dose reference coefficient is not monotonically increasing")

    return failures


def verify_layer_repeat(before, dicom, repeats, delay_mu=None, delay_position=None,
                        tolerance=METERSET_TOLERANCE):
    """
    Check that a plan whose layers were repeated delivers the original pattern n times.

    Repetition must not touch what a spot delivers, only how many times the sequence is
    delivered, so this compares the expanded plan against the pre-expansion snapshot
    tiled `repeats` times, spot by spot. Positions and energies are compared the same
    way, since a repetition which perturbed either would no longer be a repetition.

    With delay_mu, each of the repeats - 1 gaps must hold exactly one delay layer: a
    single spot of delay_mu at delay_position followed by its zeroed twin, both at the
    energy of the layer which follows the gap. A delay layer which drifted towards the
    field centre, lost its meterset or changed the energy would not buy the time it
    exists for, so all three are checked rather than only the plan total.

    Args:
        before (dict): Result of snapshot() taken before the layers were repeated.
        dicom (pydicom.Dataset): The plan after expansion. It is not modified.
        repeats (int): How many times the layer sequence is now delivered.
        delay_mu (float, optional): Monitor units of the delay spot in each gap. None
            means no delay layers were requested.
        delay_position (tuple of float, optional): Where the delay spot must sit, (x, y)
            in mm. Passed in rather than known here, so this module stays independent of
            the code it checks.
        tolerance (float): Relative tolerance for meterset quantities. Positions and
            energies always use GEOMETRY_TOLERANCE regardless of this.

    Raises:
        PlanVerificationError: If any check fails. The message lists every failure.
    """
    after = snapshot(dicom)
    failures = []

    _check(len(after["beams"]) == len(before["beams"]), failures,
           f"field count changed: {len(before['beams'])} -> {len(after['beams'])}")

    for j, (b, a) in enumerate(zip(before["beams"], after["beams"])):
        where = f"field {j}"

        # What each gap between repetitions must contain: one delay layer, which is a
        # control point pair holding a single spot of delay_mu and its zeroed twin, at
        # the given position, carrying the energy of the layer which follows it. Built
        # into the expected lists rather than special-cased afterwards, so the delay
        # layers are checked by exactly the same comparisons as everything else.
        gaps = repeats - 1
        gap_mu, gap_positions, gap_energies = [], [], []
        if delay_mu is not None and gaps > 0:
            gap_mu = [delay_mu, 0.0]
            gap_positions = list(delay_position) * 2 if delay_position is not None else []
            # The layer which follows a gap is the first layer of the next repetition.
            gap_energies = [b["energies"][0]] * 2

        # The spot pattern. Checked per spot rather than on the total: a total can be
        # right while the pattern underneath it has been reordered or reweighted.
        want_mu = _tiled(b["spot_mu"], gap_mu, repeats)
        _check(len(a["spot_mu"]) == len(want_mu), failures,
               f"{where}: spot count is {len(a['spot_mu'])}, expected {len(want_mu)} "
               f"({len(b['spot_mu'])} x {repeats} plus {gaps} delay layer(s))")
        _check(all(_close(x, y, tolerance) for x, y in zip(a["spot_mu"], want_mu)), failures,
               f"{where}: repeated spots do not deliver the original meterset")

        want_positions = _tiled(b["positions"], gap_positions, repeats)
        _check(len(a["positions"]) == len(want_positions)
               and all(_close(x, y, GEOMETRY_TOLERANCE)
                       for x, y in zip(a["positions"], want_positions)),
               failures, f"{where}: spot positions were modified by layer repetition")

        want_energies = _tiled(b["energies"], gap_energies, repeats)
        _check(len(a["energies"]) == len(want_energies)
               and all(_close(x, y, GEOMETRY_TOLERANCE)
                       for x, y in zip(a["energies"], want_energies)),
               failures, f"{where}: beam energies were modified by layer repetition")

        want_meterset = b["beam_meterset"] * repeats + gaps * (delay_mu or 0.0)
        _check(_close(a["beam_meterset"], want_meterset, tolerance), failures,
               f"{where}: BeamMeterset {a['beam_meterset']:.6f} MU, "
               f"expected {want_meterset:.6f} MU")

        # Declared BeamMeterset must agree with the spots underneath it, or the plan lies
        # about what it delivers.
        got_total = sum(a["spot_mu"])
        _check(_close(got_total, a["beam_meterset"], tolerance), failures,
               f"{where}: BeamMeterset {a['beam_meterset']:.6f} MU disagrees with the "
               f"sum of its spots, {got_total:.6f} MU")

        if b["beam_dose"] is not None and a["beam_dose"] is not None:
            # Delay layers deliberately do not count towards the stated dose: their MU
            # lands far out in the field, not at the dose reference point.
            want_dose = b["beam_dose"] * repeats
            _check(_close(a["beam_dose"], want_dose, tolerance), failures,
                   f"{where}: BeamDose {a['beam_dose']:.6f}, expected {want_dose:.6f} Gy(RBE)")

    failures += _sequence_failures(dicom)

    if failures:
        raise PlanVerificationError(
            f"Layer repetition verification FAILED for {repeats} repetitions "
            f"(tolerance {tolerance:.1e}). This plan must not be delivered:\n  - "
            + "\n  - ".join(failures))

    logger.info(f"Layer repetition verified independently: {repeats} repetitions, "
                f"tolerance {tolerance:.1e}, all checks passed.")
