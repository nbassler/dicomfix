import logging

import pytest

import dicomfix.main

logger = logging.getLogger(__name__)


def test_call_cmd_no_option():
    """Test calling dicomfix with no options."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([])
        logger.debug(f"Catching SystemExit with code: {str(e.value):s}")
    assert e.value.code == 1


def test_call_cmd_help():
    """Test calling dicomfix to print help."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main(['-h'])
        logger.debug(f"Catching SystemExit with code: {str(e.value):s}")
    assert e.value.code == 0


def test_call_cmd_version():
    """Test calling dicomfix to print version."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main(['-V'])
        logger.debug(f"Catching SystemExit with code: {str(e.value):s}")
    assert e.value.code == 0
