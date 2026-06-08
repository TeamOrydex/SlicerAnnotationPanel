import qt
import json
from datetime import datetime

from AnnotationModel import AnnotationRecord
from ClassLabelTab import ClassLabelTab
from ROITab import ROITab
from SegmentationTab import SegmentationTab
from FreeformJsonTab import FreeformJsonTab
from ReviewBar import ReviewBar


STATUS_COLORS = {
    "draft": "#888888",
    "submitted": "#2196F3",
    "approved": "#4CAF50",
    "rejected": "#f44336",
}


class AnnotationPanelRootWidget(qt.QWidget):
    """
    Root panel widget: header, tab bar, active tab content, and action bar.
    Manages a single AnnotationRecord and coordinates annotator/reviewer workflow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._record = AnnotationRecord()
        self._is_reviewer_mode = False
        self._setup_ui()
        self._update_status_display()
        self._update_action_bar()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = qt.QVBoxLayout(self)

        self._build_header(main_layout)
        self._build_tabs(main_layout)
        self._build_action_bar(main_layout)

    def _build_header(self, parent_layout):
        header_frame = qt.QFrame()
        header_frame.setFrameShape(qt.QFrame.StyledPanel)
        header_layout = qt.QVBoxLayout(header_frame)

        info_row = qt.QHBoxLayout()
        self._study_label = qt.QLabel("Study: —")
        self._series_label = qt.QLabel("Series: —")
        info_row.addWidget(self._study_label)
        info_row.addWidget(self._series_label)
        info_row.addStretch()
        header_layout.addLayout(info_row)

        status_row = qt.QHBoxLayout()
        self._status_label = qt.QLabel("Status: ● Draft")
        self._status_label.setStyleSheet("font-weight: bold;")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        header_layout.addLayout(status_row)

        mode_row = qt.QHBoxLayout()
        mode_label = qt.QLabel("Mode:")
        mode_row.addWidget(mode_label)

        self._mode_group = qt.QButtonGroup(self)
        self._annotator_radio = qt.QRadioButton("Annotator")
        self._reviewer_radio = qt.QRadioButton("Reviewer")
        self._annotator_radio.setChecked(True)
        self._mode_group.addButton(self._annotator_radio, 0)
        self._mode_group.addButton(self._reviewer_radio, 1)
        mode_row.addWidget(self._annotator_radio)
        mode_row.addWidget(self._reviewer_radio)
        mode_row.addStretch()
        header_layout.addLayout(mode_row)

        self._annotator_radio.toggled.connect(self._on_mode_changed)

        parent_layout.addWidget(header_frame)

    def _build_tabs(self, parent_layout):
        self._tab_widget = qt.QTabWidget()

        self._class_label_tab = ClassLabelTab(annotation_record=self._record)
        self._roi_tab = ROITab()
        self._segmentation_tab = SegmentationTab()
        self._freeform_tab = FreeformJsonTab()

        self._tab_widget.addTab(self._class_label_tab, "Class Labels")
        self._tab_widget.addTab(self._roi_tab, "ROI")
        self._tab_widget.addTab(self._segmentation_tab, "Segmentation")
        self._tab_widget.addTab(self._freeform_tab, "JSON")

        parent_layout.addWidget(self._tab_widget)

    def _build_action_bar(self, parent_layout):
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        parent_layout.addWidget(separator)

        self._action_container = qt.QWidget()
        self._action_layout = qt.QVBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 4, 0, 0)

        # Annotator buttons
        self._annotator_bar = qt.QWidget()
        ann_layout = qt.QHBoxLayout(self._annotator_bar)
        ann_layout.setContentsMargins(0, 0, 0, 0)

        self._save_draft_btn = qt.QPushButton("Save Draft")
        self._save_draft_btn.clicked.connect(self._on_save_draft)
        ann_layout.addWidget(self._save_draft_btn)

        self._submit_btn = qt.QPushButton("Submit for Review")
        self._submit_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 6px 16px; border-radius: 3px; }"
        )
        self._submit_btn.clicked.connect(self._on_submit)
        ann_layout.addWidget(self._submit_btn)

        ann_layout.addStretch()
        self._action_layout.addWidget(self._annotator_bar)

        # Reviewer bar
        self._review_bar = ReviewBar()
        self._review_bar.set_callbacks(
            on_approve=self._on_approve,
            on_reject=self._on_reject,
        )
        self._review_bar.hide()
        self._action_layout.addWidget(self._review_bar)

        parent_layout.addWidget(self._action_container)

    # ─── Public API ──────────────────────────────────────────────────────

    def set_study_info(self, study_id, series_id):
        self._record.study_id = study_id
        self._record.series_id = series_id
        self._study_label.setText(f"Study: {study_id}")
        self._series_label.setText(f"Series: {series_id}")

    def get_record(self):
        return self._record

    def set_record(self, record):
        self._record = record
        self._class_label_tab.set_annotation_record(record)
        self._study_label.setText(f"Study: {record.study_id}")
        self._series_label.setText(f"Series: {record.series_id}")
        self._update_status_display()
        self._review_bar.show_review_info(record)
        if record.status in ("submitted", "approved", "rejected"):
            self._set_tabs_read_only(True)

    def load_annotation(self, filepath):
        """Read a JSON file and populate the panel."""
        with open(filepath, "r") as f:
            data = json.load(f)
        record = AnnotationRecord.from_dict(data)
        self.set_record(record)

    # ─── Mode Switching ──────────────────────────────────────────────────

    def _on_mode_changed(self, checked):
        self._is_reviewer_mode = self._reviewer_radio.isChecked()
        self._update_action_bar()
        if self._is_reviewer_mode:
            self._review_bar.show_review_info(self._record)

    def _update_action_bar(self):
        if self._is_reviewer_mode:
            self._annotator_bar.hide()
            self._review_bar.show()
        else:
            self._annotator_bar.show()
            self._review_bar.hide()

    # ─── Actions ─────────────────────────────────────────────────────────

    def _on_save_draft(self):
        filepath = qt.QFileDialog.getSaveFileName(
            self, "Save Annotation", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        self._record.status = "draft"
        with open(filepath, "w") as f:
            f.write(self._record.to_json())
        self._update_status_display()

    def _on_submit(self):
        self._record.status = "submitted"
        self._update_status_display()
        self._set_tabs_read_only(True)

    def _on_approve(self):
        self._record.status = "approved"
        self._record.reviewed_by = "reviewer"
        self._record.reviewed_at = datetime.utcnow().isoformat()
        self._update_status_display()
        self._review_bar.show_review_info(self._record)

    def _on_reject(self, comments):
        self._record.status = "rejected"
        self._record.reviewed_by = "reviewer"
        self._record.reviewed_at = datetime.utcnow().isoformat()
        self._record.review_comments = comments
        self._update_status_display()
        self._review_bar.show_review_info(self._record)

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _update_status_display(self):
        status = self._record.status
        color = STATUS_COLORS.get(status, "#888888")
        self._status_label.setText(f"Status: ● {status.capitalize()}")
        self._status_label.setStyleSheet(f"font-weight: bold; color: {color};")

    def _set_tabs_read_only(self, enabled):
        self._class_label_tab.set_read_only(enabled)
        self._roi_tab.set_read_only(enabled)
        self._segmentation_tab.set_read_only(enabled)
        self._freeform_tab.set_read_only(enabled)
