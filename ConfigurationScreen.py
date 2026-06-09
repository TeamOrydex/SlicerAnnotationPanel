import qt
import json

from AnnotationModel import LabelDefinition, LabelConfig


PRESETS = {
    "Brain Tumor Annotation": {
        "class_labels": [
            {"name": "Normal", "color": "#4CAF50", "description": "No findings"},
            {"name": "Pathological", "color": "#f44336", "description": "Has findings"},
        ],
        "roi_labels": [
            {"name": "Tumor", "color": "#e6194b", "description": "Tumor region"},
            {"name": "Lesion", "color": "#f58231", "description": "Lesion area"},
            {"name": "Cyst", "color": "#42d4f4", "description": "Cyst region"},
            {"name": "Artifact", "color": "#808080", "description": "Scan artifact"},
        ],
        "segmentation_classes": [
            {"name": "Tumor Core", "color": "#e6194b", "description": "Solid tumor"},
            {"name": "Enhancing Tumor", "color": "#ffe119", "description": "Enhancing region"},
            {"name": "Edema", "color": "#3cb44b", "description": "Peritumoral edema"},
            {"name": "Necrosis", "color": "#911eb4", "description": "Necrotic core"},
        ],
    },
    "Chest CT Annotation": {
        "class_labels": [
            {"name": "Normal", "color": "#4CAF50", "description": "Normal scan"},
            {"name": "Abnormal", "color": "#f44336", "description": "Abnormal findings"},
            {"name": "Inconclusive", "color": "#FF9800", "description": "Cannot determine"},
        ],
        "roi_labels": [
            {"name": "Nodule", "color": "#e6194b", "description": "Pulmonary nodule"},
            {"name": "Mass", "color": "#f58231", "description": "Large mass"},
            {"name": "Consolidation", "color": "#4363d8", "description": "Consolidation area"},
            {"name": "Ground Glass Opacity", "color": "#42d4f4", "description": "GGO region"},
        ],
        "segmentation_classes": [
            {"name": "Lung Parenchyma", "color": "#3cb44b", "description": "Lung tissue"},
            {"name": "Nodule", "color": "#e6194b", "description": "Nodule mask"},
            {"name": "Pleural Effusion", "color": "#4363d8", "description": "Fluid collection"},
        ],
    },
    "Cardiac MRI Annotation": {
        "class_labels": [
            {"name": "Normal", "color": "#4CAF50", "description": "Normal function"},
            {"name": "Reduced EF", "color": "#f44336", "description": "Reduced ejection fraction"},
        ],
        "roi_labels": [
            {"name": "Infarct", "color": "#e6194b", "description": "Infarct region"},
            {"name": "Thrombus", "color": "#911eb4", "description": "Thrombus location"},
            {"name": "Valve", "color": "#4363d8", "description": "Valve annotation"},
        ],
        "segmentation_classes": [
            {"name": "LV Myocardium", "color": "#e6194b", "description": "Left ventricle wall"},
            {"name": "LV Cavity", "color": "#3cb44b", "description": "LV blood pool"},
            {"name": "RV Cavity", "color": "#4363d8", "description": "RV blood pool"},
        ],
    },
}


class LabelCategoryWidget(qt.QGroupBox):
    """Reusable group-box that manages a table of label definitions for one category."""

    def __init__(self, title, subtitle, parent=None):
        super().__init__(title, parent)
        self._subtitle = subtitle

        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        subtitle_label = qt.QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 4px;")
        layout.addWidget(subtitle_label)

        self._table = qt.QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Color", "Name", "Description", "Actions"])
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(2, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(3, qt.QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self._table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self._table.setMinimumHeight(120)
        layout.addWidget(self._table)

        add_btn = qt.QPushButton("+ Add")
        add_btn.setStyleSheet(
            "QPushButton { color: #1976D2; background: transparent; border: 1px dashed #1976D2;"
            " border-radius: 4px; padding: 4px 12px; font-weight: bold; }"
            " QPushButton:hover { background: #E3F2FD; }"
        )
        add_btn.clicked.connect(self._add_label)
        layout.addWidget(add_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_labels(self):
        """Return a list of LabelDefinition built from the current table rows.
        Preserves existing IDs stored in UserRole+1 on the name item."""
        labels = []
        for row in range(self._table.rowCount):
            color_item = self._table.item(row, 0)
            name_item = self._table.item(row, 1)
            desc_item = self._table.item(row, 2)
            label_id = name_item.data(qt.Qt.UserRole) if name_item else ""
            if not label_id:
                import uuid
                label_id = str(uuid.uuid4())
            labels.append(
                LabelDefinition(
                    id=label_id,
                    name=name_item.text() if name_item else "",
                    color=color_item.data(qt.Qt.UserRole) if color_item else "#ff0000",
                    description=desc_item.text() if desc_item else "",
                )
            )
        return labels

    def set_labels(self, labels):
        """Clear the table and populate it from a list of LabelDefinition."""
        self._table.setRowCount(0)
        for lbl in labels:
            self._insert_row(lbl.name, lbl.color, lbl.description, lbl.id)

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _insert_row(self, name, color, description, label_id=""):
        row = self._table.rowCount
        self._table.insertRow(row)

        color_item = qt.QTableWidgetItem("  ")
        color_item.setBackground(qt.QColor(color))
        color_item.setData(qt.Qt.UserRole, color)
        color_item.setFlags(color_item.flags() & ~qt.Qt.ItemIsEditable)
        self._table.setItem(row, 0, color_item)

        name_item = qt.QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~qt.Qt.ItemIsEditable)
        name_item.setData(qt.Qt.UserRole, label_id)
        self._table.setItem(row, 1, name_item)

        desc_item = qt.QTableWidgetItem(description)
        desc_item.setFlags(desc_item.flags() & ~qt.Qt.ItemIsEditable)
        self._table.setItem(row, 2, desc_item)

        actions_widget = qt.QWidget()
        actions_layout = qt.QHBoxLayout()
        actions_layout.setContentsMargins(2, 0, 2, 0)
        actions_layout.setSpacing(2)
        actions_widget.setLayout(actions_layout)

        edit_btn = qt.QPushButton("\u270E")
        edit_btn.setToolTip("Edit")
        edit_btn.setFixedSize(28, 28)
        edit_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; }"
            " QPushButton:hover { background: #E3F2FD; border-radius: 4px; }"
        )
        edit_btn.clicked.connect(lambda _r=row: self._edit_label(_r))
        actions_layout.addWidget(edit_btn)

        delete_btn = qt.QPushButton("\u2715")
        delete_btn.setToolTip("Delete")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; color: #c62828; }"
            " QPushButton:hover { background: #FFEBEE; border-radius: 4px; }"
        )
        delete_btn.clicked.connect(lambda _r=row: self._delete_label(_r))
        actions_layout.addWidget(delete_btn)

        self._table.setCellWidget(row, 3, actions_widget)

    def _refresh_action_connections(self):
        """Rebuild action-button connections after a row is removed so indices stay correct."""
        for row in range(self._table.rowCount):
            actions_widget = qt.QWidget()
            actions_layout = qt.QHBoxLayout()
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(2)
            actions_widget.setLayout(actions_layout)

            edit_btn = qt.QPushButton("\u270E")
            edit_btn.setToolTip("Edit")
            edit_btn.setFixedSize(28, 28)
            edit_btn.setStyleSheet(
                "QPushButton { border: none; font-size: 14px; }"
                " QPushButton:hover { background: #E3F2FD; border-radius: 4px; }"
            )
            edit_btn.clicked.connect(lambda _r=row: self._edit_label(_r))
            actions_layout.addWidget(edit_btn)

            delete_btn = qt.QPushButton("\u2715")
            delete_btn.setToolTip("Delete")
            delete_btn.setFixedSize(28, 28)
            delete_btn.setStyleSheet(
                "QPushButton { border: none; font-size: 14px; color: #c62828; }"
                " QPushButton:hover { background: #FFEBEE; border-radius: 4px; }"
            )
            delete_btn.clicked.connect(lambda _r=row: self._delete_label(_r))
            actions_layout.addWidget(delete_btn)

            self._table.setCellWidget(row, 3, actions_widget)

    # ------------------------------------------------------------------
    # Add / Edit / Delete
    # ------------------------------------------------------------------

    def _add_label(self):
        result = self._open_label_dialog("Add Label", "", "#ff0000", "")
        if result is None:
            return
        name, color, description = result
        if not self._validate_name(name):
            return
        self._insert_row(name, color, description)

    def _edit_label(self, row):
        if row < 0 or row >= self._table.rowCount:
            return
        old_name = self._table.item(row, 1).text()
        old_color = self._table.item(row, 0).data(qt.Qt.UserRole)
        old_desc = self._table.item(row, 2).text()

        result = self._open_label_dialog("Edit Label", old_name, old_color, old_desc)
        if result is None:
            return
        name, color, description = result
        if not self._validate_name(name, exclude_row=row):
            return

        self._table.item(row, 1).setText(name)
        self._table.item(row, 2).setText(description)
        color_item = self._table.item(row, 0)
        color_item.setBackground(qt.QColor(color))
        color_item.setData(qt.Qt.UserRole, color)

    def _delete_label(self, row):
        if row < 0 or row >= self._table.rowCount:
            return
        name = self._table.item(row, 1).text()
        reply = qt.QMessageBox.question(
            self,
            "Delete Label",
            f'Remove label "{name}"?',
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if reply != qt.QMessageBox.Yes:
            return
        self._table.removeRow(row)
        self._refresh_action_connections()

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def _open_label_dialog(self, title, name, color, description):
        dialog = qt.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(340)

        form_layout = qt.QFormLayout()
        dialog.setLayout(form_layout)

        name_edit = qt.QLineEdit(name)
        form_layout.addRow("Name:", name_edit)

        color_btn = qt.QPushButton("")
        color_btn.setFixedHeight(28)
        chosen_color = {"value": color}

        def _update_color_btn():
            color_btn.setStyleSheet(
                f"background-color: {chosen_color['value']}; border: 1px solid #aaa; border-radius: 4px;"
            )
            color_btn.setText(chosen_color["value"])

        _update_color_btn()

        def _pick_color():
            qc = qt.QColorDialog.getColor(qt.QColor(chosen_color["value"]), self, "Select Color")
            if qc.isValid():
                chosen_color["value"] = qc.name()
                _update_color_btn()

        color_btn.clicked.connect(_pick_color)
        form_layout.addRow("Color:", color_btn)

        desc_edit = qt.QLineEdit(description)
        form_layout.addRow("Description:", desc_edit)

        btn_box = qt.QDialogButtonBox(qt.QDialogButtonBox.Save | qt.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        form_layout.addRow(btn_box)

        if dialog.exec_() != qt.QDialog.Accepted:
            return None
        return name_edit.text.strip(), chosen_color["value"], desc_edit.text.strip()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_name(self, name, exclude_row=-1):
        if not name:
            qt.QMessageBox.warning(self, "Validation", "Label name cannot be empty.")
            return False
        for row in range(self._table.rowCount):
            if row == exclude_row:
                continue
            existing = self._table.item(row, 1)
            if existing and existing.text().lower() == name.lower():
                qt.QMessageBox.warning(
                    self, "Validation", f'A label named "{name}" already exists in this category.'
                )
                return False
        return True


class ConfigurationScreen(qt.QWidget):
    """Full-page widget where the user defines label categories before annotation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_confirm_callback = None

        outer_layout = qt.QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        outer_layout.addWidget(scroll)

        content = qt.QWidget()
        self._content_layout = qt.QVBoxLayout()
        self._content_layout.setSpacing(12)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        content.setLayout(self._content_layout)
        scroll.setWidget(content)

        # ------ Header ------
        header = qt.QLabel("Annotation Configuration")
        header.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 2px;")
        self._content_layout.addWidget(header)

        tagline = qt.QLabel("Define labels for each annotation category before you start annotating.")
        tagline.setStyleSheet("color: #666; margin-bottom: 8px;")
        self._content_layout.addWidget(tagline)

        # ------ Preset bar ------
        preset_group = qt.QGroupBox("Presets")
        preset_layout = qt.QHBoxLayout()
        preset_group.setLayout(preset_layout)

        self._preset_combo = qt.QComboBox()
        self._preset_combo.addItem("-- Select a Preset --")
        for name in PRESETS:
            self._preset_combo.addItem(name)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self._preset_combo)

        save_preset_btn = qt.QPushButton("Save as Preset")
        save_preset_btn.clicked.connect(self._on_save_preset)
        preset_layout.addWidget(save_preset_btn)

        import_btn = qt.QPushButton("Import from JSON")
        import_btn.clicked.connect(self._on_import_preset)
        preset_layout.addWidget(import_btn)

        self._content_layout.addWidget(preset_group)

        # ------ Three category sections ------
        self._class_section = LabelCategoryWidget(
            "Classification Labels",
            "Whole-scan labels (e.g. Normal / Pathological).",
        )
        self._content_layout.addWidget(self._class_section)

        self._roi_section = LabelCategoryWidget(
            "ROI Labels",
            "Region-of-interest labels drawn on slices.",
        )
        self._content_layout.addWidget(self._roi_section)

        self._seg_section = LabelCategoryWidget(
            "Segmentation Classes",
            "Voxel-level segmentation mask classes.",
        )
        self._content_layout.addWidget(self._seg_section)

        # ------ Confirm button ------
        self._confirm_btn = qt.QPushButton("Confirm && Begin Annotation")
        self._confirm_btn.setMinimumHeight(42)
        self._confirm_btn.setStyleSheet(
            "QPushButton { background-color: #1976D2; color: white; font-size: 15px;"
            " font-weight: bold; border: none; border-radius: 6px; padding: 8px 24px; }"
            " QPushButton:hover { background-color: #1565C0; }"
            " QPushButton:pressed { background-color: #0D47A1; }"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._content_layout.addWidget(self._confirm_btn)

        self._content_layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self):
        """Build and return a LabelConfig from the current state of all three sections."""
        return LabelConfig(
            class_labels=self._class_section.get_labels(),
            roi_labels=self._roi_section.get_labels(),
            segmentation_classes=self._seg_section.get_labels(),
        )

    def load_config(self, config):
        """Populate all three sections from a LabelConfig instance."""
        self._class_section.set_labels(config.class_labels)
        self._roi_section.set_labels(config.roi_labels)
        self._seg_section.set_labels(config.segmentation_classes)

    def set_confirm_callback(self, callback):
        """Register a callback invoked when the user confirms. Receives a LabelConfig."""
        self._on_confirm_callback = callback

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def _on_confirm(self):
        config = self.get_config()
        total = len(config.class_labels) + len(config.roi_labels) + len(config.segmentation_classes)
        if total == 0:
            qt.QMessageBox.warning(
                self,
                "No Labels",
                "Please add at least one label in any category before proceeding.",
            )
            return
        if self._on_confirm_callback:
            self._on_confirm_callback(config)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def _has_any_labels(self):
        config = self.get_config()
        return bool(config.class_labels or config.roi_labels or config.segmentation_classes)

    def _on_preset_selected(self, index):
        if index <= 0:
            return
        preset_name = self._preset_combo.itemText(index)
        if preset_name not in PRESETS:
            return

        if self._has_any_labels():
            reply = qt.QMessageBox.question(
                self,
                "Load Preset",
                "Loading a preset will replace all current labels. Continue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if reply != qt.QMessageBox.Yes:
                self._preset_combo.blockSignals(True)
                self._preset_combo.setCurrentIndex(0)
                self._preset_combo.blockSignals(False)
                return

        data = PRESETS[preset_name]
        config = LabelConfig.from_dict(data)
        self.load_config(config)

    def _on_save_preset(self):
        config = self.get_config()
        path = qt.QFileDialog.getSaveFileName(
            self, "Save Preset", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(config.to_dict(), f, indent=2)
            qt.QMessageBox.information(self, "Saved", f"Preset saved to:\n{path}")
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to save preset:\n{exc}")

    def _on_import_preset(self):
        path = qt.QFileDialog.getOpenFileName(
            self, "Import Preset", "", "JSON Files (*.json)"
        )
        if not path:
            return

        if self._has_any_labels():
            reply = qt.QMessageBox.question(
                self,
                "Import Preset",
                "Importing will replace all current labels. Continue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if reply != qt.QMessageBox.Yes:
                return

        try:
            with open(path, "r") as f:
                data = json.load(f)
            config = LabelConfig.from_dict(data)
            self.load_config(config)
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to import preset:\n{exc}")
