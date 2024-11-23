class Config:
    """
    Configuration class that holds all the settings and arguments for the dicomfix tool.

    This class parses and stores the settings provided via command-line arguments
    for manipulating and exporting DICOM files, including options for rescaling,
    modifying positions, and exporting formats.
    """

    def __init__(self, parsed_args):
        """
        Initialize the configuration object with parsed command-line arguments.

        Args:
            parsed_args (argparse.Namespace): The parsed command-line arguments.
        """
        self.inputfile = parsed_args.inputfile
        self.weights = parsed_args.weights
        self.output = parsed_args.output
        self.export_racehorse = parsed_args.export_racehorse
        self.approve = parsed_args.approve
        self.date = parsed_args.date
        self.intent_curative = parsed_args.intent_curative
        self.inspect = parsed_args.inspect
        self.inspect_all = parsed_args.inspect_all
        self.wizard_tr4 = parsed_args.wizard_tr4
        self.fix_raystation = parsed_args.fix_raystation
        self.print_spots = parsed_args.print_spots
        self.gantry_angles = self.parse_angles(parsed_args.gantry_angles)
        self.duplicate_fields = parsed_args.duplicate_fields
        self.rescale_dose = parsed_args.rescale_dose
        self.rescale_factor = parsed_args.rescale_factor
        self.rescale_minimize = parsed_args.rescale_minimize
        self.table_position = self.parse_position(parsed_args.table_position)
        self.snout_position = self.parse_snout_position(parsed_args.snout_position)
        self.treatment_machine = parsed_args.treatment_machine
        self.plan_label = parsed_args.plan_label
        self.patient_name = parsed_args.patient_name
        self.reviewer_name = parsed_args.reviewer_name
        self.verbosity = parsed_args.verbosity

    @staticmethod
    def parse_angles(angles):
        """
        Parse a comma-separated list of angles into a tuple of floats.

        Args:
            angles (str): A comma-separated string of angles.

        Returns:
            tuple of float: A tuple of parsed angles, or None if not provided.
        """
        if angles:
            return tuple(float(x) for x in angles.split(","))
        return None

    @staticmethod
    def parse_position(position):
        """
        Parse a comma-separated list of positions into a tuple of floats in millimeters (mm).

        Args:
            position (str): A comma-separated string of positions.

        Returns:
            tuple of float: A tuple of parsed positions converted to mm, or None if not provided.
    """
        if position:
            return tuple(10.0 * float(x) for x in position.split(","))  # convert to mm
        return None

    @staticmethod
    def parse_snout_position(snout_position):
        """
        Parse the snout position and convert it to millimeters (mm).

        Args:
            snout_position (str): The snout position in centimeters.

        Returns:
            float: The parsed snout position in mm, or None if not provided.
        """
        if snout_position:
            return float(snout_position) * 10.0  # convert to mm
        return None
