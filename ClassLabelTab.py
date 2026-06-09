import qt
import slicer

from AnnotationModel import ClassLabelAnnotation
from SliceInfo import capture_slice_info, install_slice_tracking, remove_slice_tracking


class ClassLabelTab(qt.QWidget):
    """
    Tab for assigning classification labels to an image series.
    Labels are provided by the configuration screen — no add/delete here.
    Each selected label stores the active slice instance at selection time.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = []  # List[LabelDefinition]
        self._checkboxes = []  # List[dict]: checkbox, slice_label, row, label_def
        self._selections = {}  # label name -> ClassLabelAnnotation
        self._volume_node = None
        self._setup_ui()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._volume_info_label = qt.QLabel("")
        self._volume_info_label.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(self._volume_info_label)

        heading = qt.QLabel("Select classification labels for this series")
        heading.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(heading)

        hint = qt.QLabel(
            "Scroll to the target slice first, then check a label. "
            "The anatomical plane and slice number appear next to each selection."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._scroll_area = qt.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_widget = qt.QWidget()
        self._scroll_layout = qt.QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.addStretch()

        self._scroll_area.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll_area)

        self._summary_label = qt.QLabel("Selected: (none)")
        self._summary_label.setStyleSheet("color: #555; font-style: italic;")
        layout.addWidget(self._summary_label)

    # ─── Public API ──────────────────────────────────────────────────────

    def set_labels(self, labels):
        """Populate the tab with configured class labels (LabelDefinition list)."""
        self._clear_checkboxes()
        self._labels = list(labels)
        self._selections = {}

        for label_def in self._labels:
            row = qt.QWidget()
            row_layout = qt.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            cb = qt.QCheckBox(label_def.name)
            cb.setToolTip(label_def.description)
            cb.toggled.connect(lambda checked, ld=label_def: self._on_toggled(ld, checked))
            row_layout.addWidget(cb)

            slice_label = qt.QLabel("")
            slice_label.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
            slice_label.setWordWrap(True)
            row_layout.addWidget(slice_label, 1)

            count = self._scroll_layout.count()
            self._scroll_layout.insertWidget(count - 1, row)
            self._checkboxes.append({
                "checkbox": cb,
                "slice_label": slice_label,
                "row": row,
                "label_def": label_def,
            })

    def get_class_label_annotations(self):
        """Return class label selections with slice instance metadata."""
        return list(self._selections.values())

    def get_selected_labels(self):
        """Return names of currently checked labels."""
        return list(self._selections.keys())

    def set_class_label_annotations(self, annotations):
        """Restore checked labels and slice metadata (for loading drafts)."""
        self._selections = {}
        for item in annotations:
            annotation = (
                item if isinstance(item, ClassLabelAnnotation) else ClassLabelAnnotation.from_dict(item)
            )
            if annotation.label:
                self._selections[annotation.label] = annotation

        for item in self._checkboxes:
            item["checkbox"].blockSignals(True)
            item["checkbox"].setChecked(item["label_def"].name in self._selections)
            item["checkbox"].blockSignals(False)
            self._refresh_slice_label(item)
        self._update_summary()

    def set_selected_labels(self, names):
        """Check boxes matching the given names (legacy load without slice metadata)."""
        self._selections = {}
        for name in names:
            if name:
                self._selections[name] = ClassLabelAnnotation(label=name)
        for item in self._checkboxes:
            item["checkbox"].blockSignals(True)
            item["checkbox"].setChecked(item["label_def"].name in self._selections)
            item["checkbox"].blockSignals(False)
            self._refresh_slice_label(item)
        self._update_summary()

    def set_volume(self, volume_node):
        """Display volume name and start tracking slice interactions."""
        self._volume_node = volume_node
        if volume_node:
            self._volume_info_label.setText(f"Series: {volume_node.GetName()}")
            install_slice_tracking()
        else:
            self._volume_info_label.setText("")
            remove_slice_tracking()

    def clear_and_unbind(self):
        """Uncheck all boxes. Labels persist from config."""
        self._selections = {}
        for item in self._checkboxes:
            item["checkbox"].blockSignals(True)
            item["checkbox"].setChecked(False)
            item["checkbox"].blockSignals(False)
            self._refresh_slice_label(item)
        self._volume_node = None
        self._volume_info_label.setText("")
        remove_slice_tracking()
        self._update_summary()

    # ─── Internal ────────────────────────────────────────────────────────

    def _clear_checkboxes(self):
        for item in self._checkboxes:
            item["row"].setParent(None)
            item["row"].deleteLater()
        self._checkboxes = []

    def _format_slice_display(self, annotation):
        if annotation is None:
            return ""
        plane = (annotation.slice_view or "").strip()
        if not plane and annotation.slicer_slice_view:
            plane = annotation.slicer_slice_view
        if not plane:
            plane = "Unknown plane"
        if annotation.slice_index:
            return f"{plane} · slice {annotation.slice_index}"
        return plane

    def _refresh_slice_label(self, item):
        label_name = item["label_def"].name
        checked = item["checkbox"].isChecked()
        slice_label = item["slice_label"]
        if not checked:
            slice_label.setText("")
            slice_label.setToolTip("")
            return
        annotation = self._selections.get(label_name)
        text = self._format_slice_display(annotation)
        slice_label.setText(text)
        if annotation and annotation.volume_slice_ijk:
            slice_label.setToolTip(f"IJK index: {annotation.volume_slice_ijk}")
        elif annotation and annotation.slice_position_ras:
            slice_label.setToolTip(f"RAS position: {annotation.slice_position_ras}")
        else:
            slice_label.setToolTip("")

    def _on_toggled(self, label_def, checked):
        if checked:
            slice_info = capture_slice_info(self._volume_node)
            self._selections[label_def.name] = ClassLabelAnnotation.from_slice_context(
                label_def, slice_info
            )
        else:
            self._selections.pop(label_def.name, None)
        for item in self._checkboxes:
            if item["label_def"].name == label_def.name:
                self._refresh_slice_label(item)
                break
        self._update_summary()

    def _update_summary(self):
        selected = self.get_selected_labels()
        if not selected:
            self._summary_label.setText("Selected: (none)")
            return
        count = len(selected)
        noun = "label" if count == 1 else "labels"
        self._summary_label.setText(f"Selected: {count} {noun}")
