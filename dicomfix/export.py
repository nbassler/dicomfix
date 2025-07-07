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
        p = load_DICOM_VARIAN(file, scaling)  # so far I have no other dicom files
    elif ext == ".rst":
        logger.debug("autodiscovery: Found a GSI raster scan file.")
        p = load_RASTER_GSI(file, scaling)
    else:
        raise ValueError(f"autodiscovery: Unknown file type. {file}")

    # apply beam model if available
    if beam_model:
        p.beam_model = beam_model
    else:
        logger.debug("BeamModel is unavailable in Plan.")

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
    logging.warning("IBA_PLD reader not implemented yet.")
    eps = 1.0e-10

    current_plan = Plan()

    myfield = Field()  # avoid collision with dataclasses.field
    current_plan.fields = [myfield]
    current_plan.n_fields = 1

    # TODO: needs beam model to be applied for spot parameters and MU scaling.
    # For now, we simply assume a constant factor for the number of particles per MU (which is not correct).
    # p.factor holds the number of particles * dE/dx / MU = some constant
    # p.factor = 8.106687e7  # Calculated Nov. 2016 from Brita's 32 Gy plan. (no dE/dx)
    current_plan.factor = 5.1821e8  # protons per (MU/dEdx), Estimated calculation Apr. 2017 from Brita's 32 Gy plan.

    # currently scaling is treated equal at plan and field level. This is for future use.
    current_plan.scaling = scaling
    myfield.scaling = scaling

    pldlines = file_pld.read_text().split('\n')
    pldlen = len(pldlines)
    logger.info("Read %d lines of data.", pldlen)

    myfield.layers = []
    myfield.n_layers = 0

    # First line in PLD file contains both plan and field data
    tokens = pldlines[0].split(",")
    current_plan.patient_id = tokens[1].strip()
    current_plan.patient_name = tokens[2].strip()
    current_plan.patient_initals = tokens[3].strip()
    current_plan.patient_firstname = tokens[4].strip()
    current_plan.plan_label = tokens[5].strip()
    current_plan.beam_name = tokens[6].strip()
    myfield.cmu = float(tokens[7].strip())  # total amount of MUs in this field
    myfield.pld_csetweight = float(tokens[8].strip())
    myfield.n_layers = int(tokens[9].strip())  # number of layers

    espread = 0.0  # will be set by beam model

    for i in range(1, pldlen):  # loop over all lines starting from the second one
        line = pldlines[i]
        if "Layer" in line:  # each new layers starts with the "Layer" keyword
            # the "Layer" header is formated as
            # "Layer, "
            header = line
            tokens = header.split(",")
            # extract the subsequent lines with elements
            el_first = i + 1
            el_last = el_first + int(tokens[4])

            elements = pldlines[el_first:el_last]  # each line starting with "Element" string is a spot.

            # tokens[0] just holds the "Layer" keyword
            # IBA PLD holds nominal spot size in 1D, 1 sigma in [mm]
            spotsize = get_fwhm(float(tokens[1].strip()))   # convert mm sigma to mm FWHM (this is just a float)

            energy_nominal = float(tokens[2].strip())
            cmu = float(tokens[3].strip())
            nspots = int(tokens[4].strip())
            logger.debug(tokens)

            # read number of repaints only if 5th column is present, otherwise set to 0
            nrepaint = 0  # we suspect repaints = 1 means all dose will be delivered once.
            if len(tokens) > 5:
                nrepaint = int(tokens[5].strip())

            spots = np.array([])

            layer = Layer(spots=spots,
                          spotsize=np.array([spotsize, spotsize]),
                          energy_nominal=energy_nominal,
                          energy_measured=energy_nominal,
                          espread=espread,
                          cum_mu=cmu,
                          n_spots=nspots,
                          repaint=nrepaint)

            for element in elements:  # loop over each spot in this layer
                token = element.split(",")
                # the .pld file has every spot position repeated, but MUs are only in
                # every second line, for reasons unknown.
                _x = float(token[1].strip())
                _y = float(token[2].strip())
                _mu = float(token[3].strip())

                # fix bad float conversions
                if np.abs(_x) < eps:
                    _x = 0.0
                if np.abs(_y) < eps:
                    _y = 0.0
                if _mu < eps:
                    _mu = 0.0

                # PLD files have the spots listed tiwce, once with no MUs. These are removed here.
                if _mu > 0.0:
                    layer.spots = np.append([layer.spots], [_x, _y, _mu, _mu])
                else:
                    # this was an empty spot, decrement spot count, and do not add it.
                    nspots -= 1

            layer.spots = layer.spots.reshape(nspots, 4)
            current_plan.fields[0].layers.append(layer)

            logger.debug("appended layer %i with %i spots", len(current_plan.fields[0].layers), layer.n_spots)
    return current_plan


def load_DICOM_VARIAN(file_dcm: Path, scaling=1.0) -> Plan:
    """Load varian type dicom plans."""
    logging.warning("DICOM reader not implemented yet.")
    p = Plan()
    try:
        import pydicom as dicom
    except ImportError:
        logger.error("pydicom is not installed, cannot read DICOM files.")
        logger.error("Please install pymchelper[dicom] or pymchelper[all] to us this feature.")
        return p
    ds = dicom.dcmread(file_dcm)
    # Total number of energy layers used to produce SOBP

    p.patient_id = ds['PatientID'].value
    p.patient_name = ds['PatientName'].value
    p.patient_initals = ""
    p.patient_firstname = ""
    p.plan_label = ds['RTPlanLabel'].value
    p.plan_date = ds['RTPlanDate'].value
    p.sop_instance_uid = ds['SOPInstanceUID'].value

    # protons per (MU/dEdx), Estimated calculation Nov. 2022 from DCPT beam model
    p.factor = 17247566.1  # find better solution for this, this is very approximate
    p.scaling = scaling  # nee note in IBA reader above.
    espread = 0.0  # will be set by beam model
    p.n_fields = int(ds['FractionGroupSequence'][0]['NumberOfBeams'].value)
    logger.debug("Found %i fields", p.n_fields)

    dcm_fgs = ds['FractionGroupSequence'][0]['ReferencedBeamSequence']  # fields for given group number

    for i, dcm_field in enumerate(dcm_fgs):
        myfield = Field()
        logger.debug("Appending field number %d...", i)
        p.fields.append(myfield)
        myfield.sop_instance_uid = p.sop_instance_uid
        myfield.dose = float(dcm_field['BeamDose'].value)
        myfield.cum_mu = float(dcm_field['BeamMeterset'].value)
        myfield.meterset_weight_final = float(ds['IonBeamSequence'][i]['FinalCumulativeMetersetWeight'].value)
        myfield.meterset_per_weight = myfield.cum_mu / myfield.meterset_weight_final
        myfield.pld_csetweight = 1.0
        myfield.scaling = scaling  # nee note in IBA reader above.
        myfield.n_layers = int(ds['IonBeamSequence'][i]['NumberOfControlPoints'].value)
        dcm_ibs = ds['IonBeamSequence'][i]['IonControlPointSequence']  # layers for given field number
        logger.debug("Found %i layers in field number %i", myfield.n_layers, i)

        cmu = 0.0

        for j, layer in enumerate(dcm_ibs):

            # gantry and couch angle is stored per energy layer, strangely
            if 'NominalBeamEnergy' in layer:
                energy = float(layer['NominalBeamEnergy'].value)  # Nominal energy in MeV
            if 'NumberOfScanSpotPositions' in layer:
                nspots = int(layer['NumberOfScanSpotPositions'].value)  # number of spots
                logger.debug("Found %i spots in layer number %i at energy %f", nspots, j, energy)
            if 'NumberOfPaintings' in layer:
                nrepaint = int(layer['NumberOfPaintings'].value)  # number of spots
            if 'ScanSpotPositionMap' in layer:
                _pos = np.array(layer['ScanSpotPositionMap'].value).reshape(nspots, 2)  # spot coords in mm
            if 'ScanSpotMetersetWeights' in layer:
                _mu = np.array(layer['ScanSpotMetersetWeights'].value).reshape(
                    nspots, 1) * myfield.meterset_per_weight  # spot MUs
                cmu = _mu.sum()
            if 'ScanningSpotSize' in layer:
                # Varian dicom holds nominal spot size in 2D, FWHMMx,y in [mm]
                spotsize = np.array(layer['ScanningSpotSize'].value)
                spots = np.c_[_pos, _mu]  # spots are now in the form [[x_i, y_i, mu_i], ...]
                # only append layer, if sum of mu are larger than 0
                if cmu > 0.0:
                    myfield.layers.append(Layer(spots, spotsize, energy, energy, espread, cmu, nrepaint, nspots))
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
        # TODO: loop over alle fields in the plan
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
