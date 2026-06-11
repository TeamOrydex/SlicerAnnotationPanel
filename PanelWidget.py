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
    label_configs_differ,
    EXPORT_ANNOTATIONS_FILENAME,
    EXPORT_SEGMENTATION_FILENAME,
)
from RadiologyTerms import drawing_tool_display_name
from PresetStorage import preset_name_key, save_preset_overwrite
from SliceInfo import find_preferred_volume_node, install_slice_tracking
from ClassLabelTab import ClassLabelTab
from ROITab import ROITab
from SegmentationTab import SegmentationTab
from ConfigurationScreen import ConfigurationScreen


class AnnotationPanelRootWidget(qt.QWidget):
    """
    Root panel widget: configuration screen and annotation workspace.
    Manages a single AnnotationRecord and coordinates annotation workflow.

    Flow:
      1. Configuration screen shown (define labels)
      2. Annotation workspace with import/export after configuration is confirmed
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._record = AnnotationRecord()
        self._active_volume_node = None
        self._scene_observers = []
        self._label_config = None  # LabelConfig, set after config is confirmed
        self._active_preset_name = None
        self._setup_ui()
        self._install_scene_observers()
        self._sync_detected_volume()
        self._update_readiness()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = qt.QVBoxLayout(self)
        self._build_stacked_area(main_layout)

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
        self._build_action_bar(ann_layout)

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
        self._initialize_annotation_workspace()
        self._update_readiness()

    def _should_warn_roi_deletion_on_config_confirm(
        self, old_config, new_config, preset_changed
    ):
        """Warn before confirm when label edits will remove existing ROI annotations."""
        if old_config is None or not self._record.rois:
            return False
        if preset_changed:
            return True
        return label_configs_differ(old_config, new_config)

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
        elif self._label_config:
            self._segmentation_tab.initialize_without_volume(
                self._label_config.segmentation_classes,
                create_segments=False,
            )
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
        """Enable annotation actions once label configuration is ready."""
        config_ready = self._label_config is not None
        self._tab_widget.setEnabled(config_ready)
        self._export_btn.setEnabled(config_ready)

    def _initialize_annotation_workspace(self):
        """Prepare tabs for standalone annotation; link any detected series."""
        install_slice_tracking()
        self._sync_detected_volume()
        if self._active_volume_node:
            return

        self._class_label_tab.set_volume(None)
        if self._label_config:
            self._segmentation_tab.initialize_without_volume(
                self._label_config.segmentation_classes,
                create_segments=True,
            )

    def _install_scene_observers(self):
        """Detect volumes loaded through standard Slicer workflows."""
        scene = slicer.mrmlScene
        if scene is None:
            return

        self._remove_scene_observers()

        def _on_scene_changed(caller, event):
            qt.QTimer.singleShot(0, self._sync_detected_volume)

        for event_id in (scene.NodeAddedEvent, scene.NodeRemovedEvent):
            tag = scene.AddObserver(event_id, _on_scene_changed)
            self._scene_observers.append((scene, tag))

    def _remove_scene_observers(self):
        for subject, tag in self._scene_observers:
            try:
                subject.RemoveObserver(tag)
            except Exception:
                pass
        self._scene_observers = []

    def _sync_detected_volume(self):
        """Attach to a series loaded through standard Slicer workflows."""
        volume_node = find_preferred_volume_node()
        if volume_node is None:
            if self._active_volume_node is not None:
                self._detach_volume()
            return

        if (
            self._active_volume_node is not None
            and self._active_volume_node.GetID() == volume_node.GetID()
        ):
            self._record.scan = self._build_scan_metadata(volume_node, "")
            return

        self._bind_volume(volume_node, source_path="")

    def _bind_volume(self, volume_node, source_path=""):
        """Link tabs to a detected series and capture optional scan metadata."""
        if volume_node is None:
            return

        self._active_volume_node = volume_node
        self._record.scan = self._build_scan_metadata(volume_node, source_path)
        self._class_label_tab.set_volume(volume_node)
        self._roi_tab.set_volume(volume_node)

        if self._segmentation_tab.has_segmentation_workspace():
            self._segmentation_tab.bind_volume_reference(volume_node)
        elif self._label_config:
            self._segmentation_tab.set_volume(
                volume_node,
                create_segments=True,
            )
        else:
            self._segmentation_tab.set_volume(volume_node, create_segments=False)

        self._update_readiness()

    def _detach_volume(self):
        """Unlink the panel from the active series without clearing annotations."""
        self._active_volume_node = None
        self._record.scan = None
        self._class_label_tab.set_volume(None)
        self._roi_tab.set_volume(None)
        if self._segmentation_tab.has_segmentation_workspace():
            self._segmentation_tab.detach_volume_reference()
        self._update_readiness()

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

    def _prompt_import_configuration_choice(self):
        """Ask whether to replace the active configuration with the imported one."""
        dialog = qt.QMessageBox(self)
        dialog.setWindowTitle("Import Annotations")
        dialog.setText(
            "Imported annotations contain a different annotation configuration.\n\n"
            "Would you like to replace the current configuration and annotations "
            "with the imported configuration and annotations?"
        )
        import_new_btn = dialog.addButton(
            "Import New Configuration",
            qt.QMessageBox.AcceptRole,
        )
        dialog.addButton(
            "Keep Current Configuration",
            qt.QMessageBox.RejectRole,
        )
        dialog.setDefaultButton(import_new_btn)
        dialog.exec_()
        return dialog.clickedButton() == import_new_btn

    def _import_summary_message(self, record):
        imported_parts = []
        if record.class_labels:
            imported_parts.append(f"{len(record.class_labels)} classification label(s)")
        if record.rois:
            imported_parts.append(f"{len(record.rois)} ROI(s)")
        if record.segmentation and record.segmentation.export_filepath:
            imported_parts.append("segmentation volume")
        if imported_parts:
            return "Imported " + ", ".join(imported_parts) + "."
        return "Import completed."

    def _show_import_result(self, record, resolution):
        summary = self._import_summary_message(record)
        if resolution.warnings:
            qt.QMessageBox.warning(
                self,
                "Import Completed with Warnings",
                summary + "\n\n" + "\n".join(resolution.warnings),
            )
        else:
            qt.QMessageBox.information(self, "Import Complete", summary)

    def _apply_import_with_new_configuration(self, record, resolution):
        """Replace configuration and annotations, then return to the config screen."""
        self._clear_all_annotations(notify=False)

        preset_name = derive_import_preset_name(record, resolution.directory)
        self._apply_imported_label_configuration(record.label_config, preset_name)
        self._push_labels_to_tabs_for_import(record.label_config)
        self.set_record(record)
        self._sync_detected_volume()
        self._stacked_widget.setCurrentIndex(0)
        self._show_import_result(record, resolution)
        self._update_readiness()

    def _apply_import_with_current_configuration(self, record, resolution):
        """Load imported annotations under the active configuration."""
        self._push_labels_to_tabs_for_import(self._label_config)
        self.set_record(record)
        self._sync_detected_volume()
        self._show_import_result(record, resolution)
        self._update_readiness()

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

        imported_config = record.label_config
        if imported_config is None:
            qt.QMessageBox.critical(
                self,
                "Import Failed",
                "The import package does not include label configuration.",
            )
            return False

        if label_configs_differ(self._label_config, imported_config):
            if not self._prompt_import_configuration_choice():
                return False
            self._apply_import_with_new_configuration(record, resolution)
            return True

        self._apply_import_with_current_configuration(record, resolution)
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
        self._remove_scene_observers()
        self._roi_tab.cleanup()
        self._segmentation_tab.cleanup()

    # ─── Actions ─────────────────────────────────────────────────────────

    def _collect_all_data(self):
        """Collect all tab data into the record."""
        self._record.class_labels = self._class_label_tab.get_class_label_annotations()
        self._record.rois = self._roi_tab.get_roi_annotations()
        self._record.segmentation = self._segmentation_tab.get_segmentation_data()

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
                "No annotations to export. Create annotations first."
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
