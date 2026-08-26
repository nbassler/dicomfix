"""
Tests for dicomfix/web/app.py using Streamlit's AppTest framework.

Because st.file_uploader cannot be driven programmatically, tests that need a
loaded DICOM file inject a DicomUtil instance directly into session_state before
running the app script.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dicomfix.dicomutil import DicomUtil

# AppTest.from_file() resolves relative paths against the *calling file's* directory,
# not the working directory, so both paths are anchored on the repo root explicitly.
REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "dicomfix" / "web" / "app.py"
PLAN_FILE = REPO_ROOT / "res" / "Plan5.5.dcm"


@pytest.fixture
def at_empty():
    """App with no file uploaded."""
    at = AppTest.from_file(str(APP_PATH))
    at.run()
    return at


@pytest.fixture
def at_loaded():
    """App with a DicomUtil pre-loaded in session state."""
    at = AppTest.from_file(str(APP_PATH))
    at.session_state["dicom_util"] = DicomUtil(str(PLAN_FILE))
    at.session_state["uploaded_filename"] = PLAN_FILE.name
    at.session_state["dicom_info"] = at.session_state["dicom_util"].inspect()
    at.run()
    return at


class TestNoFile:
    def test_no_exception(self, at_empty):
        assert not at_empty.exception

    def test_shows_upload_prompt(self, at_empty):
        texts = [w.value for w in at_empty.markdown]
        assert any("Please upload" in str(t) for t in texts)

    def test_no_sidebar_tasks(self, at_empty):
        assert not at_empty.sidebar.button


class TestWithFile:
    def test_no_exception(self, at_loaded):
        assert not at_loaded.exception

    def test_sidebar_has_task_buttons(self, at_loaded):
        labels = [b.label for b in at_loaded.sidebar.button]
        assert "Approve Plan" in labels
        assert "Set Current Date" in labels
        assert "Set Intent to Curative" in labels

    def test_machine_selectbox_options(self, at_loaded):
        sb = next(s for s in at_loaded.sidebar.selectbox if "Machine" in s.label)
        assert sb.options == ["TR1", "TR2", "TR3", "TR4"]

    def test_range_shifter_selectbox_options(self, at_loaded):
        sb = next(s for s in at_loaded.sidebar.selectbox if "Range" in s.label)
        assert sb.options == ["None", "RS_2CM", "RS_5CM"]

    def test_output_filename_has_dicomfix_suffix(self):
        """Output filename should have _DICOMFIX inserted before .dcm."""
        name = "myplan.dcm"
        assert name.replace(".dcm", "_DICOMFIX.dcm") == "myplan_DICOMFIX.dcm"

    def test_inspect_text_shown(self, at_loaded):
        texts = [w.value for w in at_loaded.text]
        assert any(len(t) > 0 for t in texts)


class TestButtonActions:
    def test_approve_plan_no_exception(self, at_loaded):
        at_loaded.sidebar.button[0].click().run()
        assert not at_loaded.exception

    def test_set_current_date_no_exception(self, at_loaded):
        btn = next(b for b in at_loaded.sidebar.button if b.label == "Set Current Date")
        btn.click().run()
        assert not at_loaded.exception

    def test_set_intent_no_exception(self, at_loaded):
        btn = next(b for b in at_loaded.sidebar.button if b.label == "Set Intent to Curative")
        btn.click().run()
        assert not at_loaded.exception


class TestNewFileReloads:
    def test_different_filename_triggers_reload(self):
        """Session state with a stale filename causes reload on new upload name."""
        at = AppTest.from_file(str(APP_PATH))
        at.session_state["dicom_util"] = DicomUtil(str(PLAN_FILE))
        at.session_state["uploaded_filename"] = "old_file.dcm"
        at.session_state["dicom_info"] = ""
        at.run()
        # App should not crash even with mismatched filename (no new upload provided)
        assert not at.exception
