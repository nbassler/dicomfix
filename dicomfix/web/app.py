import streamlit as st
from dicomfix.dicomutil import DicomUtil
import io


# Create two columns for layout
col1, col2 = st.columns([3, 1])

# Title of the web app
with col1:
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
    st.sidebar.subheader("Tasks")

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

    def set_range_shifter():
        st.session_state.dicom_util.set_range_shifter(st.session_state.range_shifter)
        update_inspect()

    current_machine = st.session_state.dicom_util.dicom.IonBeamSequence[0].TreatmentMachineName
    st.sidebar.selectbox(
        "Select Treatment Machine",
        options=["TR1", "TR2", "TR3", "TR4"],
        index=["TR1", "TR2", "TR3", "TR4"].index(st.session_state.get("treatment_machine", current_machine)),
        key="treatment_machine",
        on_change=set_treatment_machine
    )

    current_range_sifter = st.session_state.dicom_util.dicom.IonBeamSequence[0].RangeShifterID
    # Selectbox for Range Shifter and callback on selection change
    st.sidebar.selectbox(
        "Select Range Shifter",
        options=["None", "RS_2CM", "RS_5CM"],
        index=["None", "RS_2CM", "RS_5CM"].index(st.session_state.get("range_shifter", current_range_sifter)),
        key="range_shifter",
        on_change=set_range_shifter
    )

    # Add a widget for setting table position
    def set_table_position():
        # Convert the table position inputs (in cm) to mm
        vertical = st.session_state.vertical_position * 10.0
        longitudinal = st.session_state.longitudinal_position * 10.0
        lateral = st.session_state.lateral_position * 10.0
        st.session_state.dicom_util.set_table_position((vertical, longitudinal, lateral))
        update_inspect()

    # Table position input fields
    st.sidebar.subheader("Set Table Position")

    ic = st.session_state.dicom_util.dicom.IonBeamSequence[0].IonControlPointSequence[0]
    # Use st.number_input for each coordinate (vertical, longitudinal, and lateral)
    st.sidebar.number_input("Vertical Position [cm]",
                            value=ic.TableTopVerticalPosition * 0.1,
                            step=0.1, key="vertical_position", on_change=set_table_position)
    st.sidebar.number_input("Longitudinal Position [cm]",
                            value=ic.TableTopLongitudinalPosition * 0.1,
                            step=0.1, key="longitudinal_position", on_change=set_table_position)
    st.sidebar.number_input("Lateral Position [cm]", value=ic.TableTopLateralPosition * 0.1,
                            step=0.1, key="lateral_position", on_change=set_table_position)

    # Add a widget for setting a new dose value
    def set_new_dose():
        new_dose = st.session_state.new_dose_value
        st.session_state.dicom_util.rescale_dose(new_dose)
        update_inspect()

    # Add a number input widget for the new dose
    st.sidebar.subheader("Set New Dose")

    # Use st.number_input for the new dose
    dose = st.session_state.dicom_util.dicom.FractionGroupSequence[0].ReferencedBeamSequence[0].BeamDose
    st.sidebar.number_input("New Dose (Gy[RBE])", value=dose, step=0.1, key="new_dose_value",  on_change=set_new_dose)

    # Modify the downloaded filename to include _DICOMFIX
    original_filename = st.session_state.uploaded_filename
    new_filename = original_filename.replace(".dcm", "_DICOMFIX.dcm")

    # Display DICOM inspection results on the left
    with col1:
        # Display DICOM inspection results at the end after all updates
        st.text(st.session_state.dicom_info)

    # Download button for modified DICOM file in the upper-right (col2)
    with col2:
        # Download button for modified DICOM file
        modified_dicom_buffer = io.BytesIO()
        st.session_state.dicom_util.save(modified_dicom_buffer)

        st.download_button(
            label="Download Modified DICOM",
            data=modified_dicom_buffer.getvalue(),
            file_name=new_filename,  # Updated filename
            mime="application/octet-stream"
        )
else:
    st.write("Please upload a DICOM file using the left sidebar.")
