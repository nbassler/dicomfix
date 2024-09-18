import logging
import copy
import datetime
import pydicom
import random
# from dicomfix.dicom_comparator import compare_dicoms  # If you plan to use this in the future


logger = logging.getLogger(__name__)

DEFAULT_SAVE_FILENAME = "output.dcm"
MU_MIN = 1.0  # at least this many MU in a single spot
HLINE = 72 * '-'


class DicomUtil:
    def __init__(self, inputfile):
        # Load the DICOM file
        self.dicom = self.load_dicom(inputfile)
        self.filename = inputfile
        self.points_discarded = 0
        self.old_dicom = copy.deepcopy(self.dicom)
        self.spots_discarded = 0  # count of spots discarded due to low MU
        self.total_number_of_spots = 0
        for ib in self.dicom.IonBeamSequence:
            self.total_number_of_spots += sum([icp.NumberOfScanSpotPositions for icp in ib.IonControlPointSequence])
        self.total_number_of_spots = self.total_number_of_spots // 2  # divide by 2, as each spot has two control points

    @staticmethod
    def load_dicom(inputfile):
        """Load the DICOM file."""
        return pydicom.dcmread(inputfile)

    def modify(self, config):
        """Modify the DICOM file based on the configuration provided."""

        if config.approve:
            self.approve_plan()

        if config.date:
            self.set_current_date()

        if config.intent_curative:
            self.set_intent_to_curative()

        if config.rescale_dose or config.rescale_factor or config.rescale_minimize:
            self.rescale_plan(config)

        if config.duplicate_fields:
            self.duplicate_fields(config.duplicate_fields)

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

        if config.fix_raystation:
            self.fix_raystation()

        if config.print_spots:
            self.print_dicom_spot_comparison(config.print_spots)

    def approve_plan(self):
        """Approve the DICOM plan."""
        d = self.dicom
        d.ApprovalStatus = "APPROVED"
        logger.info(f"New approval status {d.ApprovalStatus}")

    def set_current_date(self):
        """Set the current date in the plan."""
        d = self.dicom
        # Logic for setting the current date
        _dt = datetime.datetime.now()
        d.RTPlanDate = _dt.strftime("%Y%m%d")
        d.RTPlanTime = _dt.strftime("%H%M%S.%f")
        logger.info(f"New RT plan date {d.RTPlanDate}")
        logger.info(f"New RT plan time {d.RTPlanTime}")

    def set_intent_to_curative(self):
        """Set plan intent to CURATIVE."""
        d = self.dicom
        d.ApprovalStatus = "APPROVED"
        logger.info(f"New approval status {d.ApprovalStatus}")

    def rescale_plan(self, config):
        """Rescale the DICOM plan based on the provided settings."""
        if config.rescale_minimize:
            self.minimize_plan()
        elif config.rescale_dose:
            self.rescale_dose(config.rescale_dose)
        elif config.rescale_factor:
            self.apply_rescale_factor(config.rescale_factor)

    def minimize_plan(self):
        """Minimize the plan so smallest spot is MU_MIN"""
        d = self.dicom

        mu_lowest = 9.9e9

        for j, ib in enumerate(d.IonBeamSequence):  # loop over fields
            final_original_cumulative_weight = ib.FinalCumulativeMetersetWeight
            beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_original_cumulative_weight

            for i, icp in enumerate(ib.IonControlPointSequence):
                if icp.NumberOfScanSpotPositions == 1:
                    weights = [icp.ScanSpotMetersetWeights]
                else:
                    weights = icp.ScanSpotMetersetWeights

                for k, w in enumerate(weights):
                    if w > 0.0 and ((w * meterset_per_weight) < mu_lowest):
                        mu_lowest = w * meterset_per_weight

        rescale = MU_MIN / mu_lowest
        logger.info(f"lowest spot: {mu_lowest:14.2} [MU]")
        logger.info(f"rescale by factor: {rescale:.4f}")
        self.apply_rescale_factor(rescale)

    def rescale_dose(self, new_dose):
        """Rescale the dose."""
        d = self.dicom
        for j, ib in enumerate(d.IonBeamSequence):
            scale_factor = new_dose / d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose
            logger.info(f"Rescaling dose to {new_dose:.2f} Gy(RBE)")
            self.apply_rescale_factor(scale_factor)

    def apply_rescale_factor(self, rescale_factor=1.0, layer_factors=None):
        """Apply rescale factor to the plan."""
        d = self.dicom

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
                    raise Exception(f"CSV file energy layers {layer_factors_len} must " +
                                    f"match number of energy layers in dicom file {number_of_energy_layers}.")
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

                # Check if this is a real energy layer (non-repeated one)
                # If there are non-zero weights, this is a real energy layer
                if any(w > 0.0 for w in icp.ScanSpotMetersetWeights):
                    # Apply the correct factor for the real energy layer
                    if layer_factors:
                        layer_factor = layer_factors[real_energy_layer_index]
                        logger.debug(f"CSV weight energy layer {real_energy_layer_index} factor: {layer_factor:.4f}")
                    else:
                        layer_factor = 1.0

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
                raise Exception(f"CSV file energy layers {real_energy_layer_index} must " +
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

    def duplicate_fields(self, n):
        """Duplicate fields in the plan n times."""
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
            Set the gantry angles.
            Mutiple gantry angles are provided as a tuple, one for each field.
                """
        d = self.dicom
        number_of_fields = len(d.IonBeamSequence)
        if len(gantry_angles) != number_of_fields:
            logger.error(f"Number of given gantry angles must match number of fields. \
                            {number_of_fields} fields found.")

        for i, ibs in enumerate(d.IonBeamSequence):
            old_ga = ibs.IonControlPointSequence[0].GantryAngle
            ibs.IonControlPointSequence[0].GantryAngle = gantry_angles[i]
            _ga = ibs.IonControlPointSequence[0].GantryAngle
            logger.info(f"Gantry angle field #{i+1} changed from {old_ga:8.2f} to {_ga:8.2f}")

    def set_table_position(self, table_position):
        """Set the table position."""
        d = self.dicom
        if len(table_position) != 3:
            logger.error(f"Table Position expects three values, got {len(table_position)}.")
            exit()
        for ibs in d.IonBeamSequence:
            ibs.IonControlPointSequence[0].TableTopVerticalPosition = table_position[0]
            ibs.IonControlPointSequence[0].TableTopLongitudinalPosition = table_position[1]
            ibs.IonControlPointSequence[0].TableTopLateralPosition = table_position[2]
        logger.info(f"Table vertical position     : {ibs.IonControlPointSequence[0].TableTopVerticalPosition * 0.1:8.2f} cm")
        logger.info("Table longitudinal position : " +
                    f"{ibs.IonControlPointSequence[0].TableTopLongitudinalPosition * 0.1:8.2f} cm")
        logger.info(f"Table lateral position      : {ibs.IonControlPointSequence[0].TableTopLateralPosition * 0.1:8.2f} cm")

    def set_snout_position(self, snout_position):
        """Set snout position."""
        d = self.dicom
        for ibs in d.IonBeamSequence:
            ibs.IonControlPointSequence[0].SnoutPosition = snout_position
        _sp = d.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition
        logger.info(f"Snout position set to {_sp * 0.1: 8.2f}[cm] for all fields.")

    def set_treatment_machine(self, machine_name):
        """Set treatment machine."""
        d = self.dicom
        for ibs in d.IonBeamSequence:
            ibs.TreatmentMachineName = machine_name
        logger.info(f"New Treatment Machine Name  : '{d.IonBeamSequence[-1].TreatmentMachineName}'")

    def set_plan_label(self, plan_label):
        """Set the plan label."""
        d = self.dicom
        self.dicom = plan_label
        logger.info(f"New RT plan label           : '{d.RTPlanLabel}'")

    def set_patient_name(self, patient_name):
        """Set the patient name."""
        d = self.dicom
        self.dicom.PatientName = patient_name
        logger.info(f"New patient name {d.PatientName}")

    def set_reviewer_name(self, reviewer_name):
        """Set the reviewer name."""
        d = self.dicom
        d.ReviwerName = reviewer_name
        logger.info(f"New reviewer name {d.ReviewerName}")

    def set_wizard_tr4(self):
        """Prepare plan for TR4."""
        d = self.dicom
        d.ApprovalStatus = "APPROVED"
        for ibs in d.IonBeamSequence:
            ibs.TreatmentMachineName = "TR4"
            ibs.IonControlPointSequence[0].GantryAngle = 90.0
            ibs.IonControlPointSequence[0].SnoutPosition = 421.0
        logger.info(f"All gantry angles set to \
                        {d.IonBeamSequence[-1].IonControlPointSequence[0].GantryAngle}")
        logger.info(f"All snout positions set to \
                        {d.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition}")

    def fix_raystation(self):
        """
            Apply RayStation specific fixes to the dicom plan.
            - Set Manufacturer to RaySearch Laboratories
            - Set table positions to 0 for all fields
            - Set target prescription dose to 1.1 Gy(RBE) if it is not already set
        """
        d = self.dicom
        _last_icps = None
        for ibs in d.IonBeamSequence:
            for i, icps in enumerate(ibs.IonControlPointSequence):
                # copy energy information to every second control point
                if icps.ControlPointIndex % 2 == 0:
                    icps.NominalBeamEnergy = _last_icps.NominalBeamEnergy
                _last_icps = icps
        d.Manufacturer = "RaySearch Laboratories"

        # set table positions to 0 for all fields
        for ibs in d.IonBeamSequence:
            for icps in ibs.IonControlPointSequence:
                icps.TableTopVerticalPosition = 0
                icps.TableTopLongitudinalPosition = 0
                icps.TableTopLateralPosition = 0
                logger.debug(f"TableTopVerticalPosition {icps.TableTopVerticalPosition}")
                logger.debug(f"TableTopLongitudinalPosition {icps.TableTopLongitudinalPosition}")
                logger.debug(f"TableTopLateralPosition {icps.TableTopLateralPosition}")

        # Set target prescription dose to 1.1 Gy(RBE) if it is not already set or missing
        for i, rds in enumerate(d.ReferencedDoseSequence):
            if not hasattr(rds, 'TargetPrescriptionDose') or rds.TargetPrescriptionDose is None:
                rds.TargetPrescriptionDose = 1.1  # Set a default value if missing
                logger.info(
                    f"Target prescription dose was missing or not set. Default set to {rds.TargetPrescriptionDose} Gy(RBE)")

    def save(self, output_file):
        """Save the modified DICOM file."""
        """Saves the new dicom file."""
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
        """Inspect the DICOM file."""
        d = self.dicom
        logger.info(f"Patient name             : '{d.PatientName}'")
        logger.info(f"Approval status          : '{d.ApprovalStatus}'")
        logger.info(f"RT Plan Date             : '{d.RTPlanDate}'")
        logger.info(f"RT Plan Time             : '{d.RTPlanTime}'")
        logger.info(f"Manufacturer             : '{d.Manufacturer}'")
        logger.info(f"Plan Label               : '{d.RTPlanLabel}'")
        logger.info(f"Operator's Name          : '{d.OperatorsName}'")
        logger.info(f"Reviewer Name            : '{d.ReviewerName}'")
        logger.info(f"Approval Status          : '{d.ApprovalStatus}'")
        logger.info(f"Plan Intent              : '{d.PlanIntent}'")
        # Additional info which is assumed constant across all instances:
        logger.info(f"Number of fields         : {d.FractionGroupSequence[0].NumberOfBeams}")
        logger.info(f"Beam Meterset            : {d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamMeterset:.2f} MU")
        logger.info(
            f"Beam Dose                : {d.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose:.2f} Gy(RBE)")
        logger.info(f"Treatment Machine Name   : '{d.IonBeamSequence[0].TreatmentMachineName}'")
        for i, ib in enumerate(d.IonBeamSequence):
            logger.info(HLINE)
            logger.info(f"    Field #{i+1}")
            logger.info(HLINE)
            logger.info(f"    Beam Name                : '{ib.BeamName}'")
            logger.info(f"    Number of control points : {ib.NumberOfControlPoints}")
            logger.info(f"    Number of energy layers  : {ib.NumberOfControlPoints/2:2}")
            logger.info(f"    Final Cumulative Meterset Weight : {ib.FinalCumulativeMetersetWeight:.2f}")
            icp = ib.IonControlPointSequence[0]
            # the following info is only stored in the first IonControlPoint
            logger.info(f"            Gantry Angle                     : {icp.GantryAngle:8.2f} deg")
            logger.info(f"            Snout Position                   : {icp.SnoutPosition*0.1:8.2f} cm")
            logger.info(f"            Table Top Vertical Position      : {icp.TableTopVerticalPosition*0.1:8.2f} cm")
            logger.info(
                f"            Table Top Longitudinal Position  : {icp.TableTopLongitudinalPosition*0.1:8.2f} cm")
            logger.info(f"            Table Top Lateral Position       : {icp.TableTopLateralPosition*0.1:8.2f} cm")

            layer_count = 0
            for j, icp in enumerate(ib.IonControlPointSequence):

                if (j+1) % 2 == 0:  # skip odd layers, as they are repititions of first layers, but with no spot weights
                    continue

                layer_count += 1
                logger.info(HLINE)
                logger.info(f"        Energy Layer # {layer_count:02}")
                logger.info(f"            Nominal Beam Energy              : {icp.NominalBeamEnergy:.2f} MeV")
                logger.info(f"            Number of Scan Spot Positions    : {icp.NumberOfScanSpotPositions:}")
                logger.info(f"            Cumulative Meterset Weight       : {icp.CumulativeMetersetWeight:.2f}")
        logger.info(HLINE)

        logger.debug(f"Entire DICOM file:\n\n{d}")

    def print_dicom_spot_comparison(self, num_values):
        """Print num_values randomly chosen spot meterset weights, for old and new DICOM objects for manual checking."""

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
        """Print num_values of spot weights, before and after for checking."""
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
