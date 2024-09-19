import logging
import pytest

from pathlib import Path

import dicomfix.main

logger = logging.getLogger(__name__)


input_files = {
    'plan': Path('res', 'Plan5.5.dcm'),
    'scale_factors.dat': Path('res', 'scale_factors.dat')
}

output_file = Path("output.dcm")


def test_call_cmd_no_option():
    """Test calling dicomfix with no options."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([])
    logger.info("Catching SystemExit with code: {:s}".format(str(e.value)))
    assert e.value.code == 1


def test_call_cmd_help():
    """Test calling dicomfix to print help."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main(['-h'])
    logger.info("Catching SystemExit with code: {:s}".format(str(e.value)))
    assert e.value.code == 0


def test_call_cmd_inspect():
    """Test calling pymchelper to inspect an input dicom."""
    fn = str(input_files['plan'])
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([fn, '-i'])
        logger.info("Catching SystemExit with code: {:s}".format(str(e.value)))
        assert e.value.code == 0


def test_tr4wiz():
    fn = str(input_files['plan'])
    dicomfix.main.main([fn, '-tr4',  '-o', str(output_file)])
    expected_file = output_file
    assert expected_file.is_file()
    assert expected_file.stat().st_size > 0
