import os
import qt
import json
import slicer

from AnnotationModel import AnnotationRecord, ScanMetadata, LabelConfig
from ClassLabelTab import ClassLabelTab
from ROITab import ROITab
from SegmentationTab import SegmentationTab
from ConfigurationScreen import ConfigurationScreen


class AnnotationPanelRootWidget(qt.QWidget):
    """
    Root panel widget: scan upload, configuration screen, tab bar, action bar.
    Manages a single AnnotationRecord and coordinates annotation workflow.

    Flow:
      1. Configuration screen shown (define labels)
      2. Scan upload (always visible)
      3. Once both config and scan are ready, annotation tabs become interactive
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._record = AnnotationRecord()
        self._active_volume_node = None
        self._label_config = None  # LabelConfig, set after config is confirmed
        self._setup_ui()
        self._update_readiness()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = qt.QVBoxLayout(self)

        self._build_scan_section(main_layout)
        self._build_stacked_area(main_layout)
        self._build_action_bar(main_layout)

    def _build_scan_section(self, parent_layout):
        self._scan_group = qt.QGroupBox("Scan")
        scan_layout = qt.QVBoxLayout(self._scan_group)

        # No-scan state
        self._no_scan_widget = qt.QWidget()
        no_scan_layout = qt.QVBoxLayout(self._no_scan_widget)
        no_scan_layout.setContentsMargins(0, 0, 0, 0)

        self._no_scan_label = qt.QLabel("No scan loaded. Load a scan to begin annotating.")
        no_scan_layout.addWidget(self._no_scan_label)

        btn_row = qt.QHBoxLayout()
        self._load_file_btn = qt.QPushButton("Load Scan File")
        self._load_file_btn.clicked.connect(self._on_load_scan_file)
        btn_row.addWidget(self._load_file_btn)

        self._load_dicom_btn = qt.QPushButton("Load DICOM Folder")
        self._load_dicom_btn.clicked.connect(self._on_load_dicom)
        btn_row.addWidget(self._load_dicom_btn)
        btn_row.addStretch()
        no_scan_layout.addLayout(btn_row)

        scan_layout.addWidget(self._no_scan_widget)

        # Scan-loaded state
        self._scan_info_widget = qt.QWidget()
        info_layout = qt.QVBoxLayout(self._scan_info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)

        self._scan_name_label = qt.QLabel("")
        self._scan_name_label.setStyleSheet("font-weight: bold; color: green;")
        info_layout.addWidget(self._scan_name_label)

        self._scan_dims_label = qt.QLabel("")
        info_layout.addWidget(self._scan_dims_label)

        change_row = qt.QHBoxLayout()
        self._change_scan_btn = qt.QPushButton("Change Scan")
        self._change_scan_btn.clicked.connect(self._on_change_scan)
        change_row.addWidget(self._change_scan_btn)

        self._unload_scan_btn = qt.QPushButton("Unload Scan")
        self._unload_scan_btn.clicked.connect(self._on_unload_scan)
        change_row.addWidget(self._unload_scan_btn)
        change_row.addStretch()
        info_layout.addLayout(change_row)

        scan_layout.addWidget(self._scan_info_widget)
        self._scan_info_widget.setVisible(False)

        parent_layout.addWidget(self._scan_group)

    def _build_stacked_area(self, parent_layout):
        self._stacked_widget = qt.QStackedWidget()

        # Page 0: Configuration Screen
        self._config_screen = ConfigurationScreen()
        self._config_screen.set_confirm_callback(self._on_config_confirmed)
        self._stacked_widget.addWidget(self._config_screen)

        # Page 1: Annotation Area (header + tabs)
        self._annotation_area = qt.QWidget()
        ann_layout = qt.QVBoxLayout(self._annotation_area)

        # Header with study/series info and Edit Configuration button
        header_frame = qt.QFrame()
        header_frame.setFrameShape(qt.QFrame.StyledPanel)
        header_layout = qt.QHBoxLayout(header_frame)

        self._study_label = qt.QLabel("Study: \u2014")
        self._series_label = qt.QLabel("Series: \u2014")
        header_layout.addWidget(self._study_label)
        header_layout.addWidget(self._series_label)
        header_layout.addStretch()

        self._edit_config_btn = qt.QPushButton("Edit Configuration")
        self._edit_config_btn.setStyleSheet("color: #1976D2;")
        self._edit_config_btn.clicked.connect(self._on_edit_config_clicked)
        header_layout.addWidget(self._edit_config_btn)

        ann_layout.addWidget(header_frame)

        # Tabs
        self._tab_widget = qt.QTabWidget()
        self._class_label_tab = ClassLabelTab()
        self._roi_tab = ROITab()
        self._segmentation_tab = SegmentationTab()

        self._tab_widget.addTab(self._class_label_tab, "Class Labels")
        self._tab_widget.addTab(self._roi_tab, "ROI")
        self._tab_widget.addTab(self._segmentation_tab, "Segmentation")
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        ann_layout.addWidget(self._tab_widget)

        self._stacked_widget.addWidget(self._annotation_area)

        # Start on config screen
        self._stacked_widget.setCurrentIndex(0)
        parent_layout.addWidget(self._stacked_widget)

    def _build_action_bar(self, parent_layout):
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        parent_layout.addWidget(separator)

        btn_layout = qt.QHBoxLayout()

        self._save_draft_btn = qt.QPushButton("Save Draft")
        self._save_draft_btn.clicked.connect(self._on_save_draft)
        btn_layout.addWidget(self._save_draft_btn)

        self._export_btn = qt.QPushButton("Export Annotations")
        self._export_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 6px 16px; border-radius: 3px; }"
        )
        self._export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(self._export_btn)

        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

    # ─── Configuration ───────────────────────────────────────────────────

    def _on_config_confirmed(self, config):
        """Called when user confirms label configuration."""
        if self._label_config is not None:
            self._handle_config_changes(self._label_config, config)

        self._label_config = config
        self._record.label_config = config
        self._push_labels_to_tabs(config)
        self._stacked_widget.setCurrentIndex(1)
        self._update_readiness()

    def _on_edit_config_clicked(self):
        """Return to config screen for editing."""
        result = qt.QMessageBox.warning(
            self, "Edit Configuration",
            "Editing the configuration may invalidate existing annotations "
            "if you remove labels that are already in use.\n\nContinue?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if result != qt.QMessageBox.Yes:
            return
        self._config_screen.load_config(self._label_config)
        self._stacked_widget.setCurrentIndex(0)

    def _push_labels_to_tabs(self, config):
        """Push configured labels to all annotation tabs."""
        self._class_label_tab.set_labels(config.class_labels)
        self._roi_tab.set_labels(config.roi_labels)
        self._segmentation_tab.set_labels(config.segmentation_classes)

    def _handle_config_changes(self, old_config, new_config):
        """Handle label additions, renames, and removals when re-configuring."""
        self._handle_class_label_changes(old_config.class_labels, new_config.class_labels)
        self._handle_roi_label_changes(old_config.roi_labels, new_config.roi_labels)
        self._handle_seg_class_changes(old_config.segmentation_classes, new_config.segmentation_classes)

    def _handle_class_label_changes(self, old_labels, new_labels):
        """Update class_labels in record when config changes."""
        old_map = {lbl.id: lbl.name for lbl in old_labels}
        new_map = {lbl.id: lbl.name for lbl in new_labels}

        updated = []
        warnings = []
        for name in self._record.class_labels:
            old_id = next((lid for lid, lname in old_map.items() if lname == name), None)
            if old_id and old_id in new_map:
                updated.append(new_map[old_id])
            elif old_id and old_id not in new_map:
                warnings.append(name)
            else:
                updated.append(name)

        self._record.class_labels = updated
        if warnings:
            qt.QMessageBox.information(
                self, "Labels Removed",
                "The following class labels were in use and have been removed:\n" +
                ", ".join(warnings)
            )

    def _handle_roi_label_changes(self, old_labels, new_labels):
        """Update ROI annotations when their labels are renamed or removed."""
        old_map = {lbl.id: lbl.name for lbl in old_labels}
        new_map = {lbl.id: lbl.name for lbl in new_labels}

        warnings = []
        for roi in self._record.rois:
            old_id = next((lid for lid, lname in old_map.items() if lname == roi.label), None)
            if old_id and old_id in new_map:
                roi.label = new_map[old_id]
            elif old_id and old_id not in new_map:
                warnings.append(f"ROI '{roi.roi_type}' had label '{roi.label}'")
                roi.label = ""

        if warnings:
            qt.QMessageBox.information(
                self, "ROI Labels Removed",
                "Some ROI labels were removed. Affected ROIs:\n" +
                "\n".join(warnings)
            )

    def _handle_seg_class_changes(self, old_labels, new_labels):
        """Handle segment removals gracefully (segments recreated from config)."""
        pass

    # ─── Readiness ───────────────────────────────────────────────────────

    def _update_readiness(self):
        """Enable annotation tabs only when both config and scan are ready."""
        ready = (self._label_config is not None) and (self._active_volume_node is not None)
        self._tab_widget.setEnabled(ready)
        self._save_draft_btn.setEnabled(ready)
        self._export_btn.setEnabled(ready)

    # ─── Scan Upload ─────────────────────────────────────────────────────

    def _on_load_scan_file(self):
        filepath = qt.QFileDialog.getOpenFileName(
            self, "Load Scan File", "",
            "All Supported (*.nrrd *.nii *.nii.gz *.mha *.mhd);;"
            "NRRD (*.nrrd);;NIfTI (*.nii *.nii.gz);;"
            "MetaImage (*.mha *.mhd);;All Files (*)"
        )
        if not filepath:
            return
        self._load_volume_from_file(filepath)

    def _on_load_dicom(self):
        dicom_folder = qt.QFileDialog.getExistingDirectory(
            self, "Select DICOM Folder"
        )
        if not dicom_folder:
            return
        try:
            from DICOMLib import DICOMUtils
            loaded_ids = DICOMUtils.loadDICOMDirectory(dicom_folder)
            if loaded_ids:
                volume_node = slicer.mrmlScene.GetNodeByID(loaded_ids[0])
                if volume_node:
                    self._on_scan_loaded(volume_node, dicom_folder)
                    return
            qt.QMessageBox.critical(
                self, "DICOM Load Failed",
                "No volumes could be loaded from the selected DICOM folder."
            )
        except Exception as e:
            qt.QMessageBox.critical(
                self, "DICOM Load Failed", f"Error loading DICOM: {e}"
            )

    def _load_volume_from_file(self, filepath):
        try:
            volume_node = slicer.util.loadVolume(filepath)
            if volume_node:
                self._on_scan_loaded(volume_node, filepath)
            else:
                qt.QMessageBox.critical(
                    self, "Load Failed", "Could not load the selected file."
                )
        except Exception as e:
            qt.QMessageBox.critical(
                self, "Load Failed", f"Error loading scan: {e}"
            )

    def _on_scan_loaded(self, volume_node, source_path=""):
        self._active_volume_node = volume_node

        slicer.util.setSliceViewerLayers(background=volume_node)
        slicer.util.resetSliceViews()

        self._record.scan = self._build_scan_metadata(volume_node, source_path)

        self._class_label_tab.set_volume(volume_node)
        self._roi_tab.set_volume(volume_node)
        self._segmentation_tab.set_volume(volume_node)

        self._set_scan_state(loaded=True)
        self._update_readiness()

    def _on_scan_unloaded(self):
        self._class_label_tab.clear_and_unbind()
        self._roi_tab.clear_and_unbind()
        self._segmentation_tab.clear_and_unbind()

        if self._active_volume_node:
            try:
                slicer.mrmlScene.RemoveNode(self._active_volume_node)
            except Exception:
                pass
        self._active_volume_node = None
        self._record.scan = None
        slicer.util.resetSliceViews()
        self._set_scan_state(loaded=False)
        self._update_readiness()

    def _on_change_scan(self):
        if not self._confirm_clear():
            return
        self._on_scan_unloaded()
        self._on_load_scan_file()

    def _on_unload_scan(self):
        if not self._confirm_clear():
            return
        self._on_scan_unloaded()

    def _confirm_clear(self):
        result = qt.QMessageBox.warning(
            self, "Change Scan",
            "Changing the scan will clear ALL annotations "
            "(class labels, ROIs, and segmentation masks). "
            "Make sure you have exported your work.\n\nContinue?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        return result == qt.QMessageBox.Yes

    def _set_scan_state(self, loaded):
        self._no_scan_widget.setVisible(not loaded)
        self._scan_info_widget.setVisible(loaded)

        if loaded and self._active_volume_node:
            name = self._active_volume_node.GetName()
            self._scan_name_label.setText(f"\u2713 Scan loaded: {name}")

            image_data = self._active_volume_node.GetImageData()
            if image_data:
                dims = image_data.GetDimensions()
                spacing = self._active_volume_node.GetSpacing()
                self._scan_dims_label.setText(
                    f"Dimensions: {dims[0]} \u00d7 {dims[1]} \u00d7 {dims[2]}   "
                    f"Spacing: {spacing[0]:.2f} \u00d7 {spacing[1]:.2f} \u00d7 {spacing[2]:.2f}"
                )
            else:
                self._scan_dims_label.setText("")
        else:
            self._scan_name_label.setText("")
            self._scan_dims_label.setText("")

    def _build_scan_metadata(self, volume_node, source_path):
        meta = ScanMetadata()
        meta.volume_node_id = volume_node.GetID()
        meta.filepath = source_path
        meta.filename = os.path.basename(source_path) if source_path else volume_node.GetName()

        ext = os.path.splitext(source_path)[-1].lower() if source_path else ""
        if ext in (".nrrd",):
            meta.file_format = "nrrd"
        elif ext in (".nii", ".gz"):
            meta.file_format = "nifti"
        elif ext in (".mha", ".mhd"):
            meta.file_format = "metaimage"
        elif os.path.isdir(source_path) if source_path else False:
            meta.file_format = "dicom"

        image_data = volume_node.GetImageData()
        if image_data:
            meta.dimensions = list(image_data.GetDimensions())
        meta.spacing = list(volume_node.GetSpacing())
        meta.origin = list(volume_node.GetOrigin())

        try:
            inst_uids = volume_node.GetAttribute("DICOM.instanceUIDs")
            if inst_uids:
                uid = inst_uids.split()[0]
                meta.modality = slicer.dicomDatabase.fieldForInstance(uid, "0008,0060") or ""
                meta.patient_id = slicer.dicomDatabase.fieldForInstance(uid, "0010,0020") or ""
                meta.study_description = slicer.dicomDatabase.fieldForInstance(uid, "0008,1030") or ""
                if meta.modality:
                    meta.file_format = "dicom"
        except Exception:
            pass

        return meta

    # ─── Tab Switching ───────────────────────────────────────────────────

    def _on_tab_changed(self, index):
        """Deactivate tools from other tabs when switching."""
        roi_tab_index = self._tab_widget.indexOf(self._roi_tab)
        seg_tab_index = self._tab_widget.indexOf(self._segmentation_tab)
        if index != roi_tab_index:
            self._roi_tab.cancel_placement()
        if index != seg_tab_index:
            self._segmentation_tab.deactivate_effect()

    # ─── Public API ──────────────────────────────────────────────────────

    def set_study_info(self, study_id, series_id):
        self._record.study_id = study_id
        self._record.series_id = series_id
        self._study_label.setText(f"Study: {study_id}")
        self._series_label.setText(f"Series: {series_id}")

    def get_record(self):
        self._collect_all_data()
        return self._record

    def set_record(self, record):
        self._record = record
        self._roi_tab.set_annotation_record(record)
        self._study_label.setText(f"Study: {record.study_id}")
        self._series_label.setText(f"Series: {record.series_id}")

        if record.class_labels:
            self._class_label_tab.set_selected_labels(record.class_labels)

        if record.rois:
            self._roi_tab.load_rois(record.rois)

        if record.segmentation:
            self._segmentation_tab.load_segmentation(record.segmentation)

    def load_annotation(self, filepath):
        """Load a draft JSON file and populate the panel."""
        with open(filepath, "r") as f:
            data = json.load(f)
        record = AnnotationRecord.from_dict(data)

        # Restore label configuration
        if record.label_config:
            self._label_config = record.label_config
            self._record.label_config = record.label_config
            self._config_screen.load_config(record.label_config)
            self._push_labels_to_tabs(record.label_config)
            self._stacked_widget.setCurrentIndex(1)
        else:
            self._stacked_widget.setCurrentIndex(0)
            qt.QMessageBox.information(
                self, "No Configuration",
                "This draft has no label configuration. "
                "Please define labels before proceeding."
            )

        # Try to auto-load the referenced scan
        if record.scan and record.scan.filepath:
            if os.path.exists(record.scan.filepath):
                result = qt.QMessageBox.question(
                    self, "Load Scan",
                    f"This draft references a scan at:\n{record.scan.filepath}\n\nLoad it?",
                    qt.QMessageBox.Yes | qt.QMessageBox.No,
                )
                if result == qt.QMessageBox.Yes:
                    self._load_volume_from_file(record.scan.filepath)
            else:
                qt.QMessageBox.information(
                    self, "Scan Not Found",
                    f"The original scan was not found at:\n{record.scan.filepath}\n\n"
                    "Please load the scan manually."
                )

        self.set_record(record)
        self._update_readiness()

    def cleanup(self):
        """Clean up observers when the panel is destroyed."""
        self._roi_tab.cleanup()
        self._segmentation_tab.cleanup()

    # ─── Actions ─────────────────────────────────────────────────────────

    def _collect_all_data(self):
        """Collect all tab data into the record."""
        self._record.class_labels = self._class_label_tab.get_selected_labels()
        self._record.rois = self._roi_tab.get_roi_annotations()
        self._record.segmentation = self._segmentation_tab.get_segmentation_data()

    def _on_save_draft(self):
        filepath = qt.QFileDialog.getSaveFileName(
            self, "Save Annotation Draft", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        self._collect_all_data()
        with open(filepath, "w") as f:
            f.write(self._record.to_json())

    def _on_export(self):
        self._collect_all_data()

        has_labels = bool(self._record.class_labels)
        has_rois = bool(self._record.rois)
        has_seg = (
            self._record.segmentation is not None
            and bool(self._record.segmentation.labels)
        )

        if not has_labels and not has_rois and not has_seg:
            qt.QMessageBox.warning(
                self, "Nothing to Export",
                "No annotations to export. Annotate the scan first."
            )
            return

        export_dir = qt.QFileDialog.getExistingDirectory(
            self, "Select Export Folder"
        )
        if not export_dir:
            return

        exported_files = []

        # annotation.json
        annotation_path = os.path.join(export_dir, "annotation.json")
        with open(annotation_path, "w") as f:
            f.write(self._record.to_json())
        exported_files.append("annotation.json")

        # rois.json
        if has_rois:
            rois_path = os.path.join(export_dir, "rois.json")
            rois_data = [roi.to_dict() for roi in self._record.rois]
            with open(rois_path, "w") as f:
                json.dump(rois_data, f, indent=2)
            exported_files.append("rois.json")

        # segmentation.nrrd
        if has_seg:
            seg_path = os.path.join(export_dir, "segmentation.nrrd")
            success = self._segmentation_tab.export_mask_to_file(seg_path, "nrrd")
            if success:
                self._record.segmentation.export_filepath = seg_path
                exported_files.append("segmentation.nrrd")
                with open(annotation_path, "w") as f:
                    f.write(self._record.to_json())

        # scan_metadata.json
        if self._record.scan:
            scan_path = os.path.join(export_dir, "scan_metadata.json")
            with open(scan_path, "w") as f:
                json.dump(self._record.scan.to_dict(), f, indent=2)
            exported_files.append("scan_metadata.json")

        qt.QMessageBox.information(
            self, "Export Complete",
            f"Exported to: {export_dir}\n\nFiles:\n" +
            "\n".join(f"  \u2022 {f}" for f in exported_files)
        )
