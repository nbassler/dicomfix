import sys
import argparse
import random
import copy
import logging
import pydicom

logger = logging.getLogger(__name__)

DEFAULT_SAVE_FILENAME = "output.dcm"
MU_MIN = 1.0  # at least this many MU in a single spot
HLINE = 72 * '-'


class DicomFix:
    def __init__(self, inputfile: str):
        self.points_discarded = 0
        self.dcm = pydicom.dcmread(inputfile)

    def save(self, outputfile: str = None):
        """Saves the new dicom file"""
        if not outputfile:
            outputfile = DEFAULT_SAVE_FILENAME
        logging.info(f"Total Cumulative Weight Before: {self.dcm.IonBeamSequence[0].FinalCumulativeMetersetWeight}")
        logging.info(f"Total Cumulative Weight After: {self.dcm_new.IonBeamSequence[0].FinalCumulativeMetersetWeight}")

        new_dicom_data = self.dcm_new
        new_dicom_data.save_as(outputfile)
        logging.info(f"Patient name '{new_dicom_data.PatientName}'")
        logging.info(f"Approval status '{new_dicom_data.ApprovalStatus}'")
        logging.info(f"Treatment Machine Name '{new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}'")
        logger.info(HLINE)
        # logger.info(f"Scale Factor : {scale_factor:.4f}")
        logger.info(f"New plan is saved as : '{outputfile}'")
        if self.points_discarded > 0:
            logger.warning(f" *** Discarded {self.points_discarded} spots which were below {MU_MIN:.2f} [MU] ***")

    def inspect(self):
        """Print contents of input dicom file and exit."""
        print(self.dcm)
        exit(0)

    def copy(self, weights=None, approve=None, intent_curative=None, print_spots=None, gantry_angles=None,
             duplicate_fields=None, rescale_dose=None, rescale_factor=None, table_position=None, snout_position=None,
             treatment_machine=None, patient_name=None, reviewer_name=None, wizard_tr4=None):

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
                logging.error(f"Number of given gantry angles must match number of fields. \
                               {number_of_fields} fields found.")
            for i, ibs in enumerate(new_dicom_data.IonBeamSequence):
                old_ga = ibs.IonControlPointSequence[0].GantryAngle
                ibs.IonControlPointSequence[0].GantryAngle = gantry_angles[i]
                logging.info(f"Gantry angle field #{i+1} changed from {old_ga} to \
                             {ibs.IonControlPointSequence[0].GantryAngle}")

        # rescale must be done BEFORE duplicate of fields, since it uses dicom_data which must be in sync
        # with new_dicom_data in terms of number of fields.

        if rescale_flag:
            self.rescale(rescale_factor, rescale_dose, weights, print_spots)

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

            logging.info(f"Duplicated {nf} fields {n} times.")

        if treatment_machine:
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.TreatmentMachineName = treatment_machine
            logging.info(f"New Treatment Machine Name {new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}")

        if approve:
            new_dicom_data.ApprovalStatus = "APPROVED"
            logging.info(f"New approval status {new_dicom_data.ApprovalStatus}")

        if intent_curative:
            new_dicom_data.PlanIntent = 'CURATIVE'
            logging.info(f"New plan intent {new_dicom_data.PlanIntent}")

        if patient_name:
            new_dicom_data.PatientName = patient_name
            logging.info(f"New patient name {new_dicom_data.PatientName}")

        if reviewer_name:
            new_dicom_data.ReviwerName = reviewer_name

        # TR4 specific settings
        if wizard_tr4:
            new_dicom_data.ApprovalStatus = "APPROVED"
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.TreatmentMachineName = "TR4"
                ibs.IonControlPointSequence[0].GantryAngle = 90.0
                ibs.IonControlPointSequence[0].SnoutPosition = 421.0
            logging.info(f"All gantry angles set to \
                         {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].GantryAngle}")
            logging.info(f"All snout positions set to \
                         {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition}")

        # check and set X,Y,Z of table position
        if table_position:
            if len(table_position) != 3:
                logging.error(f"Table Position expects three values, got {len(table_position)}.")
                exit()
            for ibs in new_dicom_data.IonBeamSequence:
                ibs.IonControlPointSequence[0].TableTopVerticalPosition = table_position[0]
                ibs.IonControlPointSequence[0].TableTopLongitudinalPosition = table_position[1]
                ibs.IonControlPointSequence[0].TableTopLateralPosition = table_position[2]
            logging.info(f"Table vertical position: {ibs.IonControlPointSequence[0].TableTopVerticalPosition} [cm]")
            logging.info("Table longitudinal position: " +
                         f"{ibs.IonControlPointSequence[0].TableTopLongitudinalPosition} [cm]")
            logging.info(f"Table lateral position: {ibs.IonControlPointSequence[0].TableTopLateralPosition} [cm]")

    def print_spot_comparison(self, layer, scale_factor, original_weights, modified_weights, num_values):
        """
        Print num_values of spot weights, before and after for checking.
        """
        logging.info(f"\nLayer {layer}  Scale Factor {scale_factor}")
        logging.info("Original | Modified")
        logging.info("---------|---------")

        if len(original_weights) >= num_values:
            sample_indices = random.sample(range(len(original_weights)), num_values)
        else:
            sample_indices = range(len(original_weights))

        sampled_original = [original_weights[i] for i in sample_indices]
        sampled_new = [modified_weights[i] for i in sample_indices]

        for original, modified in zip(sampled_original, sampled_new):
            logging.info(f"{original:8.4f} | {modified:8.4f}")

    def rescale(self, rescale_factor=None, rescale_dose=None, weights=None, print_spots=False):
        """
        """
        if rescale_factor:
            scale_factor = float(rescale_factor)
        else:
            scale_factor = 1

        csv_weights = None
        if weights:
            # csv_weights = read_weights_from_csv(args.weights)
            csv_weights = read_weights(weights)
            csv_weigths_len = len(csv_weights)

        for j, ion_beam in enumerate(self.dcm_new.IonBeamSequence):  # loop over fields
            logging.info(f"Rescaling field {j+1}")

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


def read_weights(self, csv_file_path):
    """Read CSV file with new weights for each energy layer"""
    weights = []
    with open(csv_file_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            weights.append(float(line))
    return weights


def main(args=None):
    """ Option parsing and main routine."""

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description='Modify ECLIPSE DICOM proton therapy treatment plans.')
    parser.add_argument('inputfile', help='input filename', type=str)

    parser.add_argument('-w', '--weights', required=False, help='Path to weights CSV file', default=None)
    parser.add_argument('-o', '--output', required=False, default="output.dcm", help='Path to output DICOM file')

    parser.add_argument('-a', '--approve', action='store_true', default=False, help='Set plan to APPROVED')
    parser.add_argument('-ic', '--intent_curative', action='store_true', default=False,
                        help='Set plan intent to CURATIVE')
    parser.add_argument('-i', '--inspect', action='store_true', default=False, help='Print contents of dicom file exit')
    parser.add_argument('-tr4', '--wizard_tr4', action='store_true', default=False,
                        help='prepare plan for TR4, this sets aproval, gantry, snout and treatment machine')
    parser.add_argument('-p', '--print_spots', type=int, default=None,
                        help='Number of random values to print for comparison')
    parser.add_argument('-g', '--gantry_angles', type=str, default=None, help='List of comma-separated gantry angles')
    parser.add_argument('-d', '--duplicate_fields', type=int, default=None,
                        help='Duplicate all fields in the plan n times')
    parser.add_argument('-rd', '--rescale_dose', type=float, default=None, help='New rescaled dose [Gy(RBE)]')
    parser.add_argument('-rf', '--rescale_factor', type=float, default=None, help='Multiply plan MUs by this factor')
    parser.add_argument('-tp', '--table_position', type=str, default=None,
                        help='New table position vertical,longitudinal,lateral [cm]. ' +
                             'Negative values should be in quotes and leading space.')
    parser.add_argument('-sp', '--snout_position', type=float, default=None, help='Set new snout position')
    parser.add_argument('-tm', '--treatment_machine', type=str, default=None, help='Treatment Machine Name')
    parser.add_argument('-pn', '--patient_name', type=str, default=None, help='Set patient name')
    parser.add_argument('-rn', '--reviewer_name', type=str, default=None, help='Set reviewer name')

    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='give more output. Option is additive, and can be used up to 3 times')

    parsed_args = parser.parse_args(args)

    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    # convert types for a few input arguments
    if parsed_args.gantry_angles:
        gantry_angles = tuple(float(x) for x in parsed_args.gantry_angles.split(","))
    else:
        gantry_angles = None

    if parsed_args.table_position:
        table_position = tuple(float(x) for x in parsed_args.table_position.split(","))
    else:
        table_position = None

    df = DicomFix(parsed_args.inputfile)

    if parsed_args.inspect:
        df.inspect()

    df.copy(parsed_args.weights, parsed_args.approve, parsed_args.intent_curative,
            parsed_args.print_spots, gantry_angles,
            parsed_args.duplicate_fields, parsed_args.rescale_dose, parsed_args.rescale_factor,
            table_position, parsed_args.snout_position,
            parsed_args.treatment_machine, parsed_args.patient_name,
            parsed_args.reviewer_name,
            parsed_args.wizard_tr4)

    df.save()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
