"""
Tests for dicomfix.gui.model, the Qt-free half of the GUI.

dicomfix.gui.model imports no Qt deliberately: the plan state and the command-line
construction are plain Python, so they are testable without the optional `gui` extra
installed. Keeping these in their own file is what makes that true in practice -- a
module-level importorskip for PyQt6 would skip them too.
"""
import hashlib
from pathlib import Path

import pytest

from dicomfix.config import Config
from dicomfix.config_parser import parse_arguments
from dicomfix.gui.model import EditSettings

PLAN_FILE = Path('res', 'Plan5.5.dcm')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Model only -- no Qt required
# ---------------------------------------------------------------------------

class TestEditSettings:
    def test_no_edits_produces_only_input_and_output(self):
        s = EditSettings()
        assert s.to_args("in.dcm", "out.dcm") == ["in.dcm", "-o", "out.dcm"]
        assert s.is_empty()

    def test_any_edit_is_no_longer_empty(self):
        s = EditSettings()
        s.rescale_factor = 2.0
        assert not s.is_empty()

    @pytest.mark.parametrize("attr,value,expected", [
        ("approve", True, "-a"),
        ("intent_curative", True, "-ic"),
        ("date", True, "-dt"),
        ("fix_raystation", True, "-rs"),
        ("wizard_tr4", True, "-tr4"),
        ("rescale_dose", 10.0, "-rd=10"),
        ("rescale_factor", 2.5, "-rf=2.5"),
        ("snout_position", 42.1, "-sp=42.1"),
        ("range_shifter", "None", "-rh=None"),
        ("range_shifter", "RS2", "-rh=RS2"),
        ("duplicate_fields", 3, "-d=3"),
    ])
    def test_each_setting_maps_to_its_cli_option(self, attr, value, expected):
        s = EditSettings()
        setattr(s, attr, value)
        assert expected in s.to_args("in.dcm", "out.dcm")

    def test_treatment_machine_is_a_separate_argument(self):
        s = EditSettings()
        s.treatment_machine = "TR4"
        args = s.to_args("in.dcm", "out.dcm")
        assert args[args.index("-tm") + 1] == "TR4"

    def test_gantry_angles_are_comma_separated_per_field(self):
        s = EditSettings(n_fields=3)
        s.gantry_angles = [90.0, 180.0, 270.0]
        assert "-g=90,180,270" in s.to_args("in.dcm", "out.dcm")

    def test_negative_table_position_uses_equals_form(self):
        """A bare '-tp -24.5,...' would be parsed as an option, not a value."""
        s = EditSettings()
        s.table_position = (-24.5, 28.65, -19.55)
        args = s.to_args("in.dcm", "out.dcm")
        assert "-tp=-24.5,28.65,-19.55" in args
        # and it must survive the real parser
        config = Config(parse_arguments(args))
        assert config.table_position == pytest.approx((-245.0, 286.5, -195.5))

    def test_generated_args_always_parse(self):
        s = EditSettings(n_fields=1)
        s.approve = True
        s.rescale_factor = 2.0
        s.treatment_machine = "TR4"
        s.gantry_angles = [90.0]
        s.range_shifter = "None"
        s.duplicate_fields = 2
        config = Config(parse_arguments(s.to_args(str(PLAN_FILE), "out.dcm")))
        assert config.rescale_factor == pytest.approx(2.0)
        assert config.treatment_machine == "TR4"
        assert config.gantry_angles == (90.0,)
        assert config.range_shifter == "NONE"
        assert config.duplicate_fields == 2

    def test_duplication_comes_after_rescaling(self):
        """modify() duplicates last; the generated command must not imply otherwise."""
        s = EditSettings()
        s.rescale_factor = 2.0
        s.duplicate_fields = 2
        args = s.to_args("in.dcm", "out.dcm")
        assert args.index("-rf=2") < args.index("-d=2")

    def test_clear_drops_every_edit(self):
        s = EditSettings(n_fields=2)
        s.rescale_factor = 2.0
        s.approve = True
        s.clear()
        assert s.is_empty()
        assert s.n_fields == 2

    def test_unset_table_position_does_not_raise(self, tmp_path):
        """RayStation leaves the table top positions present but empty (issue #37).

        A plain float() on those raises TypeError, which stopped the GUI opening real
        clinical plans at all.
        """
        import pydicom

        from dicomfix.gui.model import PlanModel
        d = pydicom.dcmread(str(PLAN_FILE))
        icp = d.IonBeamSequence[0].IonControlPointSequence[0]
        for kw in ("TableTopVerticalPosition", "TableTopLongitudinalPosition",
                   "TableTopLateralPosition"):
            setattr(icp, kw, None)
        path = tmp_path / "no_table.dcm"
        d.save_as(str(path))

        plan = PlanModel(str(path))
        assert plan.fields[0].table_vertical == pytest.approx(0.0)
        assert plan.fields[0].table_is_set is False
        # and inspect() must survive it too, since the GUI shows that text
        assert "not set" in plan.inspect()

    def test_table_position_is_flagged_as_set_when_present(self):
        from dicomfix.gui.model import PlanModel
        plan = PlanModel(str(PLAN_FILE))
        assert plan.fields[0].table_is_set is True

    def test_prescribed_dose_falls_back_to_beam_dose(self):
        """PLAN_FILE has no TargetPrescriptionDose, so the summed beam dose stands in."""
        from dicomfix.gui.model import PlanModel
        plan = PlanModel(str(PLAN_FILE))
        assert plan.prescribed_dose == pytest.approx(5.5)

    def test_short_version_drops_the_commit_part(self):
        from dicomfix.gui.model import short_version
        assert "+" not in short_version()

    def test_command_is_copy_pasteable(self):
        s = EditSettings()
        s.rescale_factor = 2.0
        cmd = s.to_command("my plan.dcm", "out.dcm")
        assert cmd.startswith("dicomfix ")
        assert '"my plan.dcm"' in cmd          # spaces must be quoted
