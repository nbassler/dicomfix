"""
Unit tests for dicomfix.config.Config

Tests cover the static/instance parsing methods without requiring a DICOM file.
"""
import argparse

import pytest

from dicomfix.config import Config
from dicomfix.dicomutil import RANGE_SHIFTER_NONE


def make_namespace(**kwargs):
    """Return a minimal argparse Namespace suitable for Config.__init__."""
    defaults = {
        'inputfile': None,
        'weights': None,
        'output': 'output.dcm',
        'export_racehorse': None,
        'approve': False,
        'date': False,
        'intent_curative': False,
        'inspect': False,
        'inspect_all': False,
        'wizard_tr4': False,
        'fix_raystation': False,
        'print_spots': None,
        'gantry_angles': None,
        'duplicate_fields': None,
        'rescale_dose': None,
        'rescale_factor': None,
        'rescale_minimize': False,
        'table_position': None,
        'tolerance_table': False,
        'snout_position': None,
        'treatment_machine': None,
        'plan_label': None,
        'patient_name': None,
        'reviewer_name': None,
        'verbosity': 0,
        'range_shifter': None,
        'repainting': None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestParseAngles:
    def test_single_angle(self):
        assert Config.parse_angles("90.0") == (90.0,)

    def test_multiple_angles(self):
        assert Config.parse_angles("90.0,45.0,270.0") == (90.0, 45.0, 270.0)

    def test_two_angles(self):
        assert Config.parse_angles("0.0,180.0") == (0.0, 180.0)

    def test_none_returns_none(self):
        assert Config.parse_angles(None) is None

    def test_zero_angle(self):
        assert Config.parse_angles("0") == (0.0,)

    def test_negative_angle(self):
        assert Config.parse_angles("-90.0") == (-90.0,)

    def test_result_is_tuple(self):
        result = Config.parse_angles("90.0,45.0")
        assert isinstance(result, tuple)

    def test_values_are_floats(self):
        result = Config.parse_angles("90,45")
        assert result is not None
        assert all(isinstance(v, float) for v in result)


class TestParsePosition:
    def test_three_positions_converted_to_mm(self):
        result = Config.parse_position("1.5,2.0,-0.5")
        assert result == pytest.approx((15.0, 20.0, -5.0))

    def test_none_returns_none(self):
        assert Config.parse_position(None) is None

    def test_zeros(self):
        assert Config.parse_position("0,0,0") == pytest.approx((0.0, 0.0, 0.0))

    def test_converts_cm_to_mm(self):
        # 10 cm -> 100 mm
        result = Config.parse_position("10,0,0")
        assert result is not None
        assert result[0] == pytest.approx(100.0)

    def test_result_is_tuple(self):
        result = Config.parse_position("1,2,3")
        assert isinstance(result, tuple)

    def test_negative_position(self):
        result = Config.parse_position("-5,0,3")
        assert result == pytest.approx((-50.0, 0.0, 30.0))


class TestParseSnoutPosition:
    def test_converts_cm_to_mm(self):
        # 42.1 cm -> 421.0 mm
        assert Config.parse_snout_position(42.1) == pytest.approx(421.0)

    def test_none_returns_none(self):
        assert Config.parse_snout_position(None) is None

    def test_zero(self):
        # NOTE: 0.0 is falsy in Python, so the method returns None for a 0-cm snout position.
        # This is the current behaviour of the code.
        assert Config.parse_snout_position(0.0) is None

    def test_string_input(self):
        # argparse type=float, but method also handles string
        assert Config.parse_snout_position("30.0") == pytest.approx(300.0)


class TestParseRangeShifter:
    def test_rs2_returns_rs2cm(self):
        config = Config(make_namespace(range_shifter="RS2"))
        assert config.range_shifter == "RS_2CM"

    def test_rs_2cm_alias(self):
        config = Config(make_namespace(range_shifter="RS_2CM"))
        assert config.range_shifter == "RS_2CM"

    def test_rs5_returns_rs5cm(self):
        config = Config(make_namespace(range_shifter="RS5"))
        assert config.range_shifter == "RS_5CM"

    def test_rs_5cm_alias(self):
        config = Config(make_namespace(range_shifter="RS_5CM"))
        assert config.range_shifter == "RS_5CM"

    # These two must NOT be equal: an explicit "none" asks for removal, while an
    # absent option asks for nothing at all. Collapsing them was issue #43.
    def test_none_string_returns_sentinel(self):
        config = Config(make_namespace(range_shifter="none"))
        assert config.range_shifter == RANGE_SHIFTER_NONE
        assert config.range_shifter  # must be truthy, or modify() skips it

    def test_none_value_returns_none(self):
        config = Config(make_namespace(range_shifter=None))
        assert config.range_shifter is None

    def test_case_insensitive_rs2(self):
        config = Config(make_namespace(range_shifter="rs2"))
        assert config.range_shifter == "RS_2CM"

    def test_case_insensitive_rs5(self):
        config = Config(make_namespace(range_shifter="rs5"))
        assert config.range_shifter == "RS_5CM"

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            Config(make_namespace(range_shifter="RS3"))

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            Config(make_namespace(range_shifter="FOO"))
