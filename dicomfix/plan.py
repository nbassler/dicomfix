import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from math import exp, log

from dicomfix.beam_model import BeamModel, get_fwhm
# from dicomfix.field import Field

import logging

logger = logging.getLogger(__name__)


def dedx_air(energy: float) -> float:
    """
    Calculate the mass stopping power of protons in air following ICRU 49.

    Valid from 1 to 500 MeV only.

    :params energy: Proton energy in MeV
    :returns: mass stopping power in MeV cm2/g
    """
    if energy > 500.0 or energy < 1.0:
        logger.error("Proton energy must be between 1 and 500 MeV.")
        raise ValueError(f"Energy = {energy:.2f} out of bounds.")
    x = log(energy)
    y = 5.4041 - 0.66877 * x - 0.034441 * (x**2) - 0.0010707 * (x**3) + 0.00082584 * (x**4)
    return exp(y)


@dataclass
class Plan:
    """
    Class for handling treatment plans.

    One plan may consist of one or more fields.
    One field may contain one of more layers.

    Beam model is optional, but needed for exact modeling of the beam.
    If no beam model is given, MUs are translated to particle numbers using approximate stopping power for air (dEdx)
    and empirical scaling factors.
    """

    fields: list = field(default_factory=list)  # https://stackoverflow.com/questions/53632152/
    patient_id: str = ""  # ID of patient
    patient_name: str = ""  # Last name of patient
    patient_initals: str = ""  # Initials of patient
    patient_firstname: str = ""  # Last name of patient
    plan_label: str = ""  #
    plan_date: str = ""  #
    n_fields: int = 0
    beam_model: Optional[BeamModel] = None  # optional beam model class
    beam_name: str = ""
    flip_xy: bool = False  # flag whether x and y has been flipped
    flip_x: bool = False
    flip_y: bool = False

    # factor holds the number of particles * dE/dx / MU = some constant
    # MU definitions is arbitrary and my vary from vendor to vendor.
    # This will only be used if no beam model is available, and is based on estimates.
    factor: float = 1.0  # vendor specific factor needed for translating MUs to number of particles
    scaling: float = 1.0

    def apply_beammodel(self):
        """Adjust plan to beam model."""
        if self.beam_model:
            for myfield in self.fields:
                for layer in myfield.layers:
                    # calculate number of particles
                    layer.mu_to_part_coef = self.beam_model.f_ppmu(layer.energy_nominal)
                    layer.energy_measured = self.beam_model.f_e(layer.energy_nominal)
                    layer.espread = self.beam_model.f_espread(layer.energy_nominal)
                    layer.spots[:, 3] = layer.spots[:, 2] * layer.mu_to_part_coef * myfield.scaling
                    layer.spotsize = np.array(
                        [self.beam_model.f_sx(layer.energy_nominal),
                         self.beam_model.f_sy(layer.energy_nominal)]) * get_fwhm(1.0)
        else:
            for myfield in self.fields:
                for layer in myfield.layers:
                    # if there is no beam model available, we will simply use air stopping power
                    # since MU is proportional to dose in monitor chamber, which means fluence ~ D_air / dEdx(air)
                    layer.mu_to_part_coef = self.factor / dedx_air(layer.energy_measured)
                    layer.spots[:, 3] = layer.spots[:, 2] * layer.mu_to_part_coef * myfield.scaling
                    # old IBA code something like:
                    # weight = mu_to_part_coef * _mu2 * field.cmu / field.pld_csetweight
                    # phi_weight = weight / dedx_air(layer.energy_measured)

        # set cumulative sums
        for myfield in self.fields:
            myfield.cum_particles = 0.0
            myfield.cum_mu = 0.0
            myfield.xmin = 0.0
            myfield.xmax = 0.0
            myfield.ymin = 0.0
            myfield.ymax = 0.0

            # set layer specific values
            for layer in myfield.layers:
                layer.n_spots = len(layer.spots)
                layer.xmin = layer.spots[:, 0].min()
                layer.xmax = layer.spots[:, 0].max()
                layer.ymin = layer.spots[:, 1].min()
                layer.ymax = layer.spots[:, 1].max()
                layer.cum_mu = layer.spots[:, 2].sum()
                if layer.cum_mu > 0.0:
                    layer.is_empty = False
                layer.cum_particles = layer.spots[:, 3].sum()

                myfield.cum_particles += layer.cum_particles
                myfield.cum_mu += layer.cum_mu

                if layer.xmin < myfield.xmin:
                    myfield.xmin = layer.xmin
                if layer.xmax > myfield.xmax:
                    myfield.xmax = layer.xmax

                if layer.ymin < myfield.ymin:
                    myfield.ymin = layer.ymin
                if layer.ymax > myfield.ymax:
                    myfield.ymax = layer.ymax

    def diagnose(self):
        """Print overview of plan."""
        print("Diagnostics:")
        print("---------------------------------------------------")
        print(f"Patient Name           : '{self.patient_name}'       [{self.patient_initals}]")
        print(f"Patient ID             : {self.patient_id}")
        print(f"Plan label             : {self.plan_label}")
        print(f"Plan date              : {self.plan_date}")
        print(f"Number of Fields       : {self.n_fields:2d}")

        for i, myfield in enumerate(self.fields):
            print("---------------------------------------------------")
            print(f"   Field                  : {i + 1:02d}/{self.n_fields:02d}:")
            myfield.diagnose()
            print("")

    def export(self, fn: Path, cols: int, field_nr: int, nominal: bool):
        """
        Export file to sobp.dat format, 'cols' marking the number of columns.

        fn : filename
        cols : number of columns for output format.
               5 column format: energy[GeV] x[cm] y[cm] FWHM[cm] weight
               6 column format: energy[GeV] x[cm] y[cm] FWHMx[cm] FWHMy[cm] weight
               7 column format: energy[GeV] sigmaT0[GeV] x[cm] y[cm] FWHM[cm] weight
        field_nr: in case of multiple field, select what field to export, use '0' to export all fields.
        nominal : flag whether norminal energy should be exported or not

        TODO:
               11 columns: ENERGY, ESPREAD, X, Y, FWHMx, FWHMy, WEIGHT, DIVx, DIVy, COVx, COVy
        """
        if cols == 7:
            header = "*ENERGY(GEV) SigmaT0(GEV) X(CM)   Y(CM)    FWHMx(cm) FWHMy(cm) WEIGHT\n"
        elif cols == 6:
            header = "*ENERGY(GEV) X(CM)   Y(CM)    FWHMx(cm) FWHMy(cm) WEIGHT\n"
        elif cols == 5:
            header = "*ENERGY(GEV) X(CM)   Y(CM)    FWHMx(cm) FWHMy(cm) WEIGHT\n"
        else:
            raise ValueError(f"Output format with {cols} columns is not supported.")

        for i, myfield in enumerate(self.fields):
            j = i + 1  # j is the field number, i is the field index.
            output = header
            # in case all fields should be written to disk, build a new filename with _XX added to the stem
            # of the filename, based on the field number (not the filed index), i.e. first file is sobp_01.dat
            if field_nr == 0:
                fout = Path(fn.parent, (f"{fn.stem}_{j:02d}{fn.suffix}"))
            else:
                # otherwise, check if this is a field the user wanted, if not, skip it.
                fout = fn
                if (j) != field_nr:
                    continue

            for layer in myfield.layers:

                # DICOM and PLD sometimes have empty layers. This will be skipped, to not clutter the sobp.dat file.
                if layer.is_empty:
                    continue

                # Do some conversions, since sobp.dat hold different units.
                if nominal:
                    energy = layer.energy_nominal * 0.001  # convert MeV -> GeV
                else:
                    energy = layer.energy_measured * 0.001  # convert MeV -> GeV
                espread = layer.espread * 0.001  # convert MeV -> GeV

                # Check if field-flip was requested. Then do so for FWHMxy and spot positions
                if self.flip_xy:
                    fwhmy, fwhmx = layer.spotsize * 0.1  # mm -> cm
                else:
                    fwhmx, fwhmy = layer.spotsize * 0.1  # mm -> cm

                for spot in layer.spots:
                    if self.flip_x:
                        spot[0] *= -1

                    if self.flip_y:
                        spot[1] *= -1

                    if self.flip_xy:
                        xpos = spot[1] * 0.1  # mm -> cm
                        ypos = spot[0] * 0.1  # mm -> cm
                    else:
                        xpos = spot[0] * 0.1  # mm -> cm
                        ypos = spot[1] * 0.1  # mm -> cm

                    wt = spot[3]
                    # format output file. Carefully tuned so they appear in nice columns synced to header. Maybe.
                    if cols == 7:
                        s = f"{energy:8.6f}     {espread:10.8f}  " \
                            + f"{xpos:6.2f}   {ypos:6.2f}  " \
                            + f"{fwhmx:6.2f}   {fwhmy:6.2f}     {wt:10.4e}\n"
                    elif cols == 6:
                        s = f"{energy:8.6f}     " \
                            + f"{xpos:6.2f}   {ypos:6.2f}  " \
                            + f"{fwhmx:6.2f}   {fwhmy:6.2f}     {wt:10.4e}\n"
                    else:
                        s = f"{energy:8.6f}     " \
                            + f"{xpos:6.2f}   {ypos:6.2f}  " \
                            + f"{fwhmx:6.2f}   {wt:10.4e}\n"
                    output += s
            logger.debug("Export field %d %s, %g MeV", j, fout, myfield.layers[0].energy_nominal)
            fout.write_text(output)  # still in field loop, output for every field
