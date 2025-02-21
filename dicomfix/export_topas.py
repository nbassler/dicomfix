import numpy as np
from pathlib import Path
import logging
import datetime
import os
from dicomfix.__version__ import __version__

from dicomfix.export import Field, BeamModel

logger = logging.getLogger(__name__)


class Topas:
    @staticmethod
    def export(fn: Path, myfield: Field, bm: BeamModel, nominal: bool,
               nstat=100000,
               sad_x=2000.0, sad_y=2560.0, beam_model_position=500.0):
        """
        Export the field to a topas input file.
        """
        # topas needs long series of spots for each parameter.
        # energy, energyspread, posX, AngleX, posY, AngleY,
        # SigmaX, SigmaY, SigmaXprime, SigmaYprime, CorrelationX, CorrelationY, spotweight

        # calculate total number of sports
        n_spots = 0
        # loop over all spots in all layers in all fields:

        for layer in myfield.layers:
            for spot in layer.spots:
                n_spots += 1

        # establish size of output arrays
        times = np.zeros(n_spots)
        energies = np.zeros(n_spots)
        espreads = np.zeros(n_spots)
        posx = np.zeros(n_spots)
        angx = np.zeros(n_spots)
        posy = np.zeros(n_spots)
        angy = np.zeros(n_spots)
        sigx = np.zeros(n_spots)
        sigy = np.zeros(n_spots)
        sigxp = np.zeros(n_spots)
        sigyp = np.zeros(n_spots)
        corx = np.zeros(n_spots)
        cory = np.zeros(n_spots)
        weights = np.zeros(n_spots)

        # loop over all spots in all layers in all fields:
        # and fill the arrays
        _spot_index = 0
        _nlayer = 0
        for layer in myfield.layers:
            if nominal:
                energy = layer.energy_nominal
            else:
                # energy from scipy interpolation
                energy = layer.energy_measured
            espread = layer.espread
            for spot in layer.spots:
                times[_spot_index] = _spot_index + 1
                energies[_spot_index] = energy
                espreads[_spot_index] = espread
                posx[_spot_index] = spot[0]
                angx[_spot_index] = np.arctan(spot[0] / (sad_x - beam_model_position)) * 180.0 / np.pi
                posy[_spot_index] = spot[1]
                angy[_spot_index] = np.arctan(spot[1] / (sad_y - beam_model_position)) * 180.0 / np.pi
                sigx[_spot_index] = bm.f_sx(layer.energy_nominal)
                sigy[_spot_index] = bm.f_sy(layer.energy_nominal)
                sigxp[_spot_index] = bm.f_divx(layer.energy_nominal)
                sigyp[_spot_index] = bm.f_divy(layer.energy_nominal)
                corx[_spot_index] = bm.f_covx(layer.energy_nominal)
                cory[_spot_index] = bm.f_covy(layer.energy_nominal)
                weights[_spot_index] = spot[3]
                _spot_index += 1
            _nlayer += 1

        total_number_of_particles = weights.sum()
        nstat_scale = (nstat / total_number_of_particles) * myfield.scaling
        logger.info(f"Proton budget for this plan: {total_number_of_particles:.3e} protons")
        logger.info(f"Requested number of simulated particles: {nstat:.3e}")
        logger.info(f"Scaling factor: {1 / nstat_scale:.4e}")
        logger.info(f"Number of spots: {n_spots}")
        logger.info(f"Number of energy layers: {_nlayer}")

        # open output file for writing
        with open(fn, "w") as f:
            f.write(f"#PARTICLE_SCALING = {1 / nstat_scale:.0f}\n")
            f.write(f"#SOPInstanceUID = {myfield.sop_instance_uid}\n")
            f.write(_topas_variables())
            f.write(_topas_setup())
            f.write(_topas_world_setup())
            f.write(_topas_geometry())
            f.write(_topas_beam())

            f.write("##############################################\n")
            f.write("###  T  I  M  E    F  E  A  T  U  R  E  S  ###\n")
            f.write("##############################################\n")
            f.write("\n")

            f.write(f"i:Tf/NumberOfSequentialTimes         = {n_spots}\n")
            f.write(f"d:Tf/TimelineStart                   = {1} s\n")
            f.write(f"d:Tf/TimelineEnd                     = {n_spots+1} s\n")
            f.write("\n")

            f.write(_topas_array(times, energies, "Energy", "f", 3, "MeV"))
            f.write(_topas_array(times, espreads, "EnergySpread", "f", 5, ""))
            f.write(_topas_array(times, posx, "spotPositionX", "f", 2, "mm"))
            f.write(_topas_array(times, angx, "spotAngleX", "f", 3, "deg"))
            f.write(_topas_array(times, posy, "spotPositionY", "f", 2, "mm"))
            f.write(_topas_array(times, angy, "spotAngleY", "f", 3, "deg"))
            f.write(_topas_array(times, sigx, "SigmaX", "f", 5, "mm"))
            f.write(_topas_array(times, sigy, "SigmaY", "f", 5, "mm"))
            f.write(_topas_array(times, sigxp, "SigmaXprime", "f", 5, ""))
            f.write(_topas_array(times, sigyp, "SigmaYprime", "f", 5, ""))
            f.write(_topas_array(times, corx, "CorrelationX", "f", 5, ""))
            f.write(_topas_array(times, cory, "CorrelationY", "f", 5, ""))
            f.write(_topas_array(times, weights * nstat_scale, "spotWeight", "f", 0, ""))

            f.write(f"#Total number of particles: {total_number_of_particles:.0f}\n")
            f.write(f"#Total number of particles scaled down by {1 / nstat_scale:.0f}\n")
            f.write(f"#Total MU in field: {myfield.cum_mu:.2f}\n")

            f.write(_topas_footer())

            # print("s:Tf/Energy/Function                 = \"Step\"")
        # _fm = " ".join(map(str, times.astype(int)))
        # print(f"dv:Tf/Energy/Times                   = {n_spots} {_fm}")
        # print(f"dv:Tf/Energy/Times                   = {n_spots} {_fm}")


def _topas_array(time_arr: np.array, arr: np.array, name: str, fmt: str = "f", precision: int = 0, unit=""):
    """generate string of time data."""
    s = ""
    n_spots = arr.size
    s += f"s:Tf/{name}/Function                 = \"Step\"\n"
    if unit == "":
        _pre = "uv"
    else:
        _pre = "dv"

    _ft = " ".join(map(str, time_arr.astype(int)))
    _fa = " ".join(f"{x:.{precision}{fmt}}" for x in arr)
    s += f"dv:Tf/{name}/Times                   = {n_spots} {_ft} s\n"
    s += f"{_pre}:Tf/{name}/Values                   = {arr.size} {_fa} {unit}\n"
    s += "\n\n"
    return s


def _topas_variables() -> str:
    lines = [
        "##############################################",
        "###           V A R I A B L E S            ###",
        "##############################################",
        "",
        "d:Rt/Plan/IsoCenterX                 = 0.00 mm",
        "d:Rt/Plan/IsoCenterY                 = 0.00 mm",
        "d:Rt/Plan/IsoCenterZ                 = 0.00 mm",
        "d:Ge/snoutPosition                   = 421.00 mm",
        "d:Ge/gantryAngle                     = 0.00 deg",
        "d:Ge/couchAngle                      = 0.00 deg",
        "dc:Ge/Patient/DicomOriginX           = 0.00 mm",
        "dc:Ge/Patient/DicomOriginY           = 0.00 mm",
        "dc:Ge/Patient/DicomOriginZ           = 0.00 mm",
        "\n"
    ]
    return "\n".join(lines)


def _topas_setup() -> str:
    lines = [
        "##############################################",
        "###         T O P A S    S E T U P         ###",
        "##############################################",
        "# sv:Ph/Default/Modules                = 6 \"g4em-standard_opt3\" "
        "\"g4h-phy_QGSP_BIC_HP\" \"g4decay\" \"g4ion-binarycascade\" "
        "\"g4h-elastic_HP\" \"g4stopping\"",
        "i:Ts/ShowHistoryCountAtInterval         = 100000",
        "i:Ts/NumberOfThreads                    = 0 # 0 for using all cores, -1 for all but one",
        "b:Ts/DumpParameters                     = \"False\"",
        "b:Ge/Patient/IgnoreInconsistentFrameOfReferenceUID = \"True\"",
        "\n"
    ]
    return "\n".join(lines)


def _topas_world_setup() -> str:
    lines = [
        "##############################################",
        "###         W O R L D    S E T U P         ###",
        "##############################################",
        's:Ge/World/Type            = "TsBox"',
        's:Ge/World/Material        = "Air"',
        "d:Ge/World/HLX             = 90. cm",
        "d:Ge/World/HLY             = 90. cm",
        "d:Ge/World/HLZ             = 90. cm",
        'b:Ge/World/Invisible       = "True"',
        "\n"
    ]
    return "\n".join(lines)


def _topas_geometry() -> str:
    lines = [
        "##############################################",
        "###            G E O M E T R Y             ###",
        "##############################################",
        's:Ge/Gantry/Parent                   = "DCM_to_IEC"',
        's:Ge/Gantry/Type                     = "Group"',
        "d:Ge/Gantry/TransX                   = 0.00 mm",
        "d:Ge/Gantry/TransY                   = 0.00 mm",
        "d:Ge/Gantry/TransZ                   = 0.00 mm",
        "d:Ge/Gantry/RotX                     = 0.00 deg",
        "d:Ge/Gantry/RotY                     = Ge/gantryAngle deg",
        "d:Ge/Gantry/RotZ                     = 0.00 deg",
        "",
        's:Ge/Couch/Parent                  = "World"',
        's:Ge/Couch/Type                    = "Group"',
        "d:Ge/Couch/RotX                    = 0. deg",
        "d:Ge/Couch/RotY                    = -1.0 * Ge/couchAngle deg",
        "d:Ge/Couch/RotZ                    = 0. deg",
        "d:Ge/Couch/TransX                  = 0.0 mm",
        "d:Ge/Couch/TransY                  = 0.0 mm",
        "d:Ge/Couch/TransZ                  = 0.0 mm",
        "",
        's:Ge/DCM_to_IEC/Parent               = "Couch"',
        's:Ge/DCM_to_IEC/Type                 = "Group"',
        "d:Ge/DCM_to_IEC/TransX               = 0.0 mm",
        "d:Ge/DCM_to_IEC/TransY               = 0.0 mm",
        "d:Ge/DCM_to_IEC/TransZ               = 0.0 mm",
        "d:Ge/DCM_to_IEC/RotX                 = 90.00 deg",
        "d:Ge/DCM_to_IEC/RotY                 = 0.0 deg",
        "d:Ge/DCM_to_IEC/RotZ                 = 0.0 deg",
        "",
        's:Ge/BeamPosition/Parent             = "Gantry"',
        's:Ge/BeamPosition/Type               = "Group"',
        "d:Ge/BeamPosition/TransZ             = -500.0 mm",
        "d:Ge/BeamPosition/TransX             = Tf/spotPositionX/Value mm",
        "d:Ge/BeamPosition/TransY             = -1.0 * Tf/spotPositionY/Value mm",
        "d:Ge/BeamPosition/RotX               = -1.0 * Tf/spotAngleY/Value deg",
        "d:Ge/BeamPosition/RotY               = -1.0 * Tf/spotAngleX/Value deg",
        "d:Ge/BeamPosition/RotZ               = 0.00 deg",
        "\n"
    ]
    return "\n".join(lines)


def _topas_beam() -> str:
    lines = [
        "##############################################",
        "###               B  E  A  M               ###",
        "##############################################",
        's:So/Field/Type                      = "Emittance"',
        's:So/Field/Component                 = "BeamPosition"',
        's:So/Field/BeamParticle              = "proton"',
        "d:So/Field/BeamEnergy                = Tf/Energy/Value MeV",
        "u:So/Field/BeamEnergySpread          = Tf/EnergySpread/Value",
        's:So/Field/Distribution              = "BiGaussian"',
        "d:So/Field/SigmaX                    = Tf/SigmaX/Value mm",
        "d:So/Field/SigmaY                    = Tf/SigmaY/Value mm",
        "u:So/Field/SigmaXprime               = Tf/SigmaXprime/Value",
        "u:So/Field/SigmaYprime               = Tf/SigmaYprime/Value",
        "u:So/Field/CorrelationX              = Tf/CorrelationX/Value",
        "u:So/Field/CorrelationY              = Tf/CorrelationY/Value",
        "",
        "i:So/Field/NumberOfHistoriesInRun    = Tf/spotWeight/Value",
        "\n"
    ]
    return "\n".join(lines)


def _topas_footer() -> str:
    "Add a footer to the topas file with generation date and username."

    lines = [
        "\n",
        f"# Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by user '{os.getlogin()}'" +
        f" using dicomfix {__version__}",
        "# https://github.com/nbassler/dicomfix"]

    return "\n".join(lines)
