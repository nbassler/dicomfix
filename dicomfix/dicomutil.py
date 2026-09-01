"""
dicomutil.py

This module provides utilities for handling and manipulating DICOM files,
with a focus on proton therapy treatment plans. It includes functionality
for loading DICOM files, rescaling spot weights, and managing dose adjustments.
"""

import copy
import datetime
import logging
import random
from decimal import Decimal

import pydicom
from pydicom.uid import generate_uid

from dicomfix import verify

# from dicomfix.dicom_comparator import compare_dicoms  # If you plan to use this in the future


logger = logging.getLogger(__name__)

DEFAULT_SAVE_FILENAME = "output.dcm"
MU_MIN = 1.0  # at least this many MU in a single spot
HLINE = 72 * '-'

# Sentinel meaning "the user explicitly asked to remove the range shifter", as opposed
# to None which means "the user did not ask for anything". See Config.parse_range_shifter.
RANGE_SHIFTER_NONE = "NONE"
# Water equivalent thickness [mm] of the available range shifters.
RANGE_SHIFTER_WET = {"RS_2CM": 22.8, "RS_5CM": 57.0}

# Where a delay spot goes, in mm. Far out in the field, so the scanning magnets have to
# sweep there and back, which is what buys the delay. Taken from the TR3/TR4 spot
# measurement plan (XRV4000), which uses this position for the same purpose, so it is
# known to be deliverable. Maximum field is 300 x 400 mm, i.e. x +/-150 and y +/-200.
DELAY_SPOT_POSITION = (140.0, 190.0)


class DicomUtil:
    """
    A utility class for handling DICOM proton therapy treatment plans.

    This class provides methods for loading, modifying, and saving DICOM
    files related to proton therapy, including rescaling monitor units (MU)
    and adjusting dose coefficients. It also tracks the total number of spots
    in the DICOM file and handles low MU spot removal.

    Attributes:
        dicom: The loaded DICOM object representing the treatment plan.
        filename: The name of the DICOM input file.
        points_discarded: Counter for spots discarded due to low MU.
        old_dicom: A deepcopy of the original DICOM object for comparison purposes.
        spots_discarded: Number of spots discarded during rescaling or filtering.
        total_number_of_spots: The total number of spots in the treatment plan.
    """

    def __init__(self, inputfile):
        """
        Initialize the DicomUtil class by loading the DICOM file and counting spots.

        Args:
            inputfile (str): Path to the DICOM file to be loaded.
        """
        self.dicom = self.load_dicom(inputfile)
        self.filename = inputfile
        self.points_discarded = 0
        self.old_dicom = copy.deepcopy(self.dicom)
        self.spots_discarded = 0  # count of spots discarded due to low MU
        self.total_number_of_spots = 0

        if hasattr(self.dicom, "IonBeamSequence"):
            for ib in self.dicom.IonBeamSequence:
                self.total_number_of_spots += sum([icp.NumberOfScanSpotPositions for icp in ib.IonControlPointSequence])
            self.total_number_of_spots = self.total_number_of_spots // 2  # divide by 2, as each spot has two control points

    @staticmethod
    def load_dicom(inputfile):
        """
        Load the DICOM file using pydicom.

        Args:
            inputfile (str): Path to the DICOM file to be loaded.

        Returns:
            pydicom.dataset.FileDataset: The loaded DICOM object.
        """
        return pydicom.dcmread(inputfile)

    def modify(self, config):
        """Modify the DICOM file based on provided configuration options."""

        if config.fix_raystation:  # must be fixed first
            self.fix_raystation()

        if config.tolerance_table:
            self.add_table_tolerance_sequence()

        if config.approve:
            self.approve_plan()

        if config.date:
            self.set_current_date()

        if config.intent_curative:
            self.set_intent_to_curative()

        if config.rescale_dose or config.rescale_factor or config.rescale_minimize or config.weights:
            self.rescale_plan(config)

        if config.gantry_angles:
            self.set_gantry_angles(config.gantry_angles)

        if config.table_position:
            self.set_table_position(config.table_position)

        if config.snout_position:
            self.set_snout_position(config.snout_position)

        if config.treatment_machine:
            self.set_treatment_machine(config.treatment_machine)

        if config.plan_label:
            self.set_plan_label(config.plan_label)

        if config.patient_name:
            self.set_patient_name(config.patient_name)

        if config.reviewer_name:
            self.set_reviewer_name(config.reviewer_name)

        if config.wizard_tr4:
            self.set_wizard_tr4()

        if config.print_spots:
            self.print_dicom_spot_comparison(config.print_spots)

        if config.range_shifter:
            self.set_range_shifter(config.range_shifter)

        # Both rewrite the same spot lists, one dividing the meterset and one multiplying
        # it, so the result of combining them is not something anyone means to ask for.
        # Checked before either runs, so neither half is applied to a refused combination.
        if config.repeat_layer and config.repainting:
            raise ValueError(
                "-rl/--repeat_layer cannot be combined with -rp/--repainting: both rewrite the "
                "spot list of every layer, -rp dividing the MU and -rl multiplying it.")

        if config.repainting:
            self.set_repainting(config.repainting)

        # "is not None", not truthiness: -rld=0 is an invalid delay, but it is still the
        # option being given, and giving it without -rl has to say so rather than pass
        # silently. The value itself is rejected by repeat_layer_spots().
        if config.repeat_layer_delay is not None and not config.repeat_layer:
            raise ValueError(
                "-rld/--repeat_layer_delay needs -rl/--repeat_layer: a delay spot goes between "
                "passes over a layer, and without -rl there is only one pass.")

        # After rescaling, so -rf and -rd act on the plan before the delay spots exist and
        # can never push them below MU_MIN.
        if config.repeat_layer:
            self.repeat_layer_spots(config.repeat_layer, delay_mu=config.repeat_layer_delay)

        # Field duplication must be done last, when all other modifications are done
        if config.duplicate_fields:
            self.duplicate_fields(config.duplicate_fields)

    def approve_plan(self):
        """Set the approval status of the plan to 'APPROVED'."""
        d = self.dicom
        d.ApprovalStatus = "APPROVED"
        logger.info(f"New approval status {d.ApprovalStatus}")

    def set_current_date(self):
        """Set the current date and time in the DICOM plan."""
        d = self.dicom
        _dt = datetime.datetime.now()
        d.RTPlanDate = _dt.strftime("%Y%m%d")
        d.RTPlanTime = _dt.strftime("%H%M%S.%f")
        logger.info(f"New RT plan date {d.RTPlanDate}")
        logger.info(f"New RT plan time {d.RTPlanTime}")

    def set_intent_to_curative(self):
        """Set the intent of the plan to 'CURATIVE'."""
        d = self.dicom
        d.PlanIntent = "CURATIVE"
        logger.info(f"New plan intent: {d.PlanIntent}")

    def rescale_plan(self, config):
        """
        Rescale the DICOM plan based on the provided settings.

        This is the entry point used by modify(), so it is where the CLI and the web UI
        see rescaling failures surface.

        Args:
            config (Config): Parsed settings; the -rd, -rf, -rm and -w options are read.

        Raises:
            ValueError: For invalid or contradictory options, a non-positive rescale
                factor, an unusable beam dose, or a malformed plan.
            verify.RescaleVerificationError: If the independent check finds the rescaled
                plan does not deliver what was requested. The plan must not be saved.
        """
        layer_factors = None
        if config.weights:
            # Read the weights from the CSV file
            layer_factors = []

            try:
                with open(config.weights) as f:
                    layer_factors = [float(line.strip()) for line in f if line.strip()]
                logger.info(f"Read {len(layer_factors)} layer factors from '{config.weights}'")
            except ValueError:
                logger.error(f"Invalid value in weights file: '{config.weights}'")
                raise

        if config.rescale_minimize:
            # in case scale factors or layer factors are given with minimize, abort.
            if config.rescale_factor or layer_factors:
                raise ValueError("Cannot minimize plan with -rd, -rs, or -w option.")
            self.minimize_plan()
        elif config.rescale_dose:
            self.rescale_dose(config.rescale_dose, layer_factors=layer_factors)
        elif config.rescale_factor:
            self.apply_rescale_factor(config.rescale_factor, layer_factors=layer_factors)
        elif layer_factors:
            self.apply_rescale_factor(1.0, layer_factors=layer_factors)

    def minimize_plan(self):
        """Minimize the plan so the smallest spot is equal to MU_MIN."""
        d = self.dicom

        mu_lowest = 9.9e9

        for j, ib in enumerate(d.IonBeamSequence):  # loop over fields
            final_original_cumulative_weight = ib.FinalCumulativeMetersetWeight
            beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_original_cumulative_weight

            for icp in ib.IonControlPointSequence:
                if icp.NumberOfScanSpotPositions == 1:
                    weights = [icp.ScanSpotMetersetWeights]
                else:
                    weights = icp.ScanSpotMetersetWeights

                for w in weights:
                    if w > 0.0 and ((w * meterset_per_weight) < mu_lowest):
                        mu_lowest = w * meterset_per_weight

        rescale = MU_MIN / mu_lowest
        logger.info(f"lowest spot: {mu_lowest:14.2} [MU]")
        logger.info(f"rescale by factor: {rescale:.4f}")
        self.apply_rescale_factor(rescale)

    def rescale_dose(self, new_dose, layer_factors=None):
        """
        Rescale the DICOM plan to a new target dose.

        Single-field plans only. BeamDose (300A,0084) is the dose from one beam for one
        fraction, so on a multi-field plan "rescale to X Gy(RBE)" is ambiguous: X per field,
        or X for the whole plan? Rather than guess and silently mis-dose the plan, this
        refuses. Use apply_rescale_factor() / -rf to scale a multi-field plan explicitly.

        The dose already in the plan may have drifted from earlier manipulation, deliberately
        or not, and the rescale factor is derived from it. The dose found, the dose requested,
        the resulting factor and the meterset before and after are therefore reported at
        warning level, so they appear without needing -v.

        Args:
            new_dose (float): The new target dose in Gy(RBE) to which the plan should be rescaled.
            layer_factors (list of float, optional): Optional list of scaling factors for each energy layer.
                If provided, these factors are applied to each corresponding energy layer in the plan.
                The length of the list should match the number of real energy layers in the DICOM plan.

        Raises:
            ValueError: if the plan has more than one field, or has no usable beam dose.
            verify.RescaleVerificationError: propagated from apply_rescale_factor() if the
                independent check finds the result does not match what was requested.
        """
        d = self.dicom
        rbs = d.FractionGroupSequence[0].ReferencedBeamSequence

        if len(rbs) > 1:
            raise ValueError(
                f"Cannot rescale to a target dose: this plan has {len(rbs)} fields. "
                "BeamDose is the dose of a single field, so the requested dose is ambiguous "
                "(per field, or for the whole plan?). Use -rf to apply an explicit factor instead.")

        if "BeamDose" not in rbs[0]:
            raise ValueError(
                "Cannot rescale to a target dose: this plan has no BeamDose (300A,0084) to scale from. "
                "Use -rf to apply an explicit factor instead.")

        current_dose = float(rbs[0].BeamDose)
        if current_dose <= 0.0:
            raise ValueError(
                f"Cannot rescale to a target dose: the dose found in this plan is {current_dose:.4f} Gy(RBE). "
                "Use -rf to apply an explicit factor instead.")

        scale_factor = new_dose / current_dose
        meterset_before = float(rbs[0].BeamMeterset) if "BeamMeterset" in rbs[0] else None

        # Report before acting, so the operator still sees the intent if the rescale fails.
        logger.warning(HLINE)
        logger.warning("Rescaling dose:")
        logger.warning(f"Dose found in plan             : {current_dose:12.4f}  Gy(RBE)")
        logger.warning(f"Dose requested                 : {new_dose:12.4f}  Gy(RBE)")
        logger.warning(f"Rescale factor to be applied   : {scale_factor:12.4f}")
        if meterset_before is not None:
            logger.warning(f"Beam Meterset before           : {meterset_before:12.4f}  MU")

        self.apply_rescale_factor(scale_factor, layer_factors=layer_factors)

        if meterset_before is not None:
            logger.warning(f"Beam Meterset after            : {float(rbs[0].BeamMeterset):12.4f}  MU")
        logger.warning(HLINE)

    def apply_rescale_factor(self, rescale_factor=1.0, layer_factors=None):
        """
        Apply a rescaling factor to the entire DICOM plan.

        This method resizes the dose and meterset weights across all fields and energy layers of the DICOM plan.
        It supports a global rescale factor, as well as individual rescale factors for each energy layer. Additionally,
        it handles spot elimination for spots that fall below a minimum monitor unit (MU) threshold.

        Args:
            rescale_factor (float): The global rescale factor to be applied across all fields and energy layers.
                Defaults to 1.0 if no rescaling is needed.
            layer_factors (list of float, optional): Optional list of rescale factors for each energy layer.
                If provided, these will be applied to each corresponding energy layer. The length of this list must match
                the number of real energy layers in the plan.

        Raises:
            ValueError: If the rescale factor is not positive, if any layer factor is
                negative, or if the number of layer factors does not match the number of
                energy layers. Also raised for a malformed plan whose IonBeamSequence and
                ReferencedBeamSequence disagree in length.
            verify.RescaleVerificationError: If the independent check at the end of this
                method finds that the rescaled plan does not deliver what was requested.
                The plan is left modified but must not be used; callers should report the
                message, which lists every failed check.
        """
        d = self.dicom

        # A non-positive factor produces a plan with zero or negative MU, which is not
        # deliverable. Refuse rather than write such a file out.
        if rescale_factor <= 0.0:
            raise ValueError(
                f"Rescale factor must be positive, got {rescale_factor}. "
                "A zero or negative factor would produce a plan with no deliverable MU.")

        if layer_factors and any(lf < 0.0 for lf in layer_factors):
            raise ValueError("Layer factors must not be negative.")

        # Measured before anything is touched, so the independent check at the end of this
        # method has something to compare against. See dicomfix/verify.py.
        _before = verify.snapshot(d)

        layer_factors_len = 0

        if layer_factors:
            layer_factors_len = len(layer_factors)

        for j, ib in enumerate(d.IonBeamSequence):  # loop over fields

            logger.info(f"Rescaling field # {j+1:02} by factor {rescale_factor:.4f}")

            # ion_control_point_sequence = ion_beam.IonControlPointSequence
            # final_original_cumulative_weight = ib.FinalCumulativeMetersetWeight
            # number_of_control_points = ion_beam.NumberOfControlPoints
            number_of_energy_layers = int(ib.NumberOfControlPoints / 2)

            if layer_factors:
                if layer_factors_len != number_of_energy_layers:
                    raise Exception(f"Number of energy layer scaling factors ({layer_factors_len}) must " +
                                    f"match number of energy layers in dicom file ({number_of_energy_layers}).")
            original_beam_dose = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose
            original_beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset  # in MU
            # original_beam_meterset_per_weight = original_beam_meterset / ib.FinalCumulativeMetersetWeight
            new_beam_dose = original_beam_dose * rescale_factor
            new_beam_meterset = original_beam_meterset * rescale_factor  # in MU
            new_beam_meterset_per_weight = new_beam_meterset / ib.FinalCumulativeMetersetWeight

            original_cumulative_meterset_weight = 0.0  # increases every energy layer
            new_cumulative_meterset_weight = 0.0  # increases every energy layer
            real_energy_layer_index = 0

            for i, icp in enumerate(ib.IonControlPointSequence):  # loop over energy layers

                logger.debug(f" --------- Processing energy layer {i}")

                # value to be written here is that of the previous energy layer
                icp.CumulativeMetersetWeight = new_cumulative_meterset_weight

                # If a single spot is in an energy layer, it will not be stored into a list by pydicom.
                # Therefore it is casted into a list here, to not break the subsequent code.
                if icp.NumberOfScanSpotPositions == 1:
                    original_spot_weights = [icp.ScanSpotMetersetWeights]
                else:
                    original_spot_weights = icp.ScanSpotMetersetWeights

                new_spot_weights = [0.0] * len(original_spot_weights)

                # Initialize layer_factor to 1.0 for all spots by default
                layer_factor = 1.0

                # Check if this is a real energy layer (non-repeated one)
                # If there are non-zero weights, this is a real energy layer.
                # Reuse original_spot_weights above: it already handles the single-spot case via
                # NumberOfScanSpotPositions. Testing isinstance(..., list) would be wrong here,
                # because after a previous rescale pydicom stores these as MultiValue, which is
                # not a list subclass.
                if any(w > 0.0 for w in original_spot_weights):
                    # Apply the correct factor for the real energy layer
                    if layer_factors:
                        logger.info(
                            f"Reduce cumulative weight in layer {real_energy_layer_index} " +
                            f"by factor: {layer_factors[real_energy_layer_index]:.4f}")
                        layer_factor = layer_factors[real_energy_layer_index]

                    # Increment the real energy layer index for the next valid layer
                    real_energy_layer_index += 1

                # eliminate spots which fall below MU_MIN after rescaling
                for k, w in enumerate(original_spot_weights):
                    value = w * layer_factor
                    if value > 0.0 and value * new_beam_meterset_per_weight < MU_MIN:
                        # build position string: (x,y) in cm
                        x = float(icp.ScanSpotPositionMap[2*k]) * 0.1
                        y = float(icp.ScanSpotPositionMap[2*k+1]) * 0.1

                        _lstr = f"{real_energy_layer_index:2}" + f" ({icp.NominalBeamEnergy:.2f} MeV)"
                        _pstr = f"({x:.2},{y:.2}) cm"
                        # _vstr = f"{value:.2f}"
                        _mstr = f"{value*new_beam_meterset_per_weight:.2f} MU"

                        logger.warning(f"  In layer {_lstr} Discarding spot with meterset {_mstr}" +
                                       f" at position {_pstr}  due to low MU")
                        self.spots_discarded += 1
                        value = 0.0
                    new_spot_weights[k] = value

                icp.ScanSpotMetersetWeights = new_spot_weights

                original_cumulative_meterset_weight += sum(original_spot_weights)
                new_cumulative_meterset_weight += sum(new_spot_weights)  # Calculate the new cumulative weight

                logger.debug(f"Layer {i:02} Cumulative Weight old-new: " +
                             f"{original_cumulative_meterset_weight} - {new_cumulative_meterset_weight}")

            # test if real_energy_layer_index is equal to the number of energy layers
            if layer_factors and real_energy_layer_index != number_of_energy_layers:
                raise ValueError(f"Given new energy layer weights {real_energy_layer_index} must " +
                                 f"match number of energy layers in dicom file {number_of_energy_layers}.")

            # repeat loop to set the CumulativeDoseReferenceCoefficient for each energy layer
            # The CumulativeDoseReferenceCoefficient is rather a dimensionless factor, which is used to
            # track the delivered dose as the energy layers are delivered.
            # this may change, if spots were dropped, or if the layer_factors were applied.
            cumulative_spot_meterset_weight = 0
            logger.info("CumulativeDoseReferenceCoefficient   Original        New   ")
            logger.info(HLINE)

            for i, icp in enumerate(ib.IonControlPointSequence):
                cdrc_original = icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient
                # new_cumulative_meterset_weight is the total meterset weight of the field.
                # The new ReferenceDoseCoefficient must be normalized so it is 1.0 at the last IonControlPoint.
                if new_cumulative_meterset_weight != 0:  # avoid division by zero
                    cdrc_new = cumulative_spot_meterset_weight / new_cumulative_meterset_weight
                else:
                    cdrc_new = 0.0

                icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient = cdrc_new

                if icp.NumberOfScanSpotPositions == 1:
                    cumulative_spot_meterset_weight += icp.ScanSpotMetersetWeights
                else:
                    cumulative_spot_meterset_weight += sum(icp.ScanSpotMetersetWeights)

                logger.info(f"    Layer {i:02}                {cdrc_original:14.3f}  {cdrc_new:14.3f}")
            logger.info(HLINE)

            # set remaining meta data
            logger.debug(f"IonBeamSequence[{j}]")
            d.IonBeamSequence[j].FinalCumulativeMetersetWeight = new_cumulative_meterset_weight
            d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset = new_beam_meterset
            d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose = new_beam_dose

            logger.info("                                           Original           New   ")
            logger.info(HLINE)
            logger.info("Final Cumulative Meterset Weight   : " +
                        f"{original_cumulative_meterset_weight:14.2f}  {new_cumulative_meterset_weight:14.2f}  ")
            logger.info("Beam Meterset                      : " +
                        f"{original_beam_meterset:14.2f}  {new_beam_meterset:14.2f}  MU ")
            logger.info("Beam Dose                          : " +
                        f"{original_beam_dose:14.2f}  {new_beam_dose:14.2f}  Gy(RBE)")
            logger.info(HLINE)
        # end of j,ion_beam loop over IonBeamSequence

        self._rescale_prescription_dose(rescale_factor)

        # Independent check that the plan now delivers what was asked for. Deliberately
        # recomputed from the DICOM tags by code that shares nothing with the above, so a
        # bug introduced here cannot hide itself. Raises rather than returning a bad plan.
        # With per-layer factors no single factor applies, so only the integrity checks run.
        verify.verify_rescale(_before, d, None if layer_factors else rescale_factor, mu_min=MU_MIN)

    def _rescale_prescription_dose(self, rescale_factor):
        """
        Scale TargetPrescriptionDose (300A,0026) along with the beam doses.

        The prescription is plan-level, so it is scaled once rather than per field.
        Leaving it untouched would produce a plan whose stated prescription contradicts
        the dose its beams actually deliver.

        Only TargetPrescriptionDose is scaled. Other dose-valued elements in
        DoseReferenceSequence are constraints rather than delivered dose, so they are
        deliberately left alone and reported instead.

        Args:
            rescale_factor (float): The same factor that was applied to the beam doses.
        """
        d = self.dicom
        # Dose-valued, but a limit rather than something the plan delivers.
        _constraints = ("DeliveryMaximumDose", "DeliveryWarningDose", "TargetMaximumDose",
                        "TargetMinimumDose", "OrganAtRiskMaximumDose", "OrganAtRiskLimitDose",
                        "OrganAtRiskFullVolumeDose")

        for dr in d.get("DoseReferenceSequence", []):
            if "TargetPrescriptionDose" in dr:
                original = float(dr.TargetPrescriptionDose)
                dr.TargetPrescriptionDose = original * rescale_factor
                logger.warning(f"Target Prescription Dose       : {original:12.4f} ->"
                               f"{float(dr.TargetPrescriptionDose):12.4f}  Gy(RBE)")

            left_alone = [name for name in _constraints if name in dr]
            if left_alone:
                logger.warning(f"NOT rescaled (dose constraints) : {', '.join(left_alone)}")

    def duplicate_fields(self, n):
        """
        Duplicate fields in the DICOM plan n times.

        Args:
            n (int): Number of times to duplicate each field.
        """
        d = self.dicom
        fgs = d.FractionGroupSequence[0]
        nf = d.FractionGroupSequence[0].NumberOfBeams
        rbs = copy.deepcopy(fgs.ReferencedBeamSequence)
        ibs = copy.deepcopy(d.IonBeamSequence)

        new_rbs = [copy.deepcopy(item) for item in rbs for _ in range(n)]
        new_ibs = [copy.deepcopy(item) for item in ibs for _ in range(n)]

        d.FractionGroupSequence[0].ReferencedBeamSequence = new_rbs
        d.FractionGroupSequence[0].NumberOfBeams = len(new_rbs)
        d.IonBeamSequence = new_ibs
        for i, ib in enumerate(d.IonBeamSequence):
            copy_number = i % n
            ib.BeamName += f" ({copy_number + 1}/{n})"  # append copy id
            logger.info(f"{ib.BeamName}")
            ib.BeamNumber = i+1
            new_rbs[i].ReferencedBeamNumber = i+1

        logger.info(f"Duplicated {nf} field(s) {n} times.")

    def set_gantry_angles(self, gantry_angles):
        """
        Set the gantry angles for each field.

        Args:
            gantry_angles (tuple of float): A tuple containing the new gantry angle for each field.
        """
        d = self.dicom
        number_of_fields = len(d.IonBeamSequence)
        if len(gantry_angles) != number_of_fields:
            raise ValueError(f"Number of gantry angles must match number of fields. {number_of_fields} fields found.")

        for i, ibs in enumerate(d.IonBeamSequence):
            old_ga = ibs.IonControlPointSequence[0].GantryAngle
            ibs.IonControlPointSequence[0].GantryAngle = gantry_angles[i]
            _ga = ibs.IonControlPointSequence[0].GantryAngle
            logger.info(f"Gantry angle field #{i+1} changed from {old_ga:8.2f} to {_ga:8.2f}")

    def set_table_position(self, table_position):
        """
        Set the table position using three coordinates.

        Args:
            table_position (tuple of float): A tuple containing the new vertical, longitudinal,
                                            and lateral positions, in that order. Each value is in [mm].
        """
        d = self.dicom
        if len(table_position) != 3:
            raise ValueError(f"Table Position expects three values, got {len(table_position)}.")

        last_ibs = None
        for ibs in d.IonBeamSequence:
            last_ibs = ibs
            # check if ibs.IonControlPointSequence has the required attributes
            ibs.IonControlPointSequence[0].TableTopVerticalPosition = table_position[0]
            ibs.IonControlPointSequence[0].TableTopLongitudinalPosition = table_position[1]
            ibs.IonControlPointSequence[0].TableTopLateralPosition = table_position[2]

        if last_ibs:
            logger.info(
                f"Table vertical position     : {last_ibs.IonControlPointSequence[0].TableTopVerticalPosition * 0.1:8.2f} cm")
            logger.info("Table longitudinal position : " +
                        f"{last_ibs.IonControlPointSequence[0].TableTopLongitudinalPosition * 0.1:8.2f} cm")
            logger.info(
                f"Table lateral position      : {last_ibs.IonControlPointSequence[0].TableTopLateralPosition * 0.1:8.2f} cm")
        else:
            raise Exception("No IonBeamSequence found to set table position.")

    def set_snout_position(self, snout_position):
        """
        Set snout position for all fields.

        Args:
            snout_position (float): The new snout position to set in mm.
        """
        d = self.dicom
        for ibs in d.IonBeamSequence:
            ibs.IonControlPointSequence[0].SnoutPosition = snout_position
        _sp = d.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition
        logger.info(f"Snout position set to {_sp * 0.1: 8.2f}[cm] for all fields.")

    def set_range_shifter(self, range_shifter=None):
        """
        Set the range shifter for all fields.

        Args:
            range_shifter (str): The new range shifter name.
            Can be None, "None", "RS_2CM" or "RS_5CM".

        """
        d = self.dicom

        # None (the API default), the "NONE" sentinel from the command line and the
        # plain "None" string from the web selectbox all mean "remove it".
        if range_shifter is None or str(range_shifter).upper() in (RANGE_SHIFTER_NONE, ""):
            n = 0
            for ibs in d.IonBeamSequence:
                if hasattr(ibs, "RangeShifterSequence"):
                    del ibs.RangeShifterSequence
                    n += 1
                ibs.NumberOfRangeShifters = 0
                for ics in ibs.IonControlPointSequence:
                    # Leaving these behind would reference a range shifter which no longer exists.
                    if hasattr(ics, "RangeShifterSettingsSequence"):
                        del ics.RangeShifterSettingsSequence
            logger.info(f"Range Shifter removed from {n} field(s).")
            return

        if range_shifter not in RANGE_SHIFTER_WET:
            raise ValueError(f"Range shifter must be 'RS_2CM', 'RS_5CM' or None, got '{range_shifter}'.")

        for ibs in d.IonBeamSequence:
            ibs.NumberOfRangeShifters = 1
            if not hasattr(ibs, "RangeShifterSequence"):
                ibs.RangeShifterSequence = [pydicom.Dataset()]
            ibs.RangeShifterSequence[0].RangeShifterNumber = 1
            ibs.RangeShifterSequence[0].RangeShifterID = range_shifter
            ibs.RangeShifterSequence[0].RangeShifterType = "BINARY"

            for ics in ibs.IonControlPointSequence:
                if not hasattr(ics, "RangeShifterSettingsSequence"):
                    ics.RangeShifterSettingsSequence = [pydicom.Dataset()]
                rsss = ics.RangeShifterSettingsSequence[0]
                rsss.RangeShifterSetting = 'IN'
                rsss.IsocenterToRangeShifterDistance = 98.0
                rsss.RangeShifterWaterEquivalentThickness = RANGE_SHIFTER_WET[range_shifter]
                rsss.ReferencedRangeShifterNumber = 1
        logger.info(f"Range Shifter set to '{range_shifter}' for all fields.")

    def set_repainting(self, n):
        """
        Repeat each spot n times and divide their weights by n (floating point).
        This avoids the need for numpy and works with standard Python lists.
        """
        d = self.dicom
        for j, ib in enumerate(d.IonBeamSequence):
            final_original_cumulative_weight = ib.FinalCumulativeMetersetWeight
            beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_original_cumulative_weight

            for i, icp in enumerate(ib.IonControlPointSequence):
                # Rescale the weights and extend it by factor n, so cumulative weights stay constant
                if icp.NumberOfScanSpotPositions == 1:
                    w = [icp.ScanSpotMetersetWeights]
                else:
                    w = icp.ScanSpotMetersetWeights
                new_weights = []

                # every second control point the weights are always set to 0
                # so we only rescale the even control point weights,
                # put the spot positions still must be repeated n times.
                if i % 2 == 0:
                    new_weights = [weight / n for weight in w]
                else:
                    new_weights = [0.0] * len(w)
                new_weights *= n  # Repeat the weights n times
                icp.ScanSpotMetersetWeights = new_weights
                icp.ScanSpotPositionMap = list(icp.ScanSpotPositionMap) * n
                icp.NumberOfScanSpotPositions *= n
                logger.debug(f"Control Point {i} in field {ib.BeamName} has {icp.NumberOfScanSpotPositions} spots.")
                logger.debug(f"Control Point {i} in field {ib.BeamName} has weights: {len(new_weights)}")
                logger.debug(f"Control Point {i} in field {ib.BeamName} has len scanspot position map: " +
                             f"{len(icp.ScanSpotPositionMap)}")
                # Check for spots below MU_MIN
                if i % 2 == 0:
                    _mu = [w * meterset_per_weight for w in new_weights]
                    if any(mu < MU_MIN for mu in _mu):
                        logger.warning(f"Some spots in field {ib.BeamName} fell below {MU_MIN} MU after rescaling.")
                        logger.warning(f"Lowest value found: {min(_mu):.2f} MU")
                        self.spots_discarded += sum(mu < MU_MIN for mu in _mu)
                        # Set weights below MU_MIN to zero
                        icp.ScanSpotMetersetWeights = [w if mu >= MU_MIN else 0.0 for w, mu in zip(new_weights, _mu)]
                    logger.debug(f"Lowest value found: {min(_mu):.2f} MU")

            logger.info(f"Repainting field {ib.BeamName} with {n} times the number of spots.")

    def repeat_layer_spots(self, n, delay_mu=None):
        """
        Repeat the spot list of every energy layer n times, in place.

        The layer's spot pattern is delivered n times in a row before the plan moves on to
        the next energy, and with delay_mu a delay spot is shimmed into each gap between
        consecutive passes:

            layer 1 (E1):  [spots] D [spots] D ... [spots]     n passes, n-1 delay spots
            layer 2 (E2):  [spots] D [spots] D ... [spots]

        This is for depth dose curve scanning: a stepper actuator advances the detector
        one position between passes, so a whole curve is measured in a single delivery
        rather than one beam request per point. The delay spot sits far out in the field,
        at DELAY_SPOT_POSITION, forcing the scanning magnets to sweep there and back,
        which buys the actuator the time it needs to reach the next position.

        Nothing is added to the IonControlPointSequence: the control point count, the layer
        energies and their order are untouched. That is deliberate, and it is what makes
        this deliverable. The delivery system requires the energy layers of a field to be
        strictly decreasing, so any scheme which repeats or inserts layers steps the energy
        back up and is refused by the console.

        Unlike set_repainting(), the weights are not divided: every pass delivers the
        original per-spot MU, so the layer delivers n times its MU and each detector
        position receives what the original plan gave. Every total therefore changes:
        FinalCumulativeMetersetWeight and BeamMeterset grow with the repeats and the delay
        spots, while BeamDose grows by n alone, since the delay spots dump into a sink far
        out in the field and must not count towards the target dose.

        Args:
            n (int): Number of passes over each layer's spot list. 1 is a no-op.
            delay_mu (float, optional): Monitor units of the delay spot placed between
                consecutive passes. None inserts no delay spots.

        Raises:
            ValueError: If n is not an integer of at least 1, if delay_mu is below MU_MIN,
                or if a field has no total meterset weight to convert MU against.
            verify.PlanVerificationError: If the independent check finds the expanded plan
                does not deliver the original pattern n times. It must not be saved.
        """
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"Number of layer repeats must be an integer of at least 1, got {n!r}.")

        if delay_mu is not None:
            if not isinstance(delay_mu, (int, float)) or isinstance(delay_mu, bool):
                raise ValueError(f"Delay spot meterset must be a number of MU, got {delay_mu!r}.")
            if delay_mu < MU_MIN:
                raise ValueError(
                    f"Delay spot meterset must be at least {MU_MIN} MU, got {delay_mu}. "
                    "A smaller spot is not deliverable and would be discarded, silently "
                    "removing the delay.")

        d = self.dicom

        if n == 1:
            logger.info("Layer repeat of 1 requested, plan left unchanged.")
            if delay_mu:
                logger.warning("No delay spots inserted: they go between passes, and 1 pass has no gaps.")
            return

        # Measured before anything is touched, for the independent check at the end.
        _before = verify.snapshot(d)

        for j, ib in enumerate(d.IonBeamSequence):
            icps = ib.IonControlPointSequence
            original_final = float(ib.FinalCumulativeMetersetWeight)

            # Everything below is expressed per unit meterset weight, which a field with
            # no total weight does not have. Say so, rather than divide by zero.
            if original_final <= 0.0:
                raise ValueError(
                    f"Field #{j+1} '{ib.BeamName}' has FinalCumulativeMetersetWeight "
                    f"{original_final}, so its MU per meterset weight is undefined and its "
                    "layers cannot be repeated.")

            rb = d.FractionGroupSequence[0].ReferencedBeamSequence[j]
            original_beam_meterset = float(rb.BeamMeterset)
            meterset_per_weight = original_beam_meterset / original_final

            self._warn_if_energies_do_not_decrease(ib, j)

            # The plan stores meterset weights, not MU, so the requested delay MU is
            # converted the same way minimize_plan() and set_repainting() do. Quantized,
            # because this weight lands in the cumulative weights, which are DS and so
            # limited to 16 characters. Six decimals is about a part in 1e9 of a delay
            # spot, far below anything deliverable.
            delay_weight = 0.0
            if delay_mu:
                delay_weight = float(Decimal(delay_mu / meterset_per_weight).quantize(Decimal("0.000001")))

            original_spots = icps[0].NumberOfScanSpotPositions
            for i, icp in enumerate(icps):
                # A single spot is not stored as a list by pydicom, so cast it to one.
                # NumberOfScanSpotPositions, not isinstance(..., list): after an earlier
                # modification pydicom stores these as MultiValue, which is not a list.
                if icp.NumberOfScanSpotPositions == 1:
                    weights = [icp.ScanSpotMetersetWeights]
                else:
                    weights = list(icp.ScanSpotMetersetWeights)
                positions = list(icp.ScanSpotPositionMap)

                # Every second control point repeats the positions with the weights
                # zeroed, so only the even ones carry meterset -- delay spots included.
                pass_weights = [float(w) for w in weights] if i % 2 == 0 else [0.0] * len(weights)
                gap_weight = delay_weight if i % 2 == 0 else 0.0

                new_weights, new_positions = [], []
                for repeat in range(n):
                    new_weights += pass_weights
                    new_positions += positions
                    if delay_mu and repeat < n - 1:
                        new_weights.append(gap_weight)
                        new_positions += list(DELAY_SPOT_POSITION)

                icp.ScanSpotMetersetWeights = new_weights
                icp.ScanSpotPositionMap = new_positions
                icp.NumberOfScanSpotPositions = len(new_weights)

            new_final = self._renumber_cumulative_weights(icps)
            ib.FinalCumulativeMetersetWeight = new_final

            # Derived from the weights rather than multiplied by n, so the declared total
            # matches the spots underneath it with the delay spots counted in.
            rb.BeamMeterset = new_final * meterset_per_weight
            if "BeamDose" in rb:
                rb.BeamDose = float(rb.BeamDose) * n

            layers = len(icps) // 2
            delay_spots = layers * (n - 1) if delay_mu else 0
            logger.info(f"Repeating the spot list of each layer in field #{j+1:02} "
                        f"'{ib.BeamName}' {n} times.")
            logger.info("                                           Original           New   ")
            logger.info(HLINE)
            logger.info("Spots in first energy layer        : " +
                        f"{original_spots:14}  {icps[0].NumberOfScanSpotPositions:14}  ")
            logger.info("Final Cumulative Meterset Weight   : " +
                        f"{original_final:14.2f}  {new_final:14.2f}  ")
            logger.info("Beam Meterset                      : " +
                        f"{original_beam_meterset:14.2f}  {float(rb.BeamMeterset):14.2f}  MU ")
            logger.info("Number of control points           : " +
                        f"{ib.NumberOfControlPoints:14}  {ib.NumberOfControlPoints:14}  (unchanged)")
            logger.info(HLINE)

            if delay_mu:
                # Warning level, so the extra MU and the dose caveat are seen without -v.
                delivered = delay_weight * meterset_per_weight
                x, y = DELAY_SPOT_POSITION
                logger.warning(f"Inserted {delay_spots} delay spot(s) of {delivered:.2f} MU at "
                               f"({x * 0.1:.1f},{y * 0.1:.1f}) cm, {n - 1} per layer, "
                               f"adding {delay_spots * delivered:.2f} MU to field #{j+1:02}.")
                logger.warning("Beam Dose is n times the original and does NOT include the delay spots.")
            logger.warning(f"Field #{j+1:02} now has {icps[0].NumberOfScanSpotPositions} spots in its "
                           "first energy layer. Check this is within what the console accepts.")

        # Independent check that the expanded plan delivers the original pattern n times,
        # recomputed from the DICOM tags by code which shares nothing with the above.
        verify.verify_layer_spot_repeat(_before, d, n,
                                        delay_mu=delay_mu, delay_position=DELAY_SPOT_POSITION)

    @staticmethod
    def _warn_if_energies_do_not_decrease(ib, j):
        """
        Report layer energies which do not descend strictly, without changing anything.

        The delivery system requires the energy layers of a field to be strictly
        decreasing, for the beam line magnets' hysteresis calibration. A plan which
        breaks that is refused by the console, and this is cheaper to hear about here
        than there. It is a property of the plan as given, not of anything dicomfix did,
        so it is reported rather than raised.
        """
        energies = [float(icp.NominalBeamEnergy) for icp in ib.IonControlPointSequence[::2]
                    if "NominalBeamEnergy" in icp]
        offenders = [(a, b) for a, b in zip(energies, energies[1:]) if b >= a]
        if offenders:
            a, b = offenders[0]
            logger.warning(
                f"Field #{j+1:02} '{ib.BeamName}' has {len(offenders)} energy layer(s) which do not "
                f"decrease (first: {a:.3f} -> {b:.3f} MeV). The delivery system may refuse this plan.")

    @staticmethod
    def _renumber_cumulative_weights(icps):
        """
        Recompute the cumulative meterset weights of a control point sequence.

        CumulativeMetersetWeight is the weight delivered up to and not including a control
        point, so the running total is written before that control point's own spots are
        added. The dose reference coefficient is the same quantity normalized to 1.

        Decimal, not float: these are written as DS, which allows 16 characters, and a
        float repr of a long sum overruns that. Summing in Decimal and quantizing also
        keeps the sequence exactly monotonic.

        Args:
            icps (Sequence): Control points of one field, with their weights already set.

        Returns:
            float: The new FinalCumulativeMetersetWeight, which the caller must store.
        """
        places = Decimal("0.000001")

        running = Decimal(0)
        cumulative = []
        for icp in icps:
            cumulative.append(running)
            weights = ([icp.ScanSpotMetersetWeights] if icp.NumberOfScanSpotPositions == 1
                       else icp.ScanSpotMetersetWeights)
            running += sum((Decimal(str(float(w))) for w in weights), Decimal(0))

        final = running.quantize(places)

        for icp, weight in zip(icps, cumulative):
            icp.CumulativeMetersetWeight = float(weight.quantize(places))
            # Runs 0 to 1 across the sequence. Absent on plans not put through -rs.
            if hasattr(icp, "ReferencedDoseReferenceSequence"):
                icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient = \
                    float(weight / running) if running else 0.0

        return float(final)

    def set_treatment_machine(self, machine_name):
        """
        Set the treatment machine name for all fields.

        Args:
            machine_name (str): The name of the new treatment machine.
        """
        d = self.dicom
        for ibs in d.IonBeamSequence:
            ibs.TreatmentMachineName = machine_name
        logger.info(f"New Treatment Machine Name  : '{d.IonBeamSequence[-1].TreatmentMachineName}'")

    def set_plan_label(self, plan_label):
        """
        Set the RT plan label.

        Args:
            plan_label (str): The new label for the RT plan.
        """
        d = self.dicom
        d.RTPlanLabel = plan_label
        logger.info(f"New RT plan label           : '{d.RTPlanLabel}'")

    def set_patient_name(self, patient_name):
        """
        Set the patient's name in the DICOM plan.

        Args:
            patient_name (str): The patient's new name.
        """
        d = self.dicom
        self.dicom.PatientName = patient_name
        logger.info(f"New patient name {d.PatientName}")

    def set_reviewer_name(self, reviewer_name):
        """
        Set the reviewer's name in the DICOM plan.

        Args:
            reviewer_name (str): The reviewer's new name.
        """
        d = self.dicom
        d.ReviewerName = reviewer_name
        logger.info(f"New reviewer name {d.ReviewerName}")

    def set_wizard_tr4(self):
        """
        Prepare the DICOM plan for TR4.

        This method sets the treatment machine name to "TR4", adjusts all gantry angles to 90 degrees,
        sets the snout position to 421.0 mm, and approves the plan.
        """
        d = self.dicom
        d.ApprovalStatus = "APPROVED"
        for ibs in d.IonBeamSequence:
            ibs.TreatmentMachineName = "TR4"
            ibs.IonControlPointSequence[0].GantryAngle = 90.0
            ibs.IonControlPointSequence[0].SnoutPosition = 421.0  # 42.1 cm
        logger.info(f"All gantry angles set to   \
                        {d.IonBeamSequence[-1].IonControlPointSequence[0].GantryAngle:8.2f} deg")
        logger.info(f"All snout positions set to \
                        {d.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition*0.1:8.2f} cm")

    def add_table_tolerance_sequence(self):
        d = self.dicom

        if not hasattr(d, "IonToleranceTableSequence"):
            logger.info(" Adding a IonToleranceTableSequence T1.")
            d.IonToleranceTableSequence = [pydicom.Dataset()]
        logger.info(" Setting default values for IonToleranceTableSequence T1.")
        d.IonToleranceTableSequence[0].ToleranceTableNumber = 1
        d.IonToleranceTableSequence[0].ToleranceTableLabel = "T1"
        d.IonToleranceTableSequence[0].GantryAngleTolerance = 0.5
        d.IonToleranceTableSequence[0].SnoutPositionTolerance = 5.0
        d.IonToleranceTableSequence[0].PatientSupportAngleTolerance = 3.0
        d.IonToleranceTableSequence[0].TableTopPitchAngleTolerance = 3.0
        d.IonToleranceTableSequence[0].TableTopRollAngleTolerance = 3.0
        d.IonToleranceTableSequence[0].TableTopVerticalPositionTolerance = 20.0
        d.IonToleranceTableSequence[0].TableTopLongitudinalPositionTolerance = 20.0
        d.IonToleranceTableSequence[0].TableTopLateralPositionTolerance = 20.0

    def fix_raystation(self):
        """
        Apply RayStation-specific fixes to the DICOM plan.

        This method performs several adjustments to make the DICOM file compatible with RayStation
        and Varian proton systems, including:

        - Set the Manufacturer to "Varian Medical System Particle Therapy"
        - Remove unsupported delta couch shift tags (300a,01d2), (300a,01d4), and (300a,01d6)
        from the PatientSetupSequence.
        - Ensure the DoseReferenceSequence exists, with a default reference to a "Target".
        - Add a default IonToleranceTableSequence if missing, with specific tolerance values.
        - Set table positions (vertical, longitudinal, lateral), pitch, roll, patient support,
        and snout positions to 0 if they are missing or None.
        - Set SnoutPosition to 421.0 mm (42.1 cm) and MetersetRate to 100 if missing or None.
        - Ensure each control point in the IonControlPointSequence contains a reference to
        the dose reference and calculate the CumulativeDoseReferenceCoefficient.
        - Set ReferencedToleranceTableNumber to 1 for all beams.
        """
        logger.info("Apply RayStation Fix")

        d = self.dicom
        d.Manufacturer = "Varian Medical System Particle Therapy"

        if 'PatientSetupSequence' in d:
            for ps in d.PatientSetupSequence:
                ps.SetupTechnique = "ISOCENTRIC"
                # Remove specific delta couch shift tags if they exist
                if (0x300a, 0x01d2) in ps:
                    logger.info(" RayStation: Removing (300a,01d2) from PatientSetupSequence")
                    del ps[0x300a, 0x01d2]  # Unset (300a,01d2)
                if (0x300a, 0x01d4) in ps:
                    logger.info(" RayStation: Removing (300a,01d4) from PatientSetupSequence")
                    del ps[0x300a, 0x01d4]  # Unset (300a,01d4)
                if (0x300a, 0x01d6) in ps:
                    logger.info(" RayStation: Removing (300a,01d6) from PatientSetupSequence")
                    del ps[0x300a, 0x01d6]  # Unset (300a,01d6)

        if not hasattr(d, "DoseReferenceSequence"):
            logger.info(" RayStation: DoseReferenceSequence was missing. Adding a TARGET as #1.")
            d.DoseReferenceSequence = [pydicom.Dataset()]
            d.DoseReferenceSequence[0].DoseReferenceNumber = 1
            d.DoseReferenceSequence[0].DoseReferenceUID = generate_uid()
            d.DoseReferenceSequence[0].DoseReferenceStructureType = "SITE"
            d.DoseReferenceSequence[0].DoseReferenceDescription = "Target"

        if not hasattr(d, "IonToleranceTableSequence"):
            logger.info(" RayStation: IonToleranceTableSequence was missing. Adding default T1.")
            self.add_table_tolerance_sequence()

        # Loop over fields
        for ib in d.IonBeamSequence:
            ib.Manufacturer = "Varian Medical System Particle Therapy"
            ib.PatientSupportAccessoryCode = "AC123"

            # TODO, we need a helper function which only sets if attribute is missing

            # Loop over snout sequence and set SnoutID to "S1"
            for ss in ib.SnoutSequence:
                ss.SnoutID = "S1"

            # Check if table position are missing. Attributes may be there, but set to None

            if ib.IonControlPointSequence[0].TableTopVerticalPosition is None:
                ib.IonControlPointSequence[0].TableTopVerticalPosition = 0.0
            if ib.IonControlPointSequence[0].TableTopLongitudinalPosition is None:
                ib.IonControlPointSequence[0].TableTopLongitudinalPosition = 0.0
            if ib.IonControlPointSequence[0].TableTopLateralPosition is None:
                ib.IonControlPointSequence[0].TableTopLateralPosition = 0.0
            if ib.IonControlPointSequence[0].TableTopPitchAngle is None:
                ib.IonControlPointSequence[0].TableTopPitchAngle = 0.0
            if ib.IonControlPointSequence[0].TableTopRollAngle is None:
                ib.IonControlPointSequence[0].TableTopRollAngle = 0.0
            if ib.IonControlPointSequence[0].PatientSupportAngle is None:
                ib.IonControlPointSequence[0].PatientSupportAngle = 0.0
            if ib.IonControlPointSequence[0].GantryAngle is None:
                ib.IonControlPointSequence[0].GantryAngle = 0.
            if ib.IonControlPointSequence[0].SnoutPosition is None:
                ib.IonControlPointSequence[0].SnoutPosition = 0.0

            if not hasattr(ib.IonControlPointSequence[0], "SnoutPosition"):
                ib.IonControlPointSequence[0].SnoutPosition = 421.0  # 42.1 cm
            if not hasattr(ib.IonControlPointSequence[0], "MetersetRate"):
                ib.IonControlPointSequence[0].MetersetRate = 100
            else:
                if ib.IonControlPointSequence[0].MetersetRate is None:
                    ib.IonControlPointSequence[0].MetersetRate = 100.0

            ib.ReferencedToleranceTableNumber = 1

            cum = 0.0
            for icp in ib.IonControlPointSequence:  # Loop over energy layers
                if not hasattr(icp, "ReferencedDoseReferenceSequence"):
                    icp.ReferencedDoseReferenceSequence = [pydicom.Dataset()]

                # first CumulativeDoseReferenceCoefficient is always zero, so cumulative
                # after the coefficient has been set.
                icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient = cum / \
                    ib.FinalCumulativeMetersetWeight
                icp.ReferencedDoseReferenceSequence[0].ReferencedDoseReferenceNumber = 1

                # NumberOfScanSpotPositions, not isinstance(..., list): pydicom stores these as
                # MultiValue after a rescale, and MultiValue is not a list subclass.
                cum += sum([icp.ScanSpotMetersetWeights] if icp.NumberOfScanSpotPositions == 1
                           else icp.ScanSpotMetersetWeights)

    def save(self, output_file):
        """
        Save the modified DICOM file.

        This method saves the updated DICOM plan to the specified output file and logs
        important information such as the cumulative weight, patient details, and any spots
        discarded due to falling below the minimum monitor unit (MU) threshold.

        Args:
            output_file (str): The path where the modified DICOM file will be saved.
        """
        if not output_file:
            output_file = DEFAULT_SAVE_FILENAME
        d = self.dicom
        do = self.old_dicom
        logger.info(HLINE)
        logger.info("Double checking the total cumulative weight:")
        logger.info(f"Total Cumulative Weight Before : {do.IonBeamSequence[0].FinalCumulativeMetersetWeight:12.4f}")
        logger.info(f"Total Cumulative Weight After  : {d.IonBeamSequence[0].FinalCumulativeMetersetWeight:12.4f}")

        d.save_as(output_file)
        logger.info(f"Patient name '{d.PatientName}'")
        logger.info(f"Approval status '{d.ApprovalStatus}'")
        logger.info(f"Treatment Machine Name '{d.IonBeamSequence[-1].TreatmentMachineName}'")
        logger.info(HLINE)
        # logger.info(f"Scale Factor : {scale_factor:.4f}")
        logger.info(f"New plan is saved as : '{output_file}'")
        if self.spots_discarded > 0:
            _pstr = f"{self.spots_discarded/self.total_number_of_spots*100:.2f}"
            logger.warning(
                f" *** Discarded {self.spots_discarded} out of {self.total_number_of_spots}"
                + f" spots ({_pstr} %) which were below {MU_MIN:.2f} [MU] ***")

    def inspect(self):
        """
        Inspect and return key attributes of the DICOM file as a string.

        This method provides a detailed inspection of the DICOM plan, including patient details,
        plan metadata, field information, gantry angles, snout positions, and energy layer parameters.
        """
        d = self.dicom

        # Safely access each attribute, checking for existence
        def safe_get(attr, default="N/A"):
            return getattr(d, attr, default)

        # Initialize a list to collect the output lines
        output = []

        output.append(f"Patient name             : '{safe_get('PatientName')}'")
        output.append(f"Approval status          : '{safe_get('ApprovalStatus')}'")
        output.append(f"RT Plan Date             : '{safe_get('RTPlanDate')}'")
        output.append(f"RT Plan Time             : '{safe_get('RTPlanTime')}'")
        output.append(f"Manufacturer             : '{safe_get('Manufacturer')}'")
        output.append(f"Plan Label               : '{safe_get('RTPlanLabel')}'")
        output.append(f"Operator's Name          : '{safe_get('OperatorsName')}'")
        output.append(f"Reviewer Name            : '{safe_get('ReviewerName')}'")
        output.append(f"Plan Intent              : '{safe_get('PlanIntent')}'")

        if hasattr(d, 'FractionGroupSequence'):
            fg = d.FractionGroupSequence[0]
            output.append(f"Number of fields         : {fg.NumberOfBeams}")
            if hasattr(fg.ReferencedBeamSequence[0], 'BeamDose'):
                output.append(f"Beam Dose                : {fg.ReferencedBeamSequence[0].BeamDose:.2f} Gy(RBE)")

        if hasattr(d, 'IonBeamSequence'):
            ib = d.IonBeamSequence[0]
            output.append(f"Treatment Machine Name   : '{ib.TreatmentMachineName}'")
            for i, ib in enumerate(d.IonBeamSequence):
                beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[i].BeamMeterset
                output.append(HLINE)
                output.append(f"    Field #{i+1}")
                output.append(HLINE)
                output.append(f"    Beam Name                : '{ib.BeamName}'")
                output.append(f"    Number of control points : {ib.NumberOfControlPoints}")
                output.append(f"    Number of energy layers  : {ib.NumberOfControlPoints // 2:2}")
                output.append(f"    Beam Meterset            : {beam_meterset:.2f} MU")
                output.append(f"    Final Cumulative Meterset Weight : {ib.FinalCumulativeMetersetWeight:.2f}")

                if hasattr(ib, 'IonControlPointSequence'):
                    icp = ib.IonControlPointSequence[0]

                    def _pos(keyword, scale=1.0, unit="cm", _icp=icp):
                        """Format a control point value that may be absent or empty.

                        RayStation exports carry the table top positions with no value,
                        so formatting them directly raises TypeError. See issue #37.
                        """
                        value = _icp.get(keyword, None)
                        if value is None or value == "":
                            return "  not set"
                        return f"{float(value) * scale:8.2f} {unit}"

                    output.append(f"            Gantry Angle                     : {_pos('GantryAngle', 1.0, 'deg')}")
                    output.append(f"            Snout Position                   : {_pos('SnoutPosition', 0.1)}")
                    output.append(
                        f"            Table Top Vertical Position      : {_pos('TableTopVerticalPosition', 0.1)}")
                    output.append(
                        f"            Table Top Longitudinal Position  : {_pos('TableTopLongitudinalPosition', 0.1)}")
                    output.append(
                        f"            Table Top Lateral Position       : {_pos('TableTopLateralPosition', 0.1)}")

                    icps = ib.IonControlPointSequence
                    layer_count = 0
                    for j, icp in enumerate(icps):

                        if (j + 1) % 2 == 0:
                            continue

                        layer_count += 1
                        delta_weight = icps[j + 1].CumulativeMetersetWeight - icp.CumulativeMetersetWeight
                        layer_mu = delta_weight / ib.FinalCumulativeMetersetWeight * beam_meterset
                        output.append(HLINE)
                        output.append(f"        Energy Layer # {layer_count:02}")
                        output.append(f"            Nominal Beam Energy              : {icp.NominalBeamEnergy:.2f} MeV")
                        output.append(f"            Number of Scan Spot Positions    : {icp.NumberOfScanSpotPositions}")
                        output.append(f"            Cumulative Meterset Weight       : {icp.CumulativeMetersetWeight:.2f}")
                        output.append(f"            Layer MU                         : {layer_mu:.2f} MU")

        output.append(HLINE)
        # Return the concatenated output as a string
        return "\n".join(output)

    def inspect_all(self):
        """ Print all attributes of the DICOM file to the console. """

        logger.debug("Inspecting all DICOM attributes:")
        print(self.dicom)

    def print_dicom_spot_comparison(self, num_values):
        """
        Compare spot meterset weights between the original and modified DICOM plans.

        This method selects a specified number of random spot meterset weights for each energy layer
        and prints a comparison between the original and modified weights for manual checking.

        Args:
            num_values (int): The number of randomly chosen spot weights to compare.
        """
        logger.info("    ---- Spot weights comparison ----")
        for i, ib in enumerate(self.dicom.IonBeamSequence):
            for j, icp in enumerate(ib.IonControlPointSequence):

                if (j+1) % 2 == 0:  # skip odd layers, as they are repititions of first layers, but with no spot weights
                    continue

                logger.info(HLINE)
                logger.info("    Meterset Weights Comparison ")
                logger.info(f"    - Field #{i+1} Layer #{(j+1)//2} ")
                logger.info(HLINE)

                if icp.NumberOfScanSpotPositions == 1:
                    original_spot_weights = [icp.ScanSpotMetersetWeights]
                else:
                    original_spot_weights = icp.ScanSpotMetersetWeights

                if icp.NumberOfScanSpotPositions == 1:
                    new_spot_weights = [icp.ScanSpotMetersetWeights]
                else:
                    new_spot_weights = icp.ScanSpotMetersetWeights

                self.print_spot_values(original_spot_weights, new_spot_weights, num_values)

    def print_spot_values(self, original_weights, modified_weights, num_values):
        """
        Print a comparison of spot weights before and after modification.

        This method prints the selected number of spot weights from the original and modified
        DICOM plans for comparison.

        Args:
            original_weights (list of float): The list of original spot weights.
            modified_weights (list of float): The list of modified spot weights.
            num_values (int): The number of spot weights to print for comparison.
        """
        logger.info("Original | Modified")
        logger.info("---------|---------")

        if len(original_weights) >= num_values:
            sample_indices = random.sample(range(len(original_weights)), num_values)
        else:
            sample_indices = range(len(original_weights))

        sampled_original = [original_weights[i] for i in sample_indices]
        sampled_new = [modified_weights[i] for i in sample_indices]

        for original, modified in zip(sampled_original, sampled_new):
            logger.info(f"{original:8.4f} | {modified:8.4f}")
