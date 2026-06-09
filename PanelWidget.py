import os
import qt
import json
import slicer

from AnnotationModel import AnnotationRecord
from ClassLabelTab import ClassLabelTab
from ROITab import ROITab
from SegmentationTab import SegmentationTab


class AnnotationPanelRootWidget(qt.QWidget):
    """
    Root panel widget: header, tab bar, active tab content, and action bar.
    Manages a single AnnotationRecord and coordinates annotation workflow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._record = AnnotationRecord()
        self._setup_ui()
        self._connect_label_sync()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = qt.QVBoxLayout(self)

        self._build_header(main_layout)
        self._build_tabs(main_layout)
        self._build_action_bar(main_layout)

    def _build_header(self, parent_layout):
        header_frame = qt.QFrame()
        header_frame.setFrameShape(qt.QFrame.StyledPanel)
        header_layout = qt.QHBoxLayout(header_frame)

        self._study_label = qt.QLabel("Study: \u2014")
        self._series_label = qt.QLabel("Series: \u2014")
        header_layout.addWidget(self._study_label)
        header_layout.addWidget(self._series_label)
        header_layout.addStretch()

        parent_layout.addWidget(header_frame)

    def _build_tabs(self, parent_layout):
        self._tab_widget = qt.QTabWidget()

        self._class_label_tab = ClassLabelTab(annotation_record=self._record)
        self._roi_tab = ROITab(annotation_record=self._record)
        self._segmentation_tab = SegmentationTab()

        self._tab_widget.addTab(self._class_label_tab, "Class Labels")
        self._tab_widget.addTab(self._roi_tab, "ROI")
        self._tab_widget.addTab(self._segmentation_tab, "Segmentation")

        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        parent_layout.addWidget(self._tab_widget)

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

    # ─── Label Synchronization ───────────────────────────────────────────

    def _connect_label_sync(self):
        """Connect ClassLabelTab checkbox changes to ROI tab label refresh."""
        original_toggled = self._class_label_tab._on_checkbox_toggled
        original_add = self._class_label_tab._on_add_custom

        def patched_toggled(checked):
            original_toggled(checked)
            self._sync_labels_to_roi_tab()

        def patched_add():
            original_add()
            self._sync_labels_to_roi_tab()

        self._class_label_tab._on_checkbox_toggled = patched_toggled
        self._class_label_tab._on_add_custom = patched_add

        self._sync_labels_to_roi_tab()

    def _sync_labels_to_roi_tab(self):
        """Push the current label list from ClassLabelTab to ROITab's combo box."""
        all_labels = list(self._class_label_tab._checkboxes.keys())
        self._roi_tab.refresh_labels(all_labels)

    # ─── Tab Switching ───────────────────────────────────────────────────

    def _on_tab_changed(self, index):
        """Cancel active tools when leaving ROI or Segmentation tabs."""
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
        self._class_label_tab.set_annotation_record(record)
        self._roi_tab.set_annotation_record(record)
        self._study_label.setText(f"Study: {record.study_id}")
        self._series_label.setText(f"Series: {record.series_id}")

        if record.rois:
            self._roi_tab.load_rois(record.rois)

        if record.segmentation:
            self._segmentation_tab.load_segmentation(record.segmentation)

    def load_annotation(self, filepath):
        """Read a JSON file and populate the panel. Unknown keys are ignored."""
        with open(filepath, "r") as f:
            data = json.load(f)
        record = AnnotationRecord.from_dict(data)
        self.set_record(record)

    def cleanup(self):
        """Clean up observers when the panel is destroyed."""
        self._roi_tab.cleanup()
        self._segmentation_tab.cleanup()

    # ─── Actions ─────────────────────────────────────────────────────────

    def _collect_all_data(self):
        """Collect all tab data into the record."""
        self._record.rois = self._roi_tab.get_roi_annotations()
        self._record.segmentation = self._segmentation_tab.get_segmentation_data()

    def _on_save_draft(self):
        filepath = qt.QFileDialog.getSaveFileName(
            self, "Save Annotation", "", "JSON Files (*.json)"
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
                self, "Nothing to Export", "No annotations to export."
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
            seg_tab = self._segmentation_tab
            if seg_tab._segmentation_node is not None:
                volume_node = seg_tab._volume_selector.currentNode()
                if volume_node:
                    seg_path = os.path.join(export_dir, "segmentation.nrrd")
                    labelmap_node = slicer.mrmlScene.AddNewNodeByClass(
                        "vtkMRMLLabelMapVolumeNode"
                    )
                    try:
                        slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                            seg_tab._segmentation_node, labelmap_node, volume_node
                        )
                        slicer.util.saveNode(labelmap_node, seg_path)
                        exported_files.append("segmentation.nrrd")
                    except Exception as e:
                        qt.QMessageBox.warning(
                            self, "Segmentation Export Warning",
                            f"Could not export segmentation: {e}"
                        )
                    finally:
                        slicer.mrmlScene.RemoveNode(labelmap_node)

        qt.QMessageBox.information(
            self, "Export Complete",
            f"Exported to: {export_dir}\n\nFiles:\n" +
            "\n".join(f"  \u2022 {f}" for f in exported_files)
        )
