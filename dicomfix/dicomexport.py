import datetime
import logging

logger = logging.getLogger(__name__)


class DicomExport:
    @staticmethod
    def export(dicom, output_file: str = None, export_format: str = None, layer=-1, field=-1):
        """
        Main export function that handles different formats.
        """
        if export_format == "racehorse":
            DicomExport.export_racehorse(dicom, output_file, layer, field)
        elif export_format == "spotlist":
            DicomExport.export_spotlist(dicom, output_file, layer, field)
        else:
            raise ValueError(f"Unknown export format: {export_format}")

    @staticmethod
    def export_racehorse(dicom, output_file: str = "export", layer=-1, field=-1):
        """Export to Varian service mode"""

        d = dicom
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
            field_count = j
            final_cumulative_weight = ion_beam.FinalCumulativeMetersetWeight
            number_of_control_points = ion_beam.NumberOfControlPoints
            number_of_energy_layers = int(number_of_control_points / 2)

            beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
            meterset_per_weight = beam_meterset / final_cumulative_weight

            check_total_mu = 0.0

            layer_count = 0
            for i, icp in enumerate(ion_beam.IonControlPointSequence):

                nominal_beam_energy = icp.NominalBeamEnergy

                # prescan this layer, whether there are any MUs in any spot
                wt_sum = 0.0
                for n, wt in enumerate(icp.ScanSpotMetersetWeights):
                    wt_sum += wt
                logger.debug(f"{layer_count}  wt_sum {wt_sum:.10}")
                if wt_sum <= 0.0:  #
                    continue  # skip if this layer has no MUs

                # increment layer count and write to .csv file
                layer_count += 1

                if layer_count > number_of_energy_layers:
                    logger.error(f"Too many energy layers. Should be {number_of_energy_layers} / 2 but found {layer_count}.")

                filename = f"{output_file}_field{field_count+1:02d}_" + \
                    f"layer_{layer_count:02d}__{nominal_beam_energy:06.2f}MeV.csv"
                c = "* ----- RACEHORSE Spot List -----\n"
                c += f"* Field: {field_count+1:02d}"  # no newline
                c += f"  Layer: {layer_count:02d}\n"  # TODO: nominal energy, but does RACEHORSE allow for it?
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

    @staticmethod
    def export_spotlist(dicom, output_file: str = "export", layer=-1, field=-1):
        """Export simple spotlist (Energy [MeV], X [cm], Y [cm], MU)"""

        d = dicom

        filename = f"{output_file}.csv"

        with open(filename, "w") as f:

            for j, ion_beam in enumerate(d.IonBeamSequence):  # loop over fields
                field_count = j
                final_cumulative_weight = ion_beam.FinalCumulativeMetersetWeight
                number_of_control_points = ion_beam.NumberOfControlPoints
                number_of_energy_layers = int(number_of_control_points / 2)

                beam_meterset = d.FractionGroupSequence[0].ReferencedBeamSequence[j].BeamMeterset
                meterset_per_weight = beam_meterset / final_cumulative_weight

                # check_total_mu = 0.0

                layer_count = 0
                for i, icp in enumerate(ion_beam.IonControlPointSequence):

                    nominal_beam_energy = icp.NominalBeamEnergy

                    # prescan this layer, whether there are any MUs in any spot
                    wt_sum = 0.0
                    for n, wt in enumerate(icp.ScanSpotMetersetWeights):
                        wt_sum += wt
                    logger.debug(f"{layer_count}  wt_sum {wt_sum:.10}")
                    if wt_sum <= 0.0:  #
                        continue  # skip if this layer has no MUs

                    # increment layer count and write to .csv file
                    layer_count += 1

                    if layer_count > number_of_energy_layers:
                        logger.error(
                            f"Too many energy layers. Should be {number_of_energy_layers} / 2 but found {layer_count}.")

                    filename = f"{output_file}_field{field_count+1:02d}_" + \
                        f"layer_{layer_count:02d}__{nominal_beam_energy:06.2f}MeV.csv"

                    for n, wt in enumerate(icp.ScanSpotMetersetWeights):
                        mu = wt * meterset_per_weight
                        x = icp.ScanSpotPositionMap[n*2]
                        y = icp.ScanSpotPositionMap[n*2+1]
                        f.write(f"{nominal_beam_energy:8.2f},{x:8.2f},{y:8.2f},{mu:8.2f}\n")  # energy, mm, mm, monitor units
