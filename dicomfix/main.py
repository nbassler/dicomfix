import sys
import argparse
import csv
import random
import copy
import logging
import pydicom

logger = logging.getLogger(__name__)

def read_weights_from_csv(csv_file_path):
    weights = []
    with open(csv_file_path, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            weights.append(float(row[0]))
    return weights

def print_comparison(layer, scale_factor, original_weights, modified_weights, num_values):
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

def rescale(parsed_args, dicom_data, new_dicom_data):

    scale_factors = []
    if parsed_args.weights:
        scale_factors = read_weights_from_csv(parsed_args.weights)

    plan_rescale_ratio = 1.0  # Initialize to 1 so it doesn't affect multiplication if not set

    if parsed_args.plan_dose and parsed_args.rescale_dose:
        plan_rescale_ratio = parsed_args.rescale_dose / parsed_args.plan_dose

    if parsed_args.rescale_factor:
        plan_rescale_ratio = parsed_args.rescale_factor

    for j,ion_beam in enumerate(new_dicom_data.IonBeamSequence):  # loop over fields
        logging.info(f"Rescaling field {j+1}")
        ion_control_point_sequence = ion_beam.IonControlPointSequence

        total_original_cumulative_weight = 0.0
        total_new_cumulative_weight = 0.0

        for i,ion_control_point in enumerate(ion_beam.IonControlPointSequence):  # loop over energy layers

            original_cumulative_weight = ion_control_point.CumulativeMetersetWeight
            total_original_cumulative_weight += original_cumulative_weight  # Add to total original cumulative weight

            # Use scale factor if available, otherwise use 1
            scale_factor = scale_factors[i] if scale_factors else 1

            # if a single spot is in an energy layer, it will not be stored into an array by pydicom.
            # Therefore it is casted into an array here, in order not to break the subsequent code.

            if ion_control_point.NumberOfScanSpotPositions == 1:
                weights = [ion_control_point.ScanSpotMetersetWeights]
            else:
                weights = ion_control_point.ScanSpotMetersetWeights

            logging.info(f"length of weights {len(weights)}")
            # Modify the weights with both scale_factor and plan_rescale_ratio
            # print(f"weights {weights}")
            # print(f'scale_factor {scale_factor}')
            # print(f"plan_rescale_ratio {plan_rescale_ratio}")
            new_weights = [w * scale_factor * plan_rescale_ratio for w in weights]


            for w in weights:
                logging.debug(f'wt: {w}')
            new_cumulative_weight = original_cumulative_weight * scale_factor * plan_rescale_ratio
            #sum(new_weights)  # Calculate the new cumulative weight
            total_new_cumulative_weight += new_cumulative_weight  # Add to total new cumulative weight

            ion_control_point.ScanSpotMetersetWeights = new_weights
            ion_control_point.CumulativeMetersetWeight = new_cumulative_weight

            logging.info(f"Layer {i} Cumulative Weight Before: {original_cumulative_weight}")
            logging.info(f"Layer {i} Cumulative Weight After: {new_cumulative_weight}")

            if parsed_args.print:
                print_comparison(i // 2 + 1, scale_factor, weights, new_weights, parsed_args.print)

            ion_control_point.CumulativeMetersetWeight = total_new_cumulative_weight

        for i,ion_control_point in enumerate(ion_beam.IonControlPointSequence):  # loop over energy layers
            ion_control_point.CumulativeDoseReferenceCoefficient = ion_control_point.CumulativeMetersetWeight / total_new_cumulative_weight

        ion_beam.FinalCumulativeMetersetWeight = total_new_cumulative_weight
        print(len(new_dicom_data.FractionGroupSequence))
        print(len(dicom_data.IonBeamSequence))
        new_dicom_data.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset = (dicom_data.IonBeamSequence[j].FinalCumulativeMetersetWeight/original_cumulative_weight) * total_new_cumulative_weight

def main(args=None):
    """Main function."""

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description='Modify ECLIPSE DICOM proton therapy treatment plans.')
    parser.add_argument('inputfile', help='input filename', type=str)

    parser.add_argument('-w', '--weights', required=False, help='Path to weights CSV file', default=None)
    parser.add_argument('-o', '--output', required=False, default="output.dcm", help='Path to output DICOM file')

    parser.add_argument('-a', '--approve', action='store_true', default=False, help='Set plan to APPROVED')
    parser.add_argument('-ic', '--intent_curative', action='store_true', default=False, help='Set plan intent to CURATIVE')
    parser.add_argument('-i', '--inspect', action='store_true', default=False, help='Print contents of dicom file exit')
    parser.add_argument('-tr4', '--tr4', action='store_true', default=False, help='prepare plan for TR4, this sets aproval, gantry, snout and treatment machine')

    parser.add_argument('-p', '--print', type=int, default=None, help='Number of random values to print for comparison')
    parser.add_argument('-g', '--gantry_angles', type=str, default=None, help='List of comma-separated gantry angles')
    parser.add_argument('-d', '--duplicate_fields', type=int, default=None, help='Duplicate all fields in the plan n times')
    parser.add_argument('-pd', '--plan_dose', type=float, default=None, help='Nominal plan dose [Gy(RBE)]')
    parser.add_argument('-rd', '--rescale_dose', type=float, default=None, help='New rescaled dose [Gy(RBE)]')
    parser.add_argument('-rf', '--rescale_factor', type=float, default=None, help='Multiply plan MUs by this factor')
    parser.add_argument('-tp', '--table_position', type=str, default=None,
                        help='New table position vertical,longitudinal,lateral [cm]. Negative values should be in quotes and leading space.')

    parser.add_argument('-tm', '--treatment_machine', type=str, default=None, help='Treatment Machine Name')
    parser.add_argument('-pn', '--patient_name', type=str, default=None, help='Set patient name')
    parser.add_argument('-rn', '--reviewer_name', type=str, default=None, help='Set reviewer name')

    parser.add_argument('-v', '--verbosity', action='count', default=0, help='give more output. Option is additive, and can be used up to 3 times')

    parsed_args = parser.parse_args(args)

    if parsed_args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif parsed_args.verbosity > 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig()

    # Check if neither weights nor rescale_dose/plan_dose are provided
    if parsed_args.weights or parsed_args.plan_dose or parsed_args.rescale_dose or parsed_args.rescale_factor:
        rescale_flag = True
    else:
        rescale_flag = False  #print("Error: No scaling factor is given for rescaling the plan or spots.")

    if parsed_args.inspect:
        d = pydicom.dcmread(parsed_args.inputfile)
        print(d)
        exit(0)

    dicom_data = pydicom.dcmread(parsed_args.inputfile)
    new_dicom_data = copy.deepcopy(dicom_data)

    # todo: fix for multi field
    ion_beam_sequence = new_dicom_data.IonBeamSequence[0]
    ion_control_point_sequence = new_dicom_data.IonBeamSequence[0].IonControlPointSequence

    if parsed_args.gantry_angles:
        number_of_fields =  len(new_dicom_data.IonBeamSequence)
        gantry_angles = parsed_args.gantry_angles.split(',')
        if len(gantry_angles) != number_of_fields:
            logging.error(f"Number of given gantry angles must match number of fields. {number_of_fields} fields found.")
        for i,ibs in enumerate(new_dicom_data.IonBeamSequence):
            old_ga = ibs.IonControlPointSequence[0].GantryAngle
            ibs.IonControlPointSequence[0].GantryAngle = gantry_angles[i]
            logging.info(f"Gantry angle field #{i+1} changed from {old_ga} to {ibs.IonControlPointSequence[0].GantryAngle}")

    # rescale must be done BEFORE duplicate of fields, since it uses dicom_data which must be in sync with new_dicom_data in terms of number of fields.
    if rescale_flag:
        rescale(parsed_args, dicom_data, new_dicom_data)

    if parsed_args.duplicate_fields:
        n = parsed_args.duplicate_fields
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
            print(ib.BeamName)
            ib.BeamNumber = i+1
            new_rbs[i].ReferencedBeamNumber = i+1

        logging.info(f"Duplicated {nf} fields {n} times.")


    if parsed_args.treatment_machine:
        for ibs in new_dicom_data.IonBeamSequence:
            ibs.TreatmentMachineName = parsed_args.treatment_machine
        logging.info(f"New Treatment Machine Name {new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}")

    if parsed_args.approve:
        new_dicom_data.ApprovalStatus = "APPROVED"
        logging.info(f"New approval status {new_dicom_data.ApprovalStatus}")

    if parsed_args.intent_curative:
        new_dicom_data.PlanIntent = 'CURATIVE'
        logging.info(f"New plan intent {new_dicom_data.PlanIntent}")

    if parsed_args.patient_name:
        new_dicom_data.PatientName = parsed_args.patient_name
        logging.info(f"New patient name {new_dicom_data.PatientName}")

    if parsed_args.reviewer_name:
        new_dicom_data.ReviwerName = parsed_args.reviewer_name

    # TR4 specific settings
    if parsed_args.tr4:
        new_dicom_data.ApprovalStatus = "APPROVED"
        for ibs in new_dicom_data.IonBeamSequence:
            ibs.TreatmentMachineName = "TR4"
            ibs.IonControlPointSequence[0].GantryAngle = 90.0
            ibs.IonControlPointSequence[0].SnoutPosition = 421.0
        logging.info(f"All gantry angles set to  {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].GantryAngle}")
        logging.info(f"All snout positions set to  {new_dicom_data.IonBeamSequence[-1].IonControlPointSequence[0].SnoutPosition}")

    if parsed_args.table_position:
        tp = parsed_args.table_position.split(",")
        if len(tp) != 3:
            logging.error(f"Table Position expects three values, got {len(tp)}.")
            exit()
        for ibs in new_dicom_data.IonBeamSequence:
            ibs.IonControlPointSequence[0].TableTopVerticalPosition = tp[0]
            ibs.IonControlPointSequence[0].TableTopLongitudinalPosition = tp[1]
            ibs.IonControlPointSequence[0].TableTopLateralPosition = tp[2]
        logging.info(f"Table Vertical Position: {ibs.IonControlPointSequence[0].TableTopVerticalPosition} [cm]")
        logging.info(f"Table Longitudinal Position: {ibs.IonControlPointSequence[0].TableTopLongitudinalPosition} [cm]")
        logging.info(f"Table Lateral Position: {ibs.IonControlPointSequence[0].TableTopLateralPosition} [cm]")


    logging.info(f"Total Cumulative Weight Before: {dicom_data.IonBeamSequence[0].FinalCumulativeMetersetWeight}")
    logging.info(f"Total Cumulative Weight After: {new_dicom_data.IonBeamSequence[0].FinalCumulativeMetersetWeight}")

    new_dicom_data.save_as(parsed_args.output)
    logging.info(f"Weight rescaled plan is saved as {parsed_args.output}")
    logging.info(f"Patient name '{new_dicom_data.PatientName}'")
    logging.info(f"Approval status '{new_dicom_data.ApprovalStatus}'")
    logging.info(f"Treatment Machine Name '{new_dicom_data.IonBeamSequence[-1].TreatmentMachineName}'")

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
