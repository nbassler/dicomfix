import logging
import pytest

from pathlib import Path

import dicomfix.main

logger = logging.getLogger(__name__)


input_files = {
    'plan': Path('res', 'Plan5.5.dcm'),
    'scale_factors.dat': Path('res', 'scale_factors.dat')
}


def test_call_cmd_inspect():
    """Test calling pymchelper to inspect an input dicom."""
    fn = str(input_files['plan'])
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([fn, '-i'])
        logger.info("Catching SystemExit with code: {:s}".format(str(e.value)))
        assert e.value.code == 0


def test_tr4wiz(tmp_path):
    fn = str(input_files['plan'])
    output_file = tmp_path / "output.dcm"
    dicomfix.main.main([fn, '-tr4',  '-o', str(output_file)])
    expected_file = output_file
    assert expected_file.is_file()
    assert expected_file.stat().st_size > 0


def test_rescale(caplog, tmp_path):
    fn = str(input_files['plan'])
    output_file = tmp_path / "output.dcm"

    caplog.set_level(logging.INFO, logger="dicomfix.dicomutil")

    dicomfix.main.main([fn, '-rf=2.0',  '-o', str(output_file)])

    # Look for a single logged line containing all three tokens
    found = any(
        ("Beam Dose" in rec.getMessage() and "5.50" in rec.getMessage() and "11.00" in rec.getMessage())
        for rec in caplog.records
        if rec.name.startswith("dicomfix.dicomutil") and rec.levelno >= logging.INFO
    )
    assert found, 'No log line contains all of "Beam Dose", "5.50", and "11.00"'

    assert output_file.is_file()
    assert output_file.stat().st_size > 0
