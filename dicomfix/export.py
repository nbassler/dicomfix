"""
Module for reading DICOM and PLD files.

One plan may contain one or more fields.
One field may contain one or more layers.
One layer may contain one or more spots.
"""

import sys
import logging
import argparse

import numpy as np
from pathlib import Path
# from typing import Optional

from dicomfix.beam_model import BeamModel, get_fwhm
from dicomfix.plan import Plan
from dicomfix.field import Field
from dicomfix.layer import Layer
from dicomfix.spot import Spot


from dicomfix.__version__ import __version__

logger = logging.getLogger(__name__)


def load(file: Path, beam_model: BeamModel, scaling: float, flip_xy: bool, flip_x: bool, flip_y: bool) -> Plan:
    """Load file, autodiscovery by suffix."""
    logger.debug("load() autodiscovery %s", file)
    ext = file.suffix.lower()  # extract suffix, incl. dot separator

    if ext == ".pld":
        logger.debug("autodiscovery: Found a IBA pld file.")
        p = load_PLD_IBA(file, scaling)
    elif ext == ".dcm":
        logger.debug("autodiscovery: Found a DICOM file.")
        p = load_DICOM_RTPLAN(file, scaling)  # so far I have no other dicom files
    elif ext == ".rst":
        logger.debug("autodiscovery: Found a GSI raster scan file.")
        p = load_RASTER_GSI(file, scaling)
    else:
        raise ValueError(f"autodiscovery: Unknown file type. {file}")

    # apply beam model if available
    if beam_model:
        p.beam_model = beam_model
    else:
        logger.error("BeamModel is unavailable in Plan.")

    p.apply_beammodel()
    p.flip_xy = flip_xy
    p.flip_x = flip_x
    p.flip_y = flip_y

    return p


def load_PLD_IBA(file_pld: Path, scaling=1.0) -> Plan:
    """
    Load a IBA-style PLD-file.

    file_pld : a file pointer to a .pld file, opened for reading.
    Here we assume there is only a single field in every .pld file.
    """
    logging.warning("IBA_PLD reader not tested yet.")
    eps = 1.0e-10

    current_plan = Plan()
    myfield = Field()  # avoid collision with dataclasses.field
    current_plan.fields = [myfield]
    current_plan.n_fields = 1

    # # TODO: needs beam model to be applied for spot parameters and MU scaling.
    # # For now, we simply assume a constant factor for the number of particles per MU (which is not correct).
    # # p.factor holds the number of particles * dE/dx / MU = some constant
    # # p.factor = 8.106687e7  # Calculated Nov. 2016 from Brita's 32 Gy plan. (no dE/dx)
    # current_plan.factor = 5.1821e8  # protons per (MU/dEdx), Estimated calculation Apr. 2017 from Brita's 32 Gy plan.

    # # currently scaling is treated equal at plan and field level. This is for future use.
    # current_plan.scaling = scaling
    # myfield.scaling = scaling

    pldlines = file_pld.read_text().split('\n')
    pldlen = len(pldlines)
    logger.info("Read %d lines of data.", pldlen)

    myfield.layers = []

    # First line in PLD file contains both plan and field data
    tokens = pldlines[0].split(",")
    current_plan.patient_id = tokens[1].strip()
    current_plan.patient_name = tokens[2].strip()
    current_plan.patient_initals = tokens[3].strip()
    current_plan.patient_firstname = tokens[4].strip()
    current_plan.plan_label = tokens[5].strip()
    current_plan.beam_name = tokens[6].strip()
    myfield.cmu = float(tokens[7].strip())          # total amount of MUs in this field
    myfield.pld_csetweight = float(tokens[8].strip())
    myfield.n_layers = int(tokens[9].strip())       # number of layers

    espread = 0.0  # will be set by beam model

    i = 1
    while i < pldlen:
        line = pldlines[i]
        if "Layer" in line:
            tokens = line.split(",")

            spotsize_sigma = float(tokens[1].strip())
            spotsize_fwhm = get_fwhm(spotsize_sigma)  # single value in mm

            energy_nominal = float(tokens[2].strip())
            cmu = float(tokens[3].strip())
            nspots_expected = int(tokens[4].strip())

            nrepaint = int(tokens[5].strip()) if len(tokens) > 5 else 0

            elements = []
            j = i + 1
            while j < pldlen and "Element" in pldlines[j]:
                elements.append(pldlines[j])
                j += 1

            spots = []
            for el in elements:
                el_tokens = el.split(",")
                _x = float(el_tokens[1].strip())
                _y = float(el_tokens[2].strip())
                _mu = float(el_tokens[3].strip())

                if abs(_x) < eps:
                    _x = 0.0
                if abs(_y) < eps:
                    _y = 0.0
                if _mu < eps:
                    _mu = 0.0

                # Skip empty spots
                if _mu > 0.0:
                    spots.append(Spot(
                        x=_x,
                        y=_y,
                        mu=_mu,
                        size_x=spotsize_fwhm,
                        size_y=spotsize_fwhm
                    ))

            # check if expected number of spots is correct
            if len(spots) != nspots_expected:
                logger.warning("Expected %d spots, but found %d in layer %d at energy %.2f MeV",
                               nspots_expected, len(spots), len(myfield.layers), energy_nominal)

            layer = Layer(
                spots=spots,
                energy_nominal=energy_nominal,
                energy_measured=energy_nominal,
                espread=espread,
                cum_mu=cmu,
                n_spots=len(spots),
                repaint=nrepaint,
                mu_to_part_coef=0.0  # to be set by beam model later
            )

            current_plan.fields[0].layers.append(layer)
            logger.debug("Appended layer %d with %d spots", len(current_plan.fields[0].layers), len(spots))

            i = j  # move to next layer or EOF
        else:
            i += 1

    return current_plan


def load_DICOM_RTPLAN(file_dcm: Path, scaling=1.0) -> Plan:
    """Load DICOM RTPLAN."""
    logging.warning("DICOM reader not tested yet.")
    p = Plan()
    try:
        import pydicom as dicom
    except ImportError:
        logger.error("pydicom is not installed, cannot read DICOM files.")
        logger.error("Please install pymchelper[dicom] or pymchelper[all] to us this feature.")
        return p
    d = dicom.dcmread(file_dcm)
    # Total number of energy layers used to produce SOBP

    p.patient_id = d['PatientID'].value
    p.patient_name = d['PatientName'].value
    p.patient_initals = ""
    p.patient_firstname = ""
    p.plan_label = d['RTPlanLabel'].value
    p.plan_date = d['RTPlanDate'].value
    p.sop_instance_uid = d['SOPInstanceUID'].value

    espread = 0.0  # will be set by beam model
    p.n_fields = int(d['FractionGroupSequence'][0]['NumberOfBeams'].value)
    logger.debug("Found %i fields", p.n_fields)

    rbs = d['FractionGroupSequence'][0]['ReferencedBeamSequence']  # fields for given group number
    for i, rb in enumerate(rbs):
        myfield = Field()
        logger.debug("Appending field number %d...", i)
        p.fields.append(myfield)
        myfield.sop_instance_uid = p.sop_instance_uid
        myfield.dose = float(rb['BeamDose'].value)
        myfield.cum_mu = float(rb['BeamMeterset'].value)

    ibs = d['IonBeamSequence']  # ion beam sequence, contains all fields
    if len(ibs.value) != p.n_fields:
        logger.error("Number of fields in IonBeamSequence (%d) does not match FractionGroupSequence (%d).",
                     len(ibs.value), p.n_fields)
        raise ValueError("Inconsistent number of fields in DICOM plan.")

    for i, ib in enumerate(ibs):
        myfield = p.fields[i]
        myfield.meterset_weight_final = float(ib['FinalCumulativeMetersetWeight'].value)
        myfield.meterset_per_weight = myfield.cum_mu / myfield.meterset_weight_final

        icps = ib['IonControlPointSequence']  # layers for given field number
        logger.debug("Found %i layers in field number %i", myfield.n_layers, i)

        cmu = 0.0

        for j, icp in enumerate(icps):

            # Several attributes are only set once at the first ion control point.
            # The strategy here is then to still set them for every layer, even if they do not change.
            # This is to ensure that the field object has all necessary attributes set.
            # But also enables future stuff like arc therapy, where these values may change per layer.
            if 'LateralSpreadingDeviceSettingsSequence' in icp:
                if len(icp['LateralSpreadingDeviceSettingsSequence'].value) != 2:
                    logger.error("LateralSpreadingDeviceSettingsSequence should contain exactly 2 elements, found %d.",
                                 len(ib['LateralSpreadingDeviceSettingsSequence'].value))
                    raise ValueError("Invalid LateralSpreadingDeviceSettingsSequence in DICOM plan.")

                lss = icp['LateralSpreadingDeviceSettingsSequence']
                sad_x = float(lss[0]['IsocenterToLateralSpreadingDeviceDistance'].value)
                sad_y = float(lss[1]['IsocenterToLateralSpreadingDeviceDistance'].value)

                logger.debug("Set Lateral spreading device distances: X = %.2f mm, Y = %.2f mm",
                             sad_x, sad_y)

            # check snout position
            if 'SnoutPosition' in icp:
                snout_position = float(icp['SnoutPosition'].value)

            # check if a range shifter is used
            if 'RangeShifterSequence' in icp:
                for rs in icp['RangeShifterSequence']:
                    if 'RangeShifterID' in rs:
                        rsid = rs['RangeShifterID'].value
                        logger.debug("Found range shifter ID: %s", rsid)
                        if rsid == 'None':
                            myfield.range_shifter_thickness = 0.0
                        elif rsid == 'RS_3CM':
                            myfield.range_shifter_thickness = 30.0
                        elif rsid == 'RS_5CM':
                            myfield.range_shifter_thickness = 50.0
                    else:
                        logger.warning("Unknown range shifter ID in DICOM plan: %s", rsid)
                myfield.range_shifter_thickness = float(ib['RangeShifterSequence'].value)

            # isocenter position and gantry counch angles are stored in each layer,
            # for now we assume they are the same for all layers in a field,
            # ideally these attributes should be stored in the layer object
            # then conversion can change it to a field level for topas export.
            if 'IsocenterPosition' in icp:
                isocenter = tuple(float(v) for v in icp['IsocenterPosition'].value)
            if 'GantryAngle' in icp:
                gantry_angle = float(icp['GantryAngle'].value)
            if 'PatientSupportAngle' in icp:
                couch_angle = float(icp['PatientSupportAngle'].value)

            if not all(tag in icp for tag in ['NominalBeamEnergy',
                                              'NumberOfScanSpotPositions',
                                              'ScanSpotPositionMap',
                                              'ScanSpotMetersetWeights',
                                              'ScanningSpotSize']):
                raise ValueError("Layer is missing required DICOM tags for spot extraction.")

            energy = float(icp['NominalBeamEnergy'].value)  # Nominal energy in MeV
            nspots = int(icp['NumberOfScanSpotPositions'].value)  # number of spots
            logger.debug("Found %i spots in layer number %i at energy %f", nspots, j, energy)
            nrepaint = int(icp['NumberOfPaintings'].value)  # number of spots

            # Extract spot positions [mm]
            pos = np.array(icp['ScanSpotPositionMap'].value).reshape(nspots, 2)

            # Extract spot MU and scale [MU]
            mu = np.array(icp['ScanSpotMetersetWeights'].value).reshape(nspots) * myfield.meterset_per_weight

            # Extract spot nominal sizes [mm FWHM]
            size_x, size_y = icp['ScanningSpotSize'].value

            spots = [Spot(x=x, y=y, mu=mu_val, size_x=size_x, size_y=size_y)
                     for (x, y), mu_val in zip(pos, mu)]

            # only append layer, if sum of mu are larger than 0
            sum_mu = np.sum(mu)

            if sum_mu > 0.0:
                cmu += sum_mu
                myfield.layers.append(Layer(
                    spots=spots,
                    energy_nominal=energy,
                    energy_measured=energy,
                    espread=espread,
                    cum_mu=cmu,
                    repaint=nrepaint,
                    mu_to_part_coef=0.0,
                    isocenter=isocenter,
                    gantry_angle=gantry_angle,
                    couch_angle=couch_angle,
                    snout_position=snout_position,
                    sad=(sad_x, sad_y)
                ))
            else:
                logger.debug("Skipping empty layer %i", j)
    return p


def load_RASTER_GSI(file_rst: Path, scaling=1.0):
    """this is implemented in pytrip, maybe we could import it?."""
    logging.warning("GSI raster file reader not implemented yet.")
    logging.info("Opening file %s", file_rst)
    p = Plan()
    p.scaling = scaling  # nee note in IBA reader above.
    return p


def main(args=None) -> int:
    """
    Read a plan file (dicom, pld, rst), and convert it to a spot list, easy to read by MC codes.

    The MU based spot list in dicom/pld/rst is converted to particle weighted spot list,
    optionally based on a realistic beam model, or on simple estimations.
    """
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('fin',
                        metavar="input_file",
                        type=Path,
                        help="path to input file in IBA '.pld'-format or Varian DICOM-RN.")
    parser.add_argument('fout',
                        nargs='?',
                        metavar="output_file",
                        type=Path,
                        help="path to the SHIELD-HIT12A/FLUKA output_file. Default: 'sobp.dat'",
                        default="sobp.dat")
    parser.add_argument('-b',
                        metavar="beam_model.csv",
                        type=Path,
                        help="optional input beam model in commasparated CSV format",
                        dest='fbm',
                        default=None)
    parser.add_argument('-i',
                        '--flip',
                        action='store_true',
                        help="flip XY axis of input (x -> y and y -> x)",
                        dest="flip_xy",
                        default=False)
    parser.add_argument('-x',
                        '--xflip',
                        action='store_true',
                        help="flip x axis of input (x -> -x)",
                        dest="flip_x",
                        default=False)
    parser.add_argument('-y',
                        '--yflip',
                        action='store_true',
                        help="flip y axis of input (y -> -y)",
                        dest="flip_y",
                        default=False)
    parser.add_argument('-f',
                        '--field',
                        type=int,
                        dest='field_nr',
                        help="select which field to export, for dicom files holding several fields. " +
                        "'0' will produce multiple output files with a running number.",
                        default=1)
    parser.add_argument('-d',
                        '--diag',
                        action='store_true',
                        help="print diagnostics of input dicom file, but do not export data",
                        dest="diag",
                        default=False)
    parser.add_argument('-n',
                        '--nominal',
                        action='store_true',
                        help="save nominal energies instead of beam model energies",
                        dest="nominal",
                        default=False)
    parser.add_argument('-s', '--scale', type=float, dest='scale', help="number of particles*dE/dx per MU", default=1.0)
    parser.add_argument('-N', '--nstat', type=int, dest='nstat',
                        help="number of target protons to be simulated (topas only)",
                        default=1e6)
    parser.add_argument('-c',
                        '--columns',
                        type=int,
                        dest='cols',
                        help="number of columns in output file. 5, 6, 7 col format supported, default is 7.",
                        default=7)
    parser.add_argument('-t', '--topas', action='store_true', help="export to topas format", dest="topas", default=False)
    parser.add_argument('-v', '--verbosity', action='count', help="increase output verbosity", default=0)
    parser.add_argument('-V', '--version', action='version', version=__version__)
    parsed_args = parser.parse_args(args)

    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)

    if parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)

    if parsed_args.fbm:
        bm = BeamModel(parsed_args.fbm)
        logger.debug("Beam model loaded from %s", parsed_args.fbm)
    else:
        bm = None

    pln = load(parsed_args.fin, bm, parsed_args.scale, parsed_args.flip_xy, parsed_args.flip_x, parsed_args.flip_y)

    if parsed_args.field_nr < 1:
        logger.error("Loop over fields not implemented yet.")
        # TODO: loop over all fields in the plan
    else:
        field_idx = parsed_args.field_nr - 1

    if parsed_args.diag:
        pln.diagnose()
    else:
        if parsed_args.topas:
            from dicomfix.export_topas import Topas
            Topas.export(parsed_args.fout, pln.fields[field_idx], bm, parsed_args.nominal, nstat=parsed_args.nstat)
        else:
            pln.export(parsed_args.fout, parsed_args.cols, parsed_args.field_nr, parsed_args.nominal)

    return 0


if __name__ == '__main__':
    # Run sys.exit with exit code of the main method.
    sys.exit(main(sys.argv[1:]))
