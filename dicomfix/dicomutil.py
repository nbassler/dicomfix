import logging
import copy
import datetime
import pydicom
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

    def load_dicom(self, inputfile):
        """Load the DICOM file."""
        self.dicom = pydicom.dcmread(inputfile)

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

        if config.raysearch:
            self.fix_raystation()

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
        """Minimize the plan so smallest spot is 1 MU."""
        # Logic for minimizing the plan
        pass

    def rescale_dose(self, new_dose):
        """Rescale the dose."""
        # Logic for rescaling the dose
        pass

    def apply_rescale_factor(self, factor):
        """Apply rescale factor to the plan."""
        # Logic for applying the factor to the dose
        pass

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
            ib.BeamName += f"_#{copy_number + 1:.02}"  # append copy id
            logger.info(f"{ib.BeamName}")
            ib.BeamNumber = i+1
            new_rbs[i].ReferencedBeamNumber = i+1

        logger.info(f"Duplicated {nf} fields {n} times.")

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
        logger.info(f"Table vertical position: {ibs.IonControlPointSequence[0].TableTopVerticalPosition * 0.1:8.2f} [cm]")
        logger.info("Table longitudinal position: " +
                    f"{ibs.IonControlPointSequence[0].TableTopLongitudinalPosition * 0.1:8.2f} [cm]")
        logger.info(f"Table lateral position: {ibs.IonControlPointSequence[0].TableTopLateralPosition * 0.1:8.2f} [cm]")

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
        logger.info(f"New Treatment Machine Name {d.IonBeamSequence[-1].TreatmentMachineName}")

    def set_plan_label(self, plan_label):
        """Set the plan label."""
        d = self.dicom
        self.dicom = plan_label
        logger.info(f"New RT plan label {d.RTPlanLabel}")

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
        logger.info(f"Total Cumulative Weight Before: {do.IonBeamSequence[0].FinalCumulativeMetersetWeight}")
        logger.info(f"Total Cumulative Weight After: {d.IonBeamSequence[0].FinalCumulativeMetersetWeight}")

        d.save_as(output_file)
        logger.info(f"Patient name '{d.PatientName}'")
        logger.info(f"Approval status '{d.ApprovalStatus}'")
        logger.info(f"Treatment Machine Name '{d.IonBeamSequence[-1].TreatmentMachineName}'")
        logger.info(HLINE)
        # logger.info(f"Scale Factor : {scale_factor:.4f}")
        logger.info(f"New plan is saved as : '{output_file}'")
        if self.points_discarded > 0:
            logger.warning(f" *** Discarded {self.points_discarded} spots which were below {MU_MIN:.2f} [MU] ***")
