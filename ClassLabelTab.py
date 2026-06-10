import qt

from AnnotationModel import ClassLabelAnnotation
from SliceInfo import capture_all_planes_slice_info, install_slice_tracking, remove_slice_tracking


class ClassLabelTab(qt.QWidget):
    """
    Tab for assigning classification labels to an image series.
    Labels are provided by the configuration screen. The user selects a label,
    presses Add, and a table row is created with slice indexes from all three planes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = []  # List[LabelDefinition]
        self._annotations = []  # List[ClassLabelAnnotation]
        self._label_buttons = {}  # label name -> QPushButton
        self._selected_label_def = None
        self._volume_node = None
        self._setup_ui()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._volume_info_label = qt.QLabel("")
        self._volume_info_label.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(self._volume_info_label)

        self._build_label_section(layout)
        self._build_table(layout)
        self._build_actions(layout)

    def _build_label_section(self, parent_layout):
        label_frame = qt.QFrame()
        label_frame.setFrameShape(qt.QFrame.StyledPanel)
        label_layout = qt.QVBoxLayout(label_frame)

        heading = qt.QLabel("Classification Labels")
        heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        label_layout.addWidget(heading)

        hint = qt.QLabel(
            "Position all three slice views, select a label, then press Add. "
            "Each row captures Axial, Coronal, and Sagittal slice indexes at that moment."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        label_layout.addWidget(hint)

        row = qt.QHBoxLayout()
        self._label_button_container = qt.QHBoxLayout()
        row.addLayout(self._label_button_container)
        row.addStretch()

        self._add_btn = qt.QPushButton("Add")
        self._add_btn.setStyleSheet(
            "QPushButton { padding: 6px 16px; font-weight: bold; }"
            "QPushButton:disabled { color: #999; }"
        )
        self._add_btn.clicked.connect(self._on_add_clicked)
        row.addWidget(self._add_btn)

        label_layout.addLayout(row)
        parent_layout.addWidget(label_frame)

    def _build_table(self, parent_layout):
        self._table = qt.QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["#", "Actions", "Label", "Axial Slice", "Coronal Slice", "Sagittal Slice", "Color"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(1, 80)
        self._table.setSelectionBehavior(qt.QTableWidget.SelectRows)
        self._table.setSelectionMode(qt.QTableWidget.SingleSelection)
        self._table.setEditTriggers(qt.QTableWidget.NoEditTriggers)
        parent_layout.addWidget(self._table)

    def _build_actions(self, parent_layout):
        action_row = qt.QHBoxLayout()

        self._delete_all_btn = qt.QPushButton("Delete All")
        self._delete_all_btn.clicked.connect(self._on_delete_all)
        action_row.addWidget(self._delete_all_btn)

        action_row.addStretch()

        self._count_label = qt.QLabel("Label count: 0")
        action_row.addWidget(self._count_label)

        parent_layout.addLayout(action_row)

    # ─── Public API ──────────────────────────────────────────────────────

    def set_labels(self, labels):
        """Populate the tab with configured class labels (LabelDefinition list)."""
        self._clear_label_buttons()
        self._labels = list(labels)
        self._annotations = []
        self._selected_label_def = None

        for label_def in self._labels:
            btn = qt.QPushButton(label_def.name)
            btn.setCheckable(True)
            btn.setToolTip(label_def.description)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 6px 12px; border: 2px solid {label_def.color}; }}"
                "QPushButton:checked { background-color: #2196F3; color: white; }"
            )
            btn.toggled.connect(lambda checked, ld=label_def: self._on_label_button_toggled(ld, checked))
            self._label_button_container.addWidget(btn)
            self._label_buttons[label_def.name] = btn

        self._refresh_table()
        self._update_add_button_state()

    def get_class_label_annotations(self):
        """Return class label selections with slice instance metadata."""
        return list(self._annotations)

    def get_selected_labels(self):
        """Return unique label names present in the annotation table."""
        return list(dict.fromkeys(ann.label for ann in self._annotations if ann.label))

    def set_class_label_annotations(self, annotations):
        """Restore annotation rows (for loading drafts)."""
        self._annotations = []
        for item in annotations:
            annotation = (
                item if isinstance(item, ClassLabelAnnotation) else ClassLabelAnnotation.from_dict(item)
            )
            if annotation.label:
                self._annotations.append(annotation)
        self._refresh_table()

    def set_selected_labels(self, names):
        """Add rows for the given label names (legacy load without slice metadata)."""
        self._annotations = []
        label_by_name = {label_def.name: label_def for label_def in self._labels}
        for name in names:
            if not name:
                continue
            label_def = label_by_name.get(name)
            if label_def:
                self._annotations.append(ClassLabelAnnotation(
                    label=label_def.name,
                    category_id=label_def.id,
                    category_color=label_def.color,
                    category_description=label_def.description,
                ))
            else:
                self._annotations.append(ClassLabelAnnotation(label=name))
        self._refresh_table()

    def set_volume(self, volume_node):
        """Display volume name and start tracking slice interactions."""
        self._volume_node = volume_node
        if volume_node:
            self._volume_info_label.setText(f"Series: {volume_node.GetName()}")
            install_slice_tracking()
        else:
            self._volume_info_label.setText("")
            remove_slice_tracking()
        self._update_add_button_state()

    def clear_and_unbind(self):
        """Clear all annotation rows. Labels persist from config."""
        self._annotations = []
        self._volume_node = None
        self._volume_info_label.setText("")
        self._clear_label_selection()
        remove_slice_tracking()
        self._refresh_table()

    # ─── Internal ────────────────────────────────────────────────────────

    def _clear_label_buttons(self):
        for btn in self._label_buttons.values():
            btn.setParent(None)
            btn.deleteLater()
        self._label_buttons = {}
        while self._label_button_container.count():
            item = self._label_button_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _clear_label_selection(self):
        self._selected_label_def = None
        for btn in self._label_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)

    def _on_label_button_toggled(self, label_def, checked):
        if checked:
            for name, btn in self._label_buttons.items():
                if name != label_def.name:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            self._selected_label_def = label_def
        elif self._selected_label_def and self._selected_label_def.name == label_def.name:
            self._selected_label_def = None
        self._update_add_button_state()

    def _update_add_button_state(self):
        can_add = bool(self._selected_label_def and self._volume_node)
        self._add_btn.setEnabled(can_add)
        if not self._volume_node:
            self._add_btn.setToolTip("Load a scan before adding labels")
        elif not self._selected_label_def:
            self._add_btn.setToolTip("Select a label first")
        else:
            self._add_btn.setToolTip("")

    def _on_add_clicked(self):
        if not self._selected_label_def or not self._volume_node:
            return

        plane_infos = capture_all_planes_slice_info(self._volume_node)
        annotation = ClassLabelAnnotation.from_all_planes_context(
            self._selected_label_def, plane_infos
        )
        self._annotations.append(annotation)
        self._refresh_table()

    def _format_plane_slice(self, annotation, plane_name):
        plane_slice = annotation.get_plane_slice(plane_name)
        if not plane_slice or not plane_slice.slice_index:
            return "—"
        return str(plane_slice.slice_index)

    def _refresh_table(self):
        self._table.setRowCount(len(self._annotations))
        for row, annotation in enumerate(self._annotations):
            self._table.setItem(row, 0, qt.QTableWidgetItem(str(row + 1)))
            self._table.setItem(row, 1, qt.QTableWidgetItem(""))
            self._table.setItem(row, 2, qt.QTableWidgetItem(annotation.label))
            self._table.setItem(row, 3, qt.QTableWidgetItem(self._format_plane_slice(annotation, "Axial")))
            self._table.setItem(row, 4, qt.QTableWidgetItem(self._format_plane_slice(annotation, "Coronal")))
            self._table.setItem(row, 5, qt.QTableWidgetItem(self._format_plane_slice(annotation, "Sagittal")))
            self._table.setItem(row, 6, qt.QTableWidgetItem(annotation.category_color or ""))

            delete_btn = qt.QPushButton("✕")
            delete_btn.setFixedSize(28, 24)
            delete_btn.setToolTip("Remove this label row")
            delete_btn.clicked.connect(lambda _checked=False, r=row: self._on_delete_row(r))
            self._table.setCellWidget(row, 1, delete_btn)

            color_item = self._table.item(row, 6)
            if color_item and annotation.category_color:
                color_item.setBackground(qt.QColor(annotation.category_color))

            for col in (0, 2, 3, 4, 5):
                item = self._table.item(row, col)
                if item:
                    plane_slice = None
                    if col == 3:
                        plane_slice = annotation.get_plane_slice("Axial")
                    elif col == 4:
                        plane_slice = annotation.get_plane_slice("Coronal")
                    elif col == 5:
                        plane_slice = annotation.get_plane_slice("Sagittal")
                    if plane_slice and plane_slice.slice_offset_mm:
                        item.setToolTip(f"Physical offset: {plane_slice.slice_offset_mm:.2f} mm")
                    elif plane_slice and plane_slice.slice_position_ras:
                        item.setToolTip(f"RAS: {plane_slice.slice_position_ras}")

        self._count_label.setText(f"Label count: {len(self._annotations)}")
        self._update_add_button_state()

    def _on_delete_row(self, row):
        if 0 <= row < len(self._annotations):
            self._annotations.pop(row)
            self._refresh_table()

    def _on_delete_all(self):
        if not self._annotations:
            return
        self._annotations = []
        self._refresh_table()
