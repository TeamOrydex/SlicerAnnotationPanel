import qt

DEFAULT_LABELS = [
    "Normal",
    "Pathological",
    "Artifact",
    "Motion Blur",
    "Incomplete Coverage",
]


class ClassLabelTab(qt.QWidget):
    """
    Tab for assigning class-level labels to a scan.
    Provides a scrollable list of checkboxes plus the ability to add custom labels.
    """

    def __init__(self, annotation_record=None, labels=None, parent=None):
        super().__init__(parent)
        self._record = annotation_record
        self._labels = list(labels) if labels else list(DEFAULT_LABELS)
        self._checkboxes = {}
        self._volume_node = None
        self._setup_ui()
        self._sync_from_record()

    def set_annotation_record(self, record):
        self._record = record
        self._sync_from_record()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._volume_info_label = qt.QLabel("")
        self._volume_info_label.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(self._volume_info_label)

        heading = qt.QLabel("Assign class labels to this scan")
        heading.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(heading)

        self._scroll_area = qt.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_widget = qt.QWidget()
        self._scroll_layout = qt.QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setSpacing(4)

        for label in self._labels:
            self._add_checkbox(label)

        self._scroll_layout.addStretch()
        self._scroll_area.setWidget(self._scroll_widget)
        layout.addWidget(self._scroll_area)

        add_row = qt.QHBoxLayout()
        self._custom_input = qt.QLineEdit()
        self._custom_input.setPlaceholderText("Enter custom label...")
        add_row.addWidget(self._custom_input)

        self._add_btn = qt.QPushButton("Add Custom Label")
        self._add_btn.clicked.connect(self._on_add_custom)
        add_row.addWidget(self._add_btn)
        layout.addLayout(add_row)

        self._summary_label = qt.QLabel("Selected: (none)")
        self._summary_label.setStyleSheet("color: #555; font-style: italic;")
        layout.addWidget(self._summary_label)

    def _add_checkbox(self, label_text):
        cb = qt.QCheckBox(label_text)
        cb.toggled.connect(self._on_checkbox_toggled)
        self._checkboxes[label_text] = cb
        count = self._scroll_layout.count()
        self._scroll_layout.insertWidget(count - 1, cb)

    def _on_checkbox_toggled(self, checked):
        self._update_record()
        self._update_summary()

    def _on_add_custom(self):
        text = self._custom_input.text.strip()
        if not text:
            return
        if text in self._checkboxes:
            qt.QMessageBox.warning(
                self, "Duplicate Label",
                f"The label \"{text}\" already exists."
            )
            return
        self._add_checkbox(text)
        self._checkboxes[text].setChecked(True)
        self._custom_input.clear()

    def _update_record(self):
        if self._record is None:
            return
        selected = [name for name, cb in self._checkboxes.items() if cb.isChecked()]
        self._record.class_labels = selected

    def _update_summary(self):
        selected = [name for name, cb in self._checkboxes.items() if cb.isChecked()]
        if selected:
            self._summary_label.setText("Selected: " + ", ".join(selected))
        else:
            self._summary_label.setText("Selected: (none)")

    def _sync_from_record(self):
        """Populate checkboxes from the annotation record."""
        if self._record is None:
            return
        for name, cb in self._checkboxes.items():
            cb.setChecked(name in self._record.class_labels)
        for label in self._record.class_labels:
            if label not in self._checkboxes:
                self._add_checkbox(label)
                self._checkboxes[label].setChecked(True)
        self._update_summary()

    # ─── Volume Binding ──────────────────────────────────────────────────

    def set_volume(self, volume_node):
        """Store volume reference and display its name."""
        self._volume_node = volume_node
        if volume_node:
            self._volume_info_label.setText(f"Annotating: {volume_node.GetName()}")
        else:
            self._volume_info_label.setText("")

    def clear_and_unbind(self):
        """Clear all selections and reset to defaults."""
        for cb in self._checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        # Remove custom labels (keep only defaults)
        for label_text in list(self._checkboxes.keys()):
            if label_text not in DEFAULT_LABELS:
                cb = self._checkboxes.pop(label_text)
                cb.setParent(None)
                cb.deleteLater()
        self._volume_node = None
        self._volume_info_label.setText("")
        self._update_summary()
        if self._record:
            self._record.class_labels = []

    def get_selected_labels(self):
        """Return list of currently checked labels."""
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]
