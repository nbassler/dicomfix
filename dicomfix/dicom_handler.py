import random
import copy
import logging
import pydicom
import datetime

logger = logging.getLogger(__name__)

DEFAULT_SAVE_FILENAME = "output.dcm"
MU_MIN = 1.0  # at least this many MU in a single spot
HLINE = 72 * '-'


class DicomFix:
    """ Class for manipulating DICOM plans."""

    def __init__(self, inputfile: str):
        """Initializes the DicomFix class and loads the input DICOM plan."""
        self.points_discarded = 0
        self.dcm = pydicom.dcmread(inputfile)
        self.filename = inputfile

    def save(self, outputfile: str = None):
        """Saves the new dicom file."""
        if not outputfile:
            outputfile = DEFAULT_SAVE_FILENAME
        logger.info(f"Total Cumulative Weight Before: {self.dcm.IonBeamSequence[0].FinalCumulativeMetersetWeight}")
        logger.info(f"Total Cumulative Weight After: {self.dcm_new.IonBeamSequence[0].FinalCumulativeMetersetWeight}")

        new_dicom_data = self.dcm_new
        new_dicom_data.save_as(outputfile)
        logger.info(f"Patient name '{new_dicom_data.PatientName}'")
        logger.info(f"Approval status '{new_dicom_data.ApprovalStatus}'")
        logger.info(f"Treatment Machine Name '{new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}'")
        logger.info(HLINE)
        # logger.info(f"Scale Factor : {scale_factor:.4f}")
        logger.info(f"New plan is saved as : '{outputfile}'")
        if self.points_discarded > 0:
            logger.warning(f" *** Discarded {self.points_discarded} spots which were below {MU_MIN:.2f} [MU] ***")

    def inspect(self):
        """Print contents of input dicom file and exit."""
        print(self.dcm)
        exit(0)

    def export_racehorse(self, of: str = None, layer=-1, field=-1, fmt=0):
        """Export to Varian serivce mode"""
        if not of:
            of = "foobar"
        d = self.dcm_new
        dt = datetime.datetime.now()
        tmstr = dt.strftime("%d-%m-%Y")

        h = "#HEADER\n"
        h += f"NAME, {d.RTPlanLabel}\n"
        h += f"DATE, {tmstr}\n"
        h += "CREATORNAME, DicomFix\n"
        h += "CREATORVERSION, 0.1\n"
        h += "\n"

        v = "#VALUES\n"
        v += "Index;Position x;Position y;Dose\n"  # if RACEHORSE allows for it, rename "Dose" to "MU", units in mm

        for j, ion_beam in enumerate(d.IonBeamSequence):  # loop over fields
            fno = j
            final_cumulative_weight = ion_beam.FinalCumulativeMetersetWeight
            number_of_control_points = ion_beam.NumberOfControlPoints
            number_of_energy_layers = int(number_of_control_points / 2)

            beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_cumulative_weight

            check_total_mu = 0.0

            lno = 0
            for i, icp in enumerate(ion_beam.IonControlPointSequence):

                nominal_beam_energy = icp.NominalBeamEnergy

                # prescan this layer, whether there are any MUs in any spot
                wt_sum = 0.0
                for n, wt in enumerate(icp.ScanSpotMetersetWeights):
                    wt_sum += wt
                logger.debug(f"{lno}  wt_sum {wt_sum:.10}")
                if wt_sum <= 0.0:  #
                    continue  # skip if this layer has no MUs

                # increment layer count and write to .csv file
                lno += 1

                if lno > number_of_energy_layers:
                    logger.error(f"Too many energy layers. Should be {number_of_energy_layers} / 2 but found {lno}.")

                filename = f"{of}_field{fno+1:02d}_layer_{lno:02d}__{nominal_beam_energy:06.2f}MeV.csv"
                c = "* ----- RACEHORSE Spot List -----\n"
                c += f"* Field: {fno+1:02d}"  # no newline
                c += f"  Layer: {lno:02d}\n"  # TODO: nominal energy, but does RACEHORSE allow for it?
                c += "\n"

                with open(filename, "w") as f:
                    f.write(c)
                    f.write(h)
                    f.write(v)
                    for n, wt in enumerate(icp.ScanSpotMetersetWeights):
                        mu = wt * meterset_per_weight
                        x = icp.ScanSpotPositionMap[n*2]
                        y = icp.ScanSpotPositionMap[n*2+1]
                        f.write(f"{n:2d},{x:8.2f},{y:8.2f},{mu:8.2f}\n")  # index, mm, mm, monitor units
                        check_total_mu += mu
        logger.debug(f"export_racehorse: check_total_mu = {check_total_mu:.2f} MU")

    def copy(self, weights=None, approve=None, intent_curative=None, date=None, print_spots=None, gantry_angles=None,
             duplicate_fields=None, rescale_dose=None, rescale_factor=None, table_position=None, snout_position=None,
             treatment_machine=None, plan_label=None, patient_name=None, reviewer_name=None, wizard_tr4=None,
             rescale_minimize=False):
        """Create a new copy of the input dicom, while overriding any of the input options"""

        # Check if neither weights nor rescale_dose/plan_dose are provided
        if weights or rescale_dose or rescale_factor:
            rescale_flag = True
        else:
            rescale_flag = False  # print("Error: No scaling factor is given for rescaling the plan or spots.")

        new_dicom_data = copy.deepcopy(self.dcm)
        self.dcm_new = new_dicom_data

        if gantry_angles:
            number_of_fields = len(new_dicom_data.IonBeamSequence)
            if len(gantry_angles) != number_of_fields:
                logger.error(f"Number of given gantry angles must match number of fields. \
                               {number_of_fields} fields found.")
            for i, ibs in enumerate(new_dicom_data.IonBeamSequence):
                old_ga = ibs.IonControlPointSequence[0].GantryAngle
                ibs.IonControlPointSequence[0].GantryAngle = gantry_angles[i]
                logger.info(f"Gantry angle field #{i+1} changed from {old_ga} to \
                             {ibs.IonControlPointSequence[0].GantryAngle}")

        # rescale must be done BEFORE duplicate of fields, since it uses dicom_data which must be in sync
        # with new_dicom_data in terms of number of fields.

        if rescale_flag:
            self.rescale(rescale_factor, rescale_dose, weights, print_spots, rescale_minimize)

        if duplicate_fields:
            n = duplicate_fields
            fgs = new_dicom_data.FractionGroupSequence[0]
            nf = new_dicom_data.FractionGroupSequence[0].NumberOfBeams
            rbs = copy.deepcopy(fgs.ReferencedBeamSequence)
            ibs = copy.deepcopy(new_dicom_data.IonBeamSequence)

            new_rbs = [copy.deepcopy(item) for item in rbs for _ in range(n)]
            new_ibs = [copy.deepcopy(item) for item in ibs for _ in range(n)]

            new_dicom_data.FractionGroupSequence[0].ReferencedBeamSequence = new_rbs
            new_dicom_data.FractionGroupSequence[0].NumberOfBeams = len(new_rbs)

            new_dicom_data.IonBeamSequence = new_ibs
            for i, ib in enumerate(new_dicom_data.IonBeamSequence):
                copy_number = i % n
                if copy_number != 0:
                    ib.BeamName += f"_copy_{copy_number}"  # append _copy
                logger.info(f"{ib.BeamName}")
                ib.BeamNumber = i+1
                new_rbs[i].ReferencedBeamNumber = i+1

            logger.info(f"Duplicated {nf} fields {n} times.")

        if treatment_machine:
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.TreatmentMachineName = treatment_machine
            logger.info(f"New Treatment Machine Name {new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}")

        if approve:
            new_dicom_data.ApprovalStatus = "APPROVED"
            logger.info(f"New approval status {new_dicom_data.ApprovalStatus}")

        if intent_curative:
            new_dicom_data.PlanIntent = 'CURATIVE'
            logger.info(f"New plan intent {new_dicom_data.PlanIntent}")

        if date:
            _dt = datetime.datetime.now()
            new_dicom_data.RTPlanDate = _dt.strftime("%Y%m%d")
            new_dicom_data.RTPlanTime = _dt.strftime("%H%M%S.%f")
            logger.info(f"New RT plan date {new_dicom_data.RTPlanDate}")
            logger.info(f"New RT plan time {new_dicom_data.RTPlanTime}")

        if plan_label:
            new_dicom_data.RTPlanLabel = plan_label
            logger.info(f"New RT plan label {new_dicom_data.RTPlanLabel}")

        if patient_name:
            new_dicom_data.PatientName = patient_name
            logger.info(f"New patient name {new_dicom_data.PatientName}")

        if reviewer_name:
            new_dicom_data.ReviwerName = reviewer_name

        # TR4 specific settings
        if wizard_tr4:
            new_dicom_data.ApprovalStatus = "APPROVED"
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.TreatmentMachineName = "TR4"
                ibs.IonControlPointSequence[0].GantryAngle = 90.0
                ibs.IonControlPointSequence[0].SnoutPosition = 421.0
            logger.info(f"All gantry angles set to \
                         {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].GantryAngle}")
            logger.info(f"All snout positions set to \
                         {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition}")

        # check and set X,Y,Z of table position
        if table_position:
            if len(table_position) != 3:
                logger.error(f"Table Position expects three values, got {len(table_position)}.")
                exit()
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.IonControlPointSequence[0].TableTopVerticalPosition = table_position[0]
                ibs.IonControlPointSequence[0].TableTopLongitudinalPosition = table_position[1]
                ibs.IonControlPointSequence[0].TableTopLateralPosition = table_position[2]
            logger.info(f"Table vertical position: {ibs.IonControlPointSequence[0].TableTopVerticalPosition * 0.1:8.2f} [cm]")
            logger.info("Table longitudinal position: " +
                        f"{ibs.IonControlPointSequence[0].TableTopLongitudinalPosition * 0.1:8.2f} [cm]")
            logger.info(f"Table lateral position: {ibs.IonControlPointSequence[0].TableTopLateralPosition * 0.1:8.2f} [cm]")

    def print_spot_comparison(self, layer, scale_factor, original_weights, modified_weights, num_values):
        """Print num_values of spot weights, before and after for checking."""

        logger.info(f"\nLayer {layer}  Scale Factor {scale_factor}")
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

    def get_rescale_for_spot_minimization(self):
        """Scan new dicom plan, and return a rescale factor to get lowest spot = MU_MIN."""
        mu_lowest = 9.9e9
        for j, ion_beam in enumerate(self.dcm_new.IonBeamSequence):  # loop over fields
            final_original_cumulative_weight = ion_beam.FinalCumulativeMetersetWeight
            beam_meterset = self.dcm.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_original_cumulative_weight

            for i, icp in enumerate(ion_beam.IonControlPointSequence):
                if icp.NumberOfScanSpotPositions == 1:
                    weights = [icp.ScanSpotMetersetWeights]
                else:
                    weights = icp.ScanSpotMetersetWeights

                for k, w in enumerate(weights):
                    if w > 0.0 and ((w * meterset_per_weight) < mu_lowest):
                        mu_lowest = w * meterset_per_weight

        logger.info(f"lowest spot: {mu_lowest:14.2} [MU]")
        rescale = MU_MIN / mu_lowest
        return rescale

    def rescale(self, rescale_factor=None, rescale_dose=None, weights=None, print_spots=False, minimize_spots=False):
        """Rescales the input dicom plan by a factor or to a given dose value"""
        if rescale_factor:
            scale_factor = float(rescale_factor)
        else:
            scale_factor = 1

        csv_weights = None  # TODO: refactor me
        if weights:
            # csv_weights = read_weights_from_csv(args.weights)
            csv_weights = weights
            csv_weigths_len = len(csv_weights)

        for j, ion_beam in enumerate(self.dcm_new.IonBeamSequence):  # loop over fields
            logger.info(f"Rescaling field {j+1}")

            # not sure if beam dose is always given in dicom?
            original_beam_dose = self.dcm.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose
            if rescale_dose:
                scale_factor = rescale_dose / original_beam_dose

            new_beam_dose = original_beam_dose * scale_factor

            ion_control_point_sequence = ion_beam.IonControlPointSequence

            final_original_cumulative_weight = ion_beam.FinalCumulativeMetersetWeight
            number_of_control_points = ion_beam.NumberOfControlPoints
            number_of_energy_layers = int(number_of_control_points / 2)

            if csv_weights:
                if csv_weigths_len != number_of_energy_layers:
                    raise Exception(f"CSV file energy layers {csv_weigths_len} must " +
                                    f"match number of energy layers in dicom file {number_of_energy_layers}.")

            original_beam_meterset = self.dcm.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            new_beam_meterset = original_beam_meterset * scale_factor
            new_meterset_per_weight = new_beam_meterset / final_original_cumulative_weight

            original_cumulative_weight = 0.0  # per energy layer
            new_cumulative_weight = 0.0  # per energy layer
            points_discarded = 0

            for i, icp in enumerate(ion_beam.IonControlPointSequence):

                logger.debug(f" --------- Processing energy layer {i}")

                icp.CumulativeMetersetWeight = new_cumulative_weight

                weights = icp.ScanSpotMetersetWeights
                if csv_weights:
                    _ie = int(i * 0.5)
                    csv_weight = csv_weights[_ie]
                    logger.debug(f"CSV weight energy layer {_ie} {csv_weight}")
                else:
                    csv_weight = 1.0

                # if a single spot is in an energy layer, it will not be stored into an array by pydicom.
                # Therefore it is casted into an array here, in order not to break the subsequent code.

                if icp.NumberOfScanSpotPositions == 1:
                    weights = [icp.ScanSpotMetersetWeights]

                new_weights = [0.0] * len(weights)

                for k, w in enumerate(weights):
                    value = w * csv_weight
                    if value > 0.0 and value * new_meterset_per_weight < MU_MIN:
                        logger.debug(f"Discarding point with weight {value:.2f} and \
                                        {value*new_meterset_per_weight:.2f} [MU]")
                        points_discarded += 1
                        value = 0.0
                    new_weights[k] = value

                icp.ScanSpotMetersetWeights = new_weights

                original_cumulative_weight += sum(weights)
                new_cumulative_weight += sum(new_weights)  # Calculate the new cumulative weight

                logger.debug(f"Layer {i:02} Cumulative Weight old-new: \
                                {original_cumulative_weight} - {new_cumulative_weight}")

                if print_spots:
                    self.print_spot_comparison(i, scale_factor, weights, new_weights, print_spots)

            # repeat loop to set the CumulativeDoseReferenceCoefficient for each energy layer
            cw = 0
            logger.info("CumulativeDoseReferenceCoefficient   Original        New   ")
            logger.info(HLINE)
            for i, icp in enumerate(ion_control_point_sequence):
                cdrc_origial = icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient
                cdrc_new = cw / new_cumulative_weight
                icp.ReferencedDoseReferenceSequence[0].CumulativeDoseReferenceCoefficient = cdrc_new
                if icp.NumberOfScanSpotPositions == 1:
                    cw += icp.ScanSpotMetersetWeights
                else:
                    cw += sum(icp.ScanSpotMetersetWeights)
                logger.info(f"    Layer {i:02}                {cdrc_origial:14.3f}  {cdrc_new:14.3f}")
            logger.info(HLINE)
            logger.info("\n")

            rescale_to_minimize = 1.0
            if minimize_spots:
                rescale_to_minimize = self.get_rescale_for_spot_minimization()
                logger.info(f"Rescale factor to minimize spots: {rescale_to_minimize}")
                new_beam_meterset *= rescale_to_minimize
                new_beam_dose *= rescale_to_minimize

            # set remaining meta data
            logger.debug(f"IonBeamSequnce[{j}]")
            self.dcm_new.IonBeamSequence[j].FinalCumulativeMetersetWeight = new_cumulative_weight
            self.dcm_new.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset = new_beam_meterset
            self.dcm_new.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamDose = new_beam_dose

            logger.info("                                  Original           New   ")
            logger.info(HLINE)
            logger.info("Final Cumulative Weight   : " +
                        f"{original_cumulative_weight:14.2f}  {new_cumulative_weight:14.2f}  ")
            logger.info("Beam Meterset             : " +
                        f"{original_beam_meterset:14.2f}  {new_beam_meterset:14.2f}  [MU] ")
            logger.info("Beam Dose                 : " +
                        f"{original_beam_dose:14.2f}  {new_beam_dose:14.2f}  [Gy(RBE)]] ")
        # end of j,ion_beam loop over IonBeamSequence
