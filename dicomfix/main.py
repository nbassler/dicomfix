import argparse
import csv
import random
import pydicom
import copy

def read_weights_from_csv(csv_file_path):
    weights = []
    with open(csv_file_path, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            weights.append(float(row[0]))
    return weights

def print_comparison(layer, scale_factor, original_weights, modified_weights, num_values):
    print(f"\nLayer {layer}  Scale Factor {scale_factor}")
    print("Original | Modified")
    print("---------|---------")

    if len(original_weights) >= num_values:
        sample_indices = random.sample(range(len(original_weights)), num_values)
    else:
        sample_indices = range(len(original_weights))

    sampled_original = [original_weights[i] for i in sample_indices]
    sampled_new = [modified_weights[i] for i in sample_indices]

    for original, modified in zip(sampled_original, sampled_new):
        print(f"{original:8.4f} | {modified:8.4f}")

def rescale():
    parser = argparse.ArgumentParser(description='Modify DICOM file weights.')
    parser.add_argument('-i', '--input', required=True, help='Path to input DICOM file')
    parser.add_argument('-w', '--weights', required=False, help='Path to weights CSV file', default=None)
    parser.add_argument('-o', '--output', required=True, help='Path to output DICOM file')
    parser.add_argument('-p', '--print', type=int, default=None, help='Number of random values to print for comparison')
    parser.add_argument('-pd', '--plan_dose', type=float, default=None, help='Plan dose')
    parser.add_argument('-rd', '--rescale_dose', type=float, default=None, help='Rescaled dose')
    args = parser.parse_args()

    # Check if neither weights nor rescale_dose/plan_dose are provided
    if args.weights is None and (args.plan_dose is None or args.rescale_dose is None):
        print("Error: No scaling factor is given for rescaling the plan or spots.")
        return

    dicom_data = pydicom.dcmread(args.input)
    new_dicom_data = copy.deepcopy(dicom_data)

    scale_factors = []
    if args.weights:
        scale_factors = read_weights_from_csv(args.weights)

    ion_control_point_sequence = new_dicom_data.IonBeamSequence[0].IonControlPointSequence

    plan_rescale_ratio = 1.0  # Initialize to 1 so it doesn't affect multiplication if not set
    if args.plan_dose is not None and args.rescale_dose is not None:
        plan_rescale_ratio = args.rescale_dose / args.plan_dose

    total_original_cumulative_weight = 0.0
    total_new_cumulative_weight = 0.0

    for i in range(0, len(ion_control_point_sequence)):
        weights = ion_control_point_sequence[i].ScanSpotMetersetWeights
        original_cumulative_weight = new_dicom_data.IonBeamSequence[0].IonControlPointSequence[i].CumulativeMetersetWeight
        total_original_cumulative_weight += original_cumulative_weight  # Add to total original cumulative weight

        # Use scale factor if available, otherwise use 1
        scale_factor = scale_factors[i] if scale_factors else 1

        # Modify the weights with both scale_factor and plan_rescale_ratio
        new_weights = [w * scale_factor * plan_rescale_ratio for w in weights]
        print("length of weights", len(weights))
        for w in weights:
            print('wt: ',w)
        new_cumulative_weight = original_cumulative_weight * scale_factor * plan_rescale_ratio
        #sum(new_weights)  # Calculate the new cumulative weight
        total_new_cumulative_weight += new_cumulative_weight  # Add to total new cumulative weight

        new_dicom_data.IonBeamSequence[0].IonControlPointSequence[i].ScanSpotMetersetWeights = new_weights
        new_dicom_data.IonBeamSequence[0].IonControlPointSequence[i].CumulativeMetersetWeight = new_cumulative_weight

        print(f"Layer {i} Cumulative Weight Before: {original_cumulative_weight}")
        print(f"Layer {i} Cumulative Weight After: {new_cumulative_weight}")

        if args.print:
            print_comparison(i // 2 + 1, scale_factor, weights, new_weights, args.print)

    new_dicom_data.IonBeamSequence[0].IonControlPointSequence[-1].CumulativeMetersetWeight = total_new_cumulative_weight
    for i in range(0, len(ion_control_point_sequence)):
        new_dicom_data.IonBeamSequence[0].IonControlPointSequence[i].CumulativeDoseReferenceCoefficie = new_dicom_data.IonBeamSequence[0].IonControlPointSequence[i].CumulativeMetersetWeight/ total_new_cumulative_weight

    new_dicom_data.IonBeamSequence[0].FinalCumulativeMetersetWeight = total_new_cumulative_weight
    new_dicom_data.FractionGroupSequence[0].ReferencedBeamSequence.BeamMeterset = (dicom_data.IonBeamSequence[0].FinalCumulativeMetersetWeight/original_cumulative_weight) *total_new_cumulative_weight
    print(f"Total Cumulative Weight Before: {total_original_cumulative_weight}")
    print(f"Total Cumulative Weight After: {total_new_cumulative_weight}")

    new_dicom_data.save_as(args.output)
    print(f"Weight rescaled plan is saved as {args.output}")

if __name__ == "__main__":
    rescale()
