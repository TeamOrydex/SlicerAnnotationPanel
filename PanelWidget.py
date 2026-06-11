import os
import qt
import json
import slicer

from AnnotationModel import (
    AnnotationRecord,
    ClassLabelAnnotation,
    LabelConfig,
    ScanMetadata,
    SegmentationData,
    derive_export_folder_name,
    resolve_unique_export_subdirectory,
    resolve_import_paths,
    build_record_from_import,
    derive_import_preset_name,
    EXPORT_ANNOTATIONS_FILENAME,
    EXPORT_SEGMENTATION_FILENAME,
)
from LabelColors import normalize_hex_color
from RadiologyTerms import drawing_tool_display_name
from PresetStorage import preset_name_key, save_preset_overwrite
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
        self._active_preset_name = None
        self._setup_ui()
        self._update_readiness()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = qt.QVBoxLayout(self)

        self._build_scan_section(main_layout)
        self._build_stacked_area(main_layout)
        self._build_action_bar(main_layout)

    def _build_scan_section(self, parent_layout):
        self._scan_group = qt.QGroupBox("Image Series")
        scan_layout = qt.QVBoxLayout(self._scan_group)

        # No-scan state
        self._no_scan_widget = qt.QWidget()
        no_scan_layout = qt.QVBoxLayout(self._no_scan_widget)
        no_scan_layout.setContentsMargins(0, 0, 0, 0)

        self._no_scan_label = qt.QLabel("No series loaded. Load an image series to begin annotating.")
        no_scan_layout.addWidget(self._no_scan_label)

        btn_row = qt.QHBoxLayout()
        self._load_file_btn = qt.QPushButton("Load Image File")
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
        self._change_scan_btn = qt.QPushButton("Change Series")
        self._change_scan_btn.clicked.connect(self._on_change_scan)
        change_row.addWidget(self._change_scan_btn)

        self._unload_scan_btn = qt.QPushButton("Unload Series")
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
        self._config_screen.set_preset_changed_callback(self._on_config_preset_changed)
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
        self._roi_tab.set_annotation_record(self._record)
        self._segmentation_tab = SegmentationTab()

        self._tab_widget.addTab(self._class_label_tab, "Classification")
        self._tab_widget.addTab(self._roi_tab, "ROI")
        self._tab_widget.addTab(self._segmentation_tab, "Segmentation")
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        ann_layout.addWidget(self._tab_widget, 1)

        self._stacked_widget.addWidget(self._annotation_area)

        # Start on config screen
        self._stacked_widget.setCurrentIndex(0)
        parent_layout.addWidget(self._stacked_widget, 1)

    def _build_action_bar(self, parent_layout):
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        parent_layout.addWidget(separator)

        btn_layout = qt.QHBoxLayout()
        btn_layout.setContentsMargins(0, 2, 0, 2)
        btn_layout.setSpacing(6)

        self._import_btn = qt.QPushButton("Import Annotations")
        self._import_btn.clicked.connect(self._on_import_annotations)
        btn_layout.addWidget(self._import_btn)

        self._save_draft_btn = qt.QPushButton("Save Draft")
        self._save_draft_btn.setStyleSheet("QPushButton { padding: 4px 10px; }")
        self._save_draft_btn.clicked.connect(self._on_save_draft)
        btn_layout.addWidget(self._save_draft_btn)

        self._export_btn = qt.QPushButton("Export Annotations")
        self._export_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 4px 10px; border-radius: 3px; }"
        )
        self._export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(self._export_btn)

        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

    # ─── Configuration ───────────────────────────────────────────────────

    def _on_config_confirmed(self, config):
        """Called when user confirms label configuration."""
        new_preset = self._config_screen.get_current_preset_name()
        preset_changed = preset_name_key(new_preset) != preset_name_key(self._active_preset_name)

        if self._should_warn_roi_deletion_on_config_confirm(
            self._label_config, config, preset_changed
        ):
            reply = qt.QMessageBox.warning(
                self,
                "Confirm Configuration",
                "You have modified label names, colors, or drawing tools.\n\n"
                "Confirming will delete existing ROI annotations so they stay "
                "consistent with the updated configuration.\n\nContinue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            if reply != qt.QMessageBox.Yes:
                return

        if preset_changed:
            self._clear_all_annotations(notify=False)
            self._push_labels_to_tabs(config, old_config=None)
        else:
            old_config = self._label_config
            if old_config is not None:
                self._collect_all_data()
                self._handle_config_changes(old_config, config)
            self._push_labels_to_tabs(config, old_config)

        self._active_preset_name = new_preset
        self._label_config = config
        self._record.label_config = config
        self._stacked_widget.setCurrentIndex(1)
        self._update_readiness()

    @staticmethod
    def _label_config_modified(old_config, new_config):
        """True when any label name, color, or ROI drawing tool differs."""
        categories = [
            (old_config.class_labels, new_config.class_labels, False),
            (old_config.roi_labels, new_config.roi_labels, True),
            (old_config.segmentation_classes, new_config.segmentation_classes, False),
        ]
        for old_labels, new_labels, include_drawing_tool in categories:
            old_by_id = {lbl.id: lbl for lbl in old_labels}
            new_by_id = {lbl.id: lbl for lbl in new_labels}
            if set(old_by_id) != set(new_by_id):
                return True
            for label_id, old_label in old_by_id.items():
                new_label = new_by_id[label_id]
                if old_label.name != new_label.name:
                    return True
                if normalize_hex_color(old_label.color) != normalize_hex_color(new_label.color):
                    return True
                if include_drawing_tool and (
                    old_label.resolved_drawing_tool() != new_label.resolved_drawing_tool()
                ):
                    return True
        return False

    def _should_warn_roi_deletion_on_config_confirm(
        self, old_config, new_config, preset_changed
    ):
        """Warn before confirm when label edits will remove existing ROI annotations."""
        if old_config is None or not self._record.rois:
            return False
        if preset_changed:
            return True
        return self._label_config_modified(old_config, new_config)

    def _on_config_preset_changed(self, new_name, old_name):
        """Clear annotations when a different preset is loaded on the config screen."""
        if preset_name_key(new_name) == preset_name_key(old_name):
            return
        self._collect_all_data()
        if not self._has_any_annotations():
            return
        self._clear_all_annotations(notify=True)

    def _on_edit_config_clicked(self):
        """Return to config screen for editing."""
        result = qt.QMessageBox.warning(
            self, "Edit Configuration",
            "Editing the configuration may invalidate existing annotations "
            "if you switch to a different preset or remove labels that are already in use.\n\nContinue?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if result != qt.QMessageBox.Yes:
            return
        self._config_screen.load_config(self._label_config)
        self._config_screen.set_current_preset_name(self._active_preset_name)
        self._stacked_widget.setCurrentIndex(0)

    def _push_labels_to_tabs(self, config, old_config=None):
        """Push configured labels to all annotation tabs."""
        self._class_label_tab.set_labels(config.class_labels)
        self._class_label_tab.set_class_label_annotations(self._record.class_labels)

        self._roi_tab.set_labels(config.roi_labels)
        if old_config is not None:
            self._roi_tab.apply_label_config(old_config.roi_labels, config.roi_labels)

        if old_config is not None:
            self._segmentation_tab.update_labels_from_config(
                old_config.segmentation_classes, config.segmentation_classes
            )
        else:
            self._segmentation_tab.set_labels(config.segmentation_classes)

    def _push_labels_to_tabs_for_import(self, config):
        """Push label config to tabs without resetting imported segmentation data."""
        self._class_label_tab.set_labels(config.class_labels, clear_annotations=False)
        self._roi_tab.set_labels(config.roi_labels)
        self._segmentation_tab.set_labels(config.segmentation_classes, create_segments=False)

    def _apply_imported_label_configuration(self, config, preset_name):
        """Persist imported label configuration and activate it across the panel."""
        try:
            save_preset_overwrite(preset_name, config.to_dict())
        except Exception as exc:
            qt.QMessageBox.warning(
                self,
                "Preset Save Failed",
                f"Annotations were imported, but the label preset could not be saved:\n{exc}",
            )
        self._config_screen.apply_imported_config(config, preset_name)
        self._active_preset_name = preset_name
        self._label_config = config
        self._record.label_config = config

    def _handle_config_changes(self, old_config, new_config):
        """Handle label additions, renames, and removals when re-configuring."""
        self._handle_class_label_changes(old_config.class_labels, new_config.class_labels)
        self._handle_roi_label_changes(old_config.roi_labels, new_config.roi_labels)
        self._handle_seg_class_changes(old_config.segmentation_classes, new_config.segmentation_classes)

    def _handle_class_label_changes(self, old_labels, new_labels):
        """Update or delete class label annotations when config changes."""
        old_map = {lbl.id: lbl.name for lbl in old_labels}
        new_map = {lbl.id: lbl.name for lbl in new_labels}
        new_names = {lbl.name for lbl in new_labels}

        updated = []
        deleted = []
        for item in self._record.class_labels:
            name = item.label if isinstance(item, ClassLabelAnnotation) else str(item)
            old_id = next((lid for lid, lname in old_map.items() if lname == name), None)
            if old_id and old_id in new_map:
                if isinstance(item, ClassLabelAnnotation):
                    item.label = new_map[old_id]
                    updated.append(item)
                else:
                    updated.append(ClassLabelAnnotation(label=new_map[old_id]))
            elif old_id and old_id not in new_map:
                deleted.append(name)
            elif name in new_names:
                if isinstance(item, ClassLabelAnnotation):
                    updated.append(item)
                else:
                    updated.append(ClassLabelAnnotation(label=name))

        self._record.class_labels = updated
        if deleted:
            qt.QMessageBox.information(
                self, "Classification Labels Deleted",
                "The following class label annotations were deleted:\n" +
                ", ".join(deleted)
            )

    def _handle_roi_label_changes(self, old_labels, new_labels):
        """Update or delete ROI annotations when their labels are edited or removed."""
        old_by_id = {lbl.id: lbl for lbl in old_labels}
        new_by_id = {lbl.id: lbl for lbl in new_labels}

        kept = []
        deleted = []
        tool_changed = []
        for roi in self._record.rois:
            old_id = roi.category_id if roi.category_id in old_by_id else None
            if not old_id:
                old_id = next(
                    (lid for lid, lbl in old_by_id.items() if lbl.name == roi.label),
                    None,
                )
            if old_id and old_id not in new_by_id:
                deleted.append(f"{roi.roi_type} ({roi.label})")
                continue
            if old_id and old_id in new_by_id:
                old_def = old_by_id[old_id]
                new_def = new_by_id[old_id]
                if new_def.drawing_tool_changed_from(old_def):
                    tool_changed.append(
                        f"{new_def.name}: "
                        f"{drawing_tool_display_name(old_def.resolved_drawing_tool())} "
                        f"→ {drawing_tool_display_name(new_def.resolved_drawing_tool())}"
                    )
                    continue
                roi.label = new_def.name
                roi.color = new_def.color
            kept.append(roi)

        self._record.rois = kept
        messages = []
        if deleted:
            messages.append(
                "ROIs using deleted labels were removed:\n" + "\n".join(deleted)
            )
        if tool_changed:
            messages.append(
                "ROIs were removed because the configured drawing tool changed:\n"
                + "\n".join(tool_changed)
            )
        if messages:
            qt.QMessageBox.information(self, "ROIs Deleted", "\n\n".join(messages))

    def _handle_seg_class_changes(self, old_labels, new_labels):
        """Delete segmentation metadata for removed classes and warn the user."""
        old_by_id = {lbl.id: lbl for lbl in old_labels}
        new_by_id = {lbl.id: lbl for lbl in new_labels}
        removed = set(old_by_id) - set(new_by_id)
        if not removed:
            return

        removed_names = {old_by_id[lid].name for lid in removed}
        deleted = sorted(removed_names)

        if self._record.segmentation:
            self._record.segmentation.labels = [
                lbl for lbl in self._record.segmentation.labels
                if lbl.name not in removed_names
            ]
            for name in removed_names:
                self._record.segmentation.per_label_voxel_counts.pop(name, None)
            self._record.segmentation.total_voxel_count = sum(
                self._record.segmentation.per_label_voxel_counts.values()
            )

        if deleted:
            qt.QMessageBox.information(
                self, "Segmentation Classes Deleted",
                "The following segmentation classes and their painted data were deleted:\n" +
                "\n".join(deleted)
            )

    # ─── Readiness ───────────────────────────────────────────────────────

    def _has_any_annotations(self):
        has_seg = (
            self._record.segmentation is not None
            and (
                bool(self._record.segmentation.labels)
                or bool(self._record.segmentation.export_filepath)
                or bool(self._record.segmentation.per_label_voxel_counts)
                or self._record.segmentation.total_voxel_count > 0
            )
        )
        return bool(self._record.class_labels or self._record.rois or has_seg)

    def _clear_all_annotations(self, notify=False):
        """Remove all classification, ROI, and segmentation annotations. Keeps scan loaded."""
        self._record.class_labels = []
        self._record.rois = []
        self._record.segmentation = None

        self._class_label_tab.set_class_label_annotations([])

        volume = self._active_volume_node
        self._roi_tab.clear_and_unbind()
        self._segmentation_tab.clear_and_unbind()

        if volume:
            self._roi_tab.set_volume(volume)
            self._segmentation_tab.set_volume(volume, create_segments=False)
        if self._label_config:
            self._segmentation_tab.set_labels(
                self._label_config.segmentation_classes,
                create_segments=False,
            )

        if notify:
            qt.QMessageBox.information(
                self,
                "Annotations Cleared",
                "Existing annotations were removed because the label preset changed.",
            )

    def _update_readiness(self):
        """Enable tabs when label config exists; scan is optional after import."""
        config_ready = self._label_config is not None
        has_scan = self._active_volume_node is not None
        has_annotations = self._has_any_annotations()
        self._tab_widget.setEnabled(config_ready)
        self._import_btn.setEnabled(True)
        self._save_draft_btn.setEnabled(config_ready and (has_scan or has_annotations))
        self._export_btn.setEnabled(config_ready and (has_scan or has_annotations))

    # ─── Scan Upload ─────────────────────────────────────────────────────

    def _on_load_scan_file(self):
        filepath = qt.QFileDialog.getOpenFileName(
            self, "Load Image File", "",
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
                self, "Load Failed", f"Error loading image series: {e}"
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
            self, "Change Series",
            "Changing the series will clear ALL annotations "
            "(classification labels, ROIs, and segmentations). "
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
            self._scan_name_label.setText(f"\u2713 Series loaded: {name}")

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
        from SliceInfo import capture_volume_metadata

        file_format = ""
        ext = os.path.splitext(source_path)[-1].lower() if source_path else ""
        if ext in (".nrrd",):
            file_format = "nrrd"
        elif ext in (".nii", ".gz"):
            file_format = "nifti"
        elif ext in (".mha", ".mhd"):
            file_format = "metaimage"
        elif os.path.isdir(source_path) if source_path else False:
            file_format = "dicom"

        captured = capture_volume_metadata(volume_node)
        if captured.get("modality") and not file_format:
            file_format = "dicom"

        meta = ScanMetadata.from_volume_capture(captured, source_path, file_format)
        if not meta.filename and source_path:
            meta.filename = os.path.basename(source_path)
        elif not meta.filename:
            meta.filename = volume_node.GetName()
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

    def set_record(self, record, *, clear_existing=True):
        volume = self._active_volume_node
        if clear_existing:
            self._class_label_tab.set_class_label_annotations([])
            self._roi_tab.clear_and_unbind()
            self._segmentation_tab.clear_and_unbind()
            if volume:
                self._roi_tab.set_volume(volume)
            if self._label_config:
                self._segmentation_tab.set_labels(
                    self._label_config.segmentation_classes,
                    create_segments=False,
                )

        self._record = record
        self._roi_tab.set_annotation_record(record)
        self._study_label.setText(f"Study: {record.study_id}")
        self._series_label.setText(f"Series: {record.series_id}")

        if record.class_labels:
            self._class_label_tab.set_class_label_annotations(record.class_labels)

        if record.rois:
            self._roi_tab.load_rois(record.rois)

        if record.label_config:
            self._segmentation_tab.set_labels(
                record.label_config.segmentation_classes,
                create_segments=False,
            )

        if record.segmentation:
            success = self._segmentation_tab.load_segmentation(record.segmentation)
            if volume:
                self._segmentation_tab.bind_volume_reference(volume)
            if not success:
                error_detail = getattr(
                    self._segmentation_tab, "_last_import_error", ""
                ) or "Unknown error."
                qt.QMessageBox.warning(
                    self,
                    "Segmentation Import Failed",
                    f"Could not load the segmentation volume.\n\n{error_detail}",
                )
            elif record.label_config:
                seg_map = (
                    record.segmentation.label_to_segment_map
                    if record.segmentation
                    else None
                )
                self._segmentation_tab.reconcile_imported_segment_labels(
                    record.label_config.segmentation_classes,
                    label_to_segment_map=seg_map,
                )
        elif record.label_config:
            self._segmentation_tab.reconcile_imported_segment_labels(
                record.label_config.segmentation_classes,
            )

    def import_annotations(self, path):
        """Import annotations from an export folder or annotations.json file."""
        resolution = resolve_import_paths(path)
        if resolution.errors and not resolution.is_importable():
            qt.QMessageBox.critical(
                self,
                "Import Failed",
                "\n".join(resolution.errors),
            )
            return False

        record, build_errors = build_record_from_import(
            resolution,
            fallback_label_config=self._label_config,
        )
        if build_errors or record is None:
            qt.QMessageBox.critical(
                self,
                "Import Failed",
                "\n".join(build_errors or resolution.errors or ["Import failed."]),
            )
            return False

        if self._has_any_annotations():
            result = qt.QMessageBox.question(
                self,
                "Import Annotations",
                "Importing will replace the current annotations in this session.\n\nContinue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            if result != qt.QMessageBox.Yes:
                return False

        preset_name = derive_import_preset_name(record, resolution.directory)
        self._apply_imported_label_configuration(record.label_config, preset_name)
        self._push_labels_to_tabs_for_import(record.label_config)
        self._stacked_widget.setCurrentIndex(1)

        self.set_record(record)

        imported_parts = []
        if record.class_labels:
            imported_parts.append(f"{len(record.class_labels)} classification label(s)")
        if record.rois:
            imported_parts.append(f"{len(record.rois)} ROI(s)")
        if record.segmentation and record.segmentation.export_filepath:
            imported_parts.append("segmentation volume")

        summary = "Imported " + ", ".join(imported_parts) + "." if imported_parts else "Import completed."
        if resolution.warnings:
            qt.QMessageBox.warning(
                self,
                "Import Completed with Warnings",
                summary + "\n\n" + "\n".join(resolution.warnings),
            )
        else:
            qt.QMessageBox.information(self, "Import Complete", summary)

        self._update_readiness()
        return True

    def load_annotation(self, filepath):
        """Load a draft or exported annotation file and populate the panel."""
        return self.import_annotations(filepath)

    def _on_import_annotations(self):
        folder = qt.QFileDialog.getExistingDirectory(
            self, "Select Export Folder", ""
        )
        path = ConfigurationScreen._file_dialog_path(folder)
        if not path:
            file_result = qt.QFileDialog.getOpenFileName(
                self,
                "Select annotations.json",
                "",
                "JSON Files (*.json)",
            )
            path = ConfigurationScreen._file_dialog_path(file_result)
        if not path:
            return
        self.import_annotations(path)

    def cleanup(self):
        """Clean up observers when the panel is destroyed."""
        self._roi_tab.cleanup()
        self._segmentation_tab.cleanup()

    # ─── Actions ─────────────────────────────────────────────────────────

    def _collect_all_data(self):
        """Collect all tab data into the record."""
        self._record.class_labels = self._class_label_tab.get_class_label_annotations()
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
                "No annotations to export. Annotate the series first."
            )
            return

        parent_export_dir = qt.QFileDialog.getExistingDirectory(
            self, "Select Export Folder"
        )
        if not parent_export_dir:
            return

        folder_name = derive_export_folder_name(self._record)
        export_dir = resolve_unique_export_subdirectory(parent_export_dir, folder_name)
        os.makedirs(export_dir, exist_ok=True)

        exported_files = []

        annotation_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
        with open(annotation_path, "w") as f:
            f.write(self._record.to_export_json())
        exported_files.append(EXPORT_ANNOTATIONS_FILENAME)

        if has_seg:
            seg_path = os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME)
            success = self._segmentation_tab.export_mask_to_file(seg_path, "nifti")
            if success:
                exported_files.append(EXPORT_SEGMENTATION_FILENAME)
            else:
                error_detail = getattr(
                    self._segmentation_tab, "_last_export_error", ""
                ) or "Unknown error."
                qt.QMessageBox.warning(
                    self,
                    "Segmentation Export Failed",
                    "Classification and ROI annotations were exported, but the "
                    "segmentation NIfTI volume could not be written.\n\n"
                    f"Details: {error_detail}",
                )

        qt.QMessageBox.information(
            self, "Export Complete",
            f"Exported to: {export_dir}\n\nFiles:\n" +
            "\n".join(f"  \u2022 {f}" for f in exported_files)
        )
