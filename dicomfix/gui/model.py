# File: model.py
# Purpose: the GUI's data model. Holds the plan being viewed and the edits queued against it.

import logging

from dicomfix.__version__ import __version__
from dicomfix.dicomutil import DicomUtil

logger = logging.getLogger(__name__)


def short_version():
    """
    Release version without the setuptools-scm local part.

    __version__ looks like "1.1.0.post3+gb257bfe.d20260826" between releases; the part
    after "+" identifies the exact commit and is useful in About, but too noisy for a
    window title.
    """
    return __version__.split("+", 1)[0]

TREATMENT_MACHINES = ["TR1", "TR2", "TR3", "TR4"]
RANGE_SHIFTERS = ["None", "RS2", "RS5"]

# Snout position [cm] with the snout fully retracted.
SNOUT_RETRACTED = 42.1


def describe_unsupported(path):
    """
    Check whether a file is a plan dicomfix can work on.

    Used to guard drag-and-drop, so dropping a CT series or a stray file gives a clear
    message instead of a traceback.

    Args:
        path (str): File to check.

    Returns:
        str or None: Why the file is unusable, or None when it is a usable ion plan.
    """
    import pydicom

    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=False)
    except Exception as exc:
        return f"Not a DICOM file:\n{exc}"

    modality = str(getattr(ds, "Modality", "") or "")
    if modality != "RTPLAN":
        return f"This is a DICOM {modality or 'file of unknown modality'}, not an RTPLAN."
    if "IonBeamSequence" not in ds:
        return ("This RTPLAN has no IonBeamSequence, so it is not an ion plan. "
                "dicomfix works on proton/ion plans.")
    return None


def _value(dataset, keyword, default=0.0):
    """
    Read a numeric DICOM element that may be absent *or present but empty*.

    RayStation exports leave the table top positions present with no value, so a plain
    float(icp.TableTopVerticalPosition) raises TypeError on real plans. See issue #37.
    """
    value = dataset.get(keyword, None)
    return default if value is None or value == "" else float(value)


class Field:
    """Read-only view of one field, in the units the UI displays."""

    def __init__(self, ion_beam):
        icp = ion_beam.IonControlPointSequence[0]
        self.name = getattr(ion_beam, "BeamName", "")
        self.treatment_machine_name = getattr(ion_beam, "TreatmentMachineName", "")

        # True when the plan actually carries a table position. RayStation leaves these
        # empty, and a displayed 0.0 would otherwise look like a deliberate origin.
        self.table_is_set = all(
            icp.get(k, None) not in (None, "")
            for k in ("TableTopVerticalPosition", "TableTopLongitudinalPosition",
                      "TableTopLateralPosition"))

        # DICOM stores these in mm and as DS strings; the UI works in cm and floats.
        self.table_vertical = _value(icp, "TableTopVerticalPosition") * 0.1
        self.table_longitudinal = _value(icp, "TableTopLongitudinalPosition") * 0.1
        self.table_lateral = _value(icp, "TableTopLateralPosition") * 0.1
        self.snout_position = _value(icp, "SnoutPosition") * 0.1
        self.gantry = _value(icp, "GantryAngle")
        # PatientSupportAngle is read-only in dicomfix: shown, never written.
        self.couch = _value(icp, "PatientSupportAngle")


class PlanModel:
    """One loaded plan, as the UI sees it."""

    def __init__(self, filename):
        self.filename = filename
        self.dicom_util = DicomUtil(filename)
        d = self.dicom_util.dicom

        self.fields = [Field(ib) for ib in d.IonBeamSequence]
        self.approved = getattr(d, "ApprovalStatus", "") == "APPROVED"
        self.curative_intent = getattr(d, "PlanIntent", "") == "CURATIVE"
        self.patient_name = str(getattr(d, "PatientName", ""))
        self.plan_label = str(getattr(d, "RTPlanLabel", ""))

    @property
    def treatment_machine(self):
        return self.fields[-1].treatment_machine_name if self.fields else ""

    @property
    def treatment_machine_index(self):
        """Index into TREATMENT_MACHINES, or -1 for a machine we do not list."""
        name = self.treatment_machine
        return TREATMENT_MACHINES.index(name) if name in TREATMENT_MACHINES else -1

    @property
    def table_positions_differ(self):
        """
        True when the fields do not all share one table position.

        DICOM stores the table top position per field, but dicomfix's -tp writes a single
        value to every field. On a plan whose fields genuinely differ, setting the table
        therefore discards the others' positions, so the UI has to say so first.
        """
        positions = {(f.table_vertical, f.table_longitudinal, f.table_lateral)
                     for f in self.fields}
        return len(positions) > 1

    @property
    def prescribed_dose(self):
        """
        The plan's prescribed dose per fraction, in Gy(RBE).

        TargetPrescriptionDose (300A,0026) when the plan carries one, otherwise the sum
        of BeamDose over the fields, which is the same quantity expressed per beam.
        Returns None when neither is available, in which case dose-based rescaling has
        nothing to scale from.
        """
        d = self.dicom_util.dicom
        for dr in d.get("DoseReferenceSequence", []):
            if "TargetPrescriptionDose" in dr:
                return float(dr.TargetPrescriptionDose)

        total = 0.0
        found = False
        for rb in d.FractionGroupSequence[0].ReferencedBeamSequence:
            if "BeamDose" in rb:
                total += float(rb.BeamDose)
                found = True
        return total if found else None

    @property
    def range_shifter_index(self):
        """Index into RANGE_SHIFTERS based on what the first field currently carries."""
        if not self.dicom_util.dicom.IonBeamSequence:
            return 0
        ibs = self.dicom_util.dicom.IonBeamSequence[0]
        seq = getattr(ibs, "RangeShifterSequence", None)
        if not seq:
            return 0  # "None"
        rs_id = str(getattr(seq[0], "RangeShifterID", ""))
        if rs_id == "RS_2CM":
            return 1
        if rs_id == "RS_5CM":
            return 2
        return 0

    def inspect(self):
        """Human-readable summary, reusing the same output the CLI's -i prints."""
        return self.dicom_util.inspect()


class EditSettings:
    """
    Edits queued against the loaded plan, applied only on export.

    Everything defaults to "leave unchanged". The single job of this class is to turn
    those choices into a dicomfix command line: the GUI then runs that through the same
    parse_arguments() -> Config() -> DicomUtil.modify() path the CLI uses, so the two
    cannot drift apart, and the command can be shown to the user for provenance.
    """

    def __init__(self, n_fields=1):
        self.n_fields = n_fields

        self.approve = False
        self.intent_curative = False
        self.date = False
        self.fix_raystation = False
        self.wizard_tr4 = False

        self.treatment_machine = None       # "TR1".."TR4"
        self.gantry_angles = None           # list of float, one per field
        self.table_position = None          # (vertical, longitudinal, lateral) in cm
        self.snout_position = None          # cm
        self.range_shifter = None           # "None", "RS2", "RS5"
        self.rescale_dose = None            # Gy(RBE)
        self.rescale_factor = None
        self.duplicate_fields = None        # int

    def clear(self):
        """Drop every queued edit, keeping the field count."""
        n = self.n_fields
        self.__init__(n)

    def is_empty(self):
        """True when exporting would only copy the plan."""
        return self.to_args("in.dcm", "out.dcm") == ["in.dcm", "-o", "out.dcm"]

    def to_args(self, inputfile, output):
        """
        Build the dicomfix command line for these settings.

        Args:
            inputfile (str): Plan to read.
            output (str): Plan to write.

        Returns:
            list of str: Arguments suitable for dicomfix.config_parser.parse_arguments().
        """
        args = [str(inputfile)]

        # fix_raystation first, mirroring the order modify() applies things in
        if self.fix_raystation:
            args.append("-rs")
        if self.wizard_tr4:
            args.append("-tr4")
        if self.approve:
            args.append("-a")
        if self.date:
            args.append("-dt")
        if self.intent_curative:
            args.append("-ic")

        if self.rescale_dose is not None:
            args.append(f"-rd={_num(self.rescale_dose)}")
        if self.rescale_factor is not None:
            args.append(f"-rf={_num(self.rescale_factor)}")

        if self.gantry_angles is not None:
            args.append("-g=" + ",".join(_num(a) for a in self.gantry_angles))
        if self.table_position is not None:
            # The "-tp=" form matters: a bare "-tp -24.5,..." would be read as an option.
            args.append("-tp=" + ",".join(_num(v) for v in self.table_position))
        if self.snout_position is not None:
            args.append(f"-sp={_num(self.snout_position)}")

        if self.treatment_machine:
            args += ["-tm", self.treatment_machine]
        if self.range_shifter is not None:
            args.append(f"-rh={self.range_shifter}")

        # duplication last, as modify() does it last
        if self.duplicate_fields:
            args.append(f"-d={int(self.duplicate_fields)}")

        args += ["-o", str(output)]
        return args

    def to_command(self, inputfile, output):
        """The same thing as a copy-pasteable command line, for provenance."""
        return "dicomfix " + " ".join(_quote(a) for a in self.to_args(inputfile, output))


def _num(value):
    """Format a number without trailing zeros, so the command line stays readable."""
    return f"{float(value):g}"


def _quote(arg):
    """Quote an argument if a shell would otherwise split or mangle it."""
    return f'"{arg}"' if (" " in arg or "(" in arg or ")" in arg) else arg
