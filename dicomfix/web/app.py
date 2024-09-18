import streamlit as st
from dicomfix.dicomutil import DicomUtil
import io

# Title of the web app
st.title("DicomFix")

# Sidebar for file upload
st.sidebar.title("Upload DICOM File")
uploaded_file = st.sidebar.file_uploader("Choose a DICOM file", type=["dcm"])

# Initialize the session state for DicomUtil object and DICOM inspection text
if "dicom_util" not in st.session_state:
    st.session_state.dicom_util = None
if "dicom_info" not in st.session_state:
    st.session_state.dicom_info = ""
if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = ""

# Function to update the DICOM inspection text in session state


def update_inspect():
    if st.session_state.dicom_util is not None:
        st.session_state.dicom_info = st.session_state.dicom_util.inspect()


# Load the DICOM file into the session state if uploaded
if uploaded_file is not None and st.session_state.dicom_util is None:
    # Load the DICOM file
    st.session_state.uploaded_filename = uploaded_file.name
    with io.BytesIO(uploaded_file.read()) as f:
        with open(st.session_state.uploaded_filename, "wb") as temp_file:
            temp_file.write(f.read())
        st.session_state.dicom_util = DicomUtil(st.session_state.uploaded_filename)
    update_inspect()

# Sidebar options for modifying the DICOM file
if st.session_state.dicom_util:
    st.sidebar.subheader("Modifications")

    if st.sidebar.button("Approve Plan"):
        st.session_state.dicom_util.approve_plan()
        update_inspect()

    if st.sidebar.button("Set Current Date"):
        st.session_state.dicom_util.set_current_date()
        update_inspect()

    if st.sidebar.button("Set Intent to Curative"):
        st.session_state.dicom_util.set_intent_to_curative()
        update_inspect()

    # Selectbox for Treatment Machine and callback on selection change
    def set_treatment_machine():
        st.session_state.dicom_util.set_treatment_machine(st.session_state.treatment_machine)
        update_inspect()

    st.sidebar.selectbox(
        "Select Treatment Machine",
        options=["TR1", "TR2", "TR3", "TR4"],
        index=["TR1", "TR2", "TR3", "TR4"].index(st.session_state.get("treatment_machine", "TR1")),
        key="treatment_machine",
        on_change=set_treatment_machine
    )

    # Modify the downloaded filename to include _DICOMFIX
    original_filename = st.session_state.uploaded_filename
    new_filename = original_filename.replace(".dcm", "_DICOMFIX.dcm")

    # Download button for modified DICOM file
    modified_dicom_buffer = io.BytesIO()
    st.session_state.dicom_util.save(modified_dicom_buffer)

    st.sidebar.download_button(
        label="Download Modified DICOM",
        data=modified_dicom_buffer.getvalue(),
        file_name=new_filename,  # Updated filename
        mime="application/octet-stream"
    )

# Display DICOM inspection results at the end after all updates
if st.session_state.dicom_util:
    st.text_area("DICOM Inspection", value=st.session_state.dicom_info, height=400)
else:
    st.write("Please upload a DICOM file using the left sidebar.")
