import qt


class ClassLabelTab(qt.QWidget):
    """
    Tab for assigning class-level labels to a scan.
    Labels are provided by the configuration screen — no add/delete here.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = []  # List[LabelDefinition]
        self._checkboxes = []  # List[dict] with "widget" and "label_def"
        self._volume_node = None
        self._setup_ui()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._volume_info_label = qt.QLabel("")
        self._volume_info_label.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(self._volume_info_label)

        heading = qt.QLabel("Select class labels for this scan")
        heading.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(heading)

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

        for label_def in self._labels:
            cb = qt.QCheckBox(label_def.name)
            cb.setToolTip(label_def.description)
            cb.toggled.connect(self._on_toggled)
            count = self._scroll_layout.count()
            self._scroll_layout.insertWidget(count - 1, cb)
            self._checkboxes.append({"widget": cb, "label_def": label_def})

    def get_selected_labels(self):
        """Return names of currently checked labels."""
        return [item["label_def"].name for item in self._checkboxes if item["widget"].isChecked()]

    def set_selected_labels(self, names):
        """Check boxes matching the given names (for loading drafts)."""
        name_set = set(names)
        for item in self._checkboxes:
            item["widget"].blockSignals(True)
            item["widget"].setChecked(item["label_def"].name in name_set)
            item["widget"].blockSignals(False)
        self._update_summary()

    def set_volume(self, volume_node):
        """Display volume name."""
        self._volume_node = volume_node
        if volume_node:
            self._volume_info_label.setText(f"Annotating: {volume_node.GetName()}")
        else:
            self._volume_info_label.setText("")

    def clear_and_unbind(self):
        """Uncheck all boxes. Labels persist from config."""
        for item in self._checkboxes:
            item["widget"].blockSignals(True)
            item["widget"].setChecked(False)
            item["widget"].blockSignals(False)
        self._volume_node = None
        self._volume_info_label.setText("")
        self._update_summary()

    # ─── Internal ────────────────────────────────────────────────────────

    def _clear_checkboxes(self):
        for item in self._checkboxes:
            item["widget"].setParent(None)
            item["widget"].deleteLater()
        self._checkboxes = []

    def _on_toggled(self, checked):
        self._update_summary()

    def _update_summary(self):
        selected = self.get_selected_labels()
        if selected:
            self._summary_label.setText("Selected: " + ", ".join(selected))
        else:
            self._summary_label.setText("Selected: (none)")
