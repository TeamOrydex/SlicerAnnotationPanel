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
        self._checkboxes = []  # List[dict] with "widget" and "label_def"
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
            "The anatomical plane, slice number, and RAS position are recorded."
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
            cb = qt.QCheckBox(label_def.name)
            cb.setToolTip(label_def.description)
            cb.toggled.connect(lambda checked, ld=label_def: self._on_toggled(ld, checked))
            count = self._scroll_layout.count()
            self._scroll_layout.insertWidget(count - 1, cb)
            self._checkboxes.append({"widget": cb, "label_def": label_def})

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
            item["widget"].blockSignals(True)
            item["widget"].setChecked(item["label_def"].name in self._selections)
            item["widget"].blockSignals(False)
        self._update_summary()

    def set_selected_labels(self, names):
        """Check boxes matching the given names (legacy load without slice metadata)."""
        self._selections = {}
        for name in names:
            if name:
                self._selections[name] = ClassLabelAnnotation(label=name)
        for item in self._checkboxes:
            item["widget"].blockSignals(True)
            item["widget"].setChecked(item["label_def"].name in self._selections)
            item["widget"].blockSignals(False)
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
            item["widget"].blockSignals(True)
            item["widget"].setChecked(False)
            item["widget"].blockSignals(False)
        self._volume_node = None
        self._volume_info_label.setText("")
        remove_slice_tracking()
        self._update_summary()

    # ─── Internal ────────────────────────────────────────────────────────

    def _clear_checkboxes(self):
        for item in self._checkboxes:
            item["widget"].setParent(None)
            item["widget"].deleteLater()
        self._checkboxes = []

    def _on_toggled(self, label_def, checked):
        if checked:
            slice_info = capture_slice_info(self._volume_node)
            self._selections[label_def.name] = ClassLabelAnnotation.from_slice_context(
                label_def, slice_info
            )
        else:
            self._selections.pop(label_def.name, None)
        self._update_summary()

    def _update_summary(self):
        selected = self.get_selected_labels()
        if not selected:
            self._summary_label.setText("Selected: (none)")
            return

        parts = []
        for name in selected:
            ann = self._selections.get(name)
            if ann and ann.slice_view:
                plane = ann.slice_view
                suffix = f"{plane}, slice {ann.slice_index}"
                if ann.volume_slice_ijk:
                    suffix += f", IJK {ann.volume_slice_ijk}"
                parts.append(f"{name} ({suffix})")
            else:
                parts.append(name)
        self._summary_label.setText("Selected: " + "; ".join(parts))
