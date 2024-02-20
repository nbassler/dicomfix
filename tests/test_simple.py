import logging
import pytest

from pathlib import Path

import dicomfix

logger = logging.getLogger(__name__)


input_files = {
    'Plan5.5Gy.dcm': Path('res', 'Plan5.5.dcm'),
    'scale_factors.dat': Path('res', 'scale_factors.dat')
}

output_file = "output.dcm"


def test_call_cmd_no_option():
    """Test calling pymchelper with no options."""
    with pytest.raises(SystemExit) as e:
        logger.info("Catching: %s", e)
        dicomfix.main([])
        assert e.value == 2
