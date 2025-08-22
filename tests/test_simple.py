import logging
import pytest

import dicomfix.main

logger = logging.getLogger(__name__)


def test_call_cmd_no_option():
    """Test calling dicomfix with no options."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([])
        logger.debug("Catching SystemExit with code: {:s}".format(str(e.value)))
    assert e.value.code == 1


def test_call_cmd_help():
    """Test calling dicomfix to print help."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main(['-h'])
        logger.debug("Catching SystemExit with code: {:s}".format(str(e.value)))
    assert e.value.code == 0


def test_call_cmd_version():
    """Test calling dicomfix to print version."""
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main(['-V'])
        logger.debug("Catching SystemExit with code: {:s}".format(str(e.value)))
    assert e.value.code == 0
