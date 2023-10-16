class MainController:
    """Controls interactions between the model and view."""
    def __init__(self, view, model):
        self.view = view
        self.model = model
        self.connect_signals()

    def connect_signals(self):
        self.view.open_dicom_callback = self.on_open_dicom
        self.view.selection_changed_callback = self.on_files_selected


    def on_open_dicom(self):
        print("Open DICOM triggered from controller.")
        files = self.view.open_dicom_files()
        self.model.files_loaded = files[0]
        self.view.file_list_model.setStringList(files[0])
        # here open each dicom file and build the self.fields


    def on_files_selected(self, selected, deselected):
        # Get all selected items
        indexes = self.view.ui.listView.selectionModel().selectedIndexes()

        # Extract the text (filename) of each selected item
        selected_files = [self.view.file_list_model.data(index) for index in indexes]

        # Update your model here, for example:
        self.model.files_selected = selected_files
        print(f"Selected files: {selected_files}")






