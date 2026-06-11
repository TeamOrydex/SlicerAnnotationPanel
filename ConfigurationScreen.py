import os
import qt
import json

from AnnotationModel import LabelDefinition, LabelConfig
from LabelColors import get_category_palette, next_available_color, normalize_hex_color, DEFAULT_LABEL_COLOR
from RadiologyTerms import (
    DEFAULT_ROI_DRAWING_TOOL,
    ROI_DRAWING_TOOLS,
    drawing_tool_display_name,
    normalize_drawing_tool,
)
from PresetStorage import (
    delete_preset,
    find_preset_name,
    get_presets_dir,
    is_preset_name_taken,
    list_preset_names,
    load_preset,
    normalize_preset_name,
    preset_name_key,
    save_preset,
    _qt_line_text,
)


class LabelCategoryWidget(qt.QGroupBox):
    """Reusable group-box that manages a table of label definitions for one category."""

    def __init__(self, title, subtitle, parent=None, include_drawing_tool=False, category_key="classification"):
        super().__init__(title, parent)
        self._subtitle = subtitle
        self._include_drawing_tool = include_drawing_tool
        self._category_key = category_key

        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        subtitle_label = qt.QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 4px;")
        layout.addWidget(subtitle_label)

        headers = ["Color", "Name", "Description"]
        if include_drawing_tool:
            headers.append("Drawing Tool")
        headers.append("Actions")
        self._table = qt.QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(2, qt.QHeaderView.Stretch)
        if include_drawing_tool:
            header.setSectionResizeMode(3, qt.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(4, qt.QHeaderView.ResizeToContents)
        else:
            header.setSectionResizeMode(3, qt.QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self._table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self._table.setMinimumHeight(120)
        layout.addWidget(self._table)

        btn_row = qt.QHBoxLayout()
        add_btn = qt.QPushButton("+ Add")
        add_btn.setStyleSheet(
            "QPushButton { color: #1976D2; background: transparent; border: 1px dashed #1976D2;"
            " border-radius: 4px; padding: 4px 12px; font-weight: bold; }"
            " QPushButton:hover { background: #E3F2FD; }"
        )
        add_btn.clicked.connect(self._add_label)
        btn_row.addWidget(add_btn)

        self._clear_labels_btn = qt.QPushButton("Clear Labels")
        self._clear_labels_btn.setStyleSheet(
            "QPushButton { color: #c62828; background: transparent; border: 1px solid #ef9a9a;"
            " border-radius: 4px; padding: 4px 12px; }"
            " QPushButton:hover { background: #FFEBEE; }"
        )
        self._clear_labels_btn.clicked.connect(self._on_clear_labels_clicked)
        btn_row.addWidget(self._clear_labels_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._clear_handler = None

    @property
    def _actions_col(self):
        return 4 if self._include_drawing_tool else 3

    @property
    def _tool_col(self):
        return 3

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
            stored_color = color_item.data(qt.Qt.UserRole) if color_item else ""
            drawing_tool = ""
            if self._include_drawing_tool:
                tool_item = self._table.item(row, self._tool_col)
                stored_tool = tool_item.data(qt.Qt.UserRole) if tool_item else ""
                drawing_tool = normalize_drawing_tool(stored_tool) or DEFAULT_ROI_DRAWING_TOOL
            labels.append(
                LabelDefinition(
                    id=label_id,
                    name=name_item.text() if name_item else "",
                    color=normalize_hex_color(stored_color) or DEFAULT_LABEL_COLOR,
                    description=desc_item.text() if desc_item else "",
                    drawing_tool=drawing_tool,
                )
            )
        return labels

    def set_labels(self, labels):
        """Clear the table and populate it from a list of LabelDefinition."""
        self._table.setRowCount(0)
        for lbl in labels:
            drawing_tool = ""
            if self._include_drawing_tool:
                drawing_tool = lbl.resolved_drawing_tool()
            self._insert_row(lbl.name, lbl.color, lbl.description, lbl.id, drawing_tool)

    def set_clear_handler(self, handler):
        """Register a callback invoked when the user clicks Clear Labels."""
        self._clear_handler = handler

    def clear_labels(self):
        """Remove every label row from this category table."""
        self._table.setRowCount(0)

    def _on_clear_labels_clicked(self):
        if self._clear_handler:
            self._clear_handler()
        else:
            self.clear_labels()

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _get_used_colors(self):
        colors = []
        for row in range(self._table.rowCount):
            color_item = self._table.item(row, 0)
            if color_item:
                stored = color_item.data(qt.Qt.UserRole)
                if stored:
                    colors.append(stored)
        return colors

    def _pick_default_color(self):
        return next_available_color(
            self._get_used_colors(),
            palette=get_category_palette(self._category_key),
        )

    def _insert_row(self, name, color, description, label_id="", drawing_tool=""):
        color = normalize_hex_color(color) or self._pick_default_color()
        if self._include_drawing_tool:
            drawing_tool = normalize_drawing_tool(drawing_tool) or DEFAULT_ROI_DRAWING_TOOL
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

        if self._include_drawing_tool:
            tool_item = qt.QTableWidgetItem(drawing_tool_display_name(drawing_tool))
            tool_item.setData(qt.Qt.UserRole, drawing_tool)
            tool_item.setFlags(tool_item.flags() & ~qt.Qt.ItemIsEditable)
            self._table.setItem(row, self._tool_col, tool_item)

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
        edit_btn.clicked.connect(lambda _checked=False, _r=row: self._edit_label(_r))
        actions_layout.addWidget(edit_btn)

        delete_btn = qt.QPushButton("\u2715")
        delete_btn.setToolTip("Delete")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; color: #c62828; }"
            " QPushButton:hover { background: #FFEBEE; border-radius: 4px; }"
        )
        delete_btn.clicked.connect(lambda _checked=False, _r=row: self._delete_label(_r))
        actions_layout.addWidget(delete_btn)

        self._table.setCellWidget(row, self._actions_col, actions_widget)

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
            edit_btn.clicked.connect(lambda _checked=False, _r=row: self._edit_label(_r))
            actions_layout.addWidget(edit_btn)

            delete_btn = qt.QPushButton("\u2715")
            delete_btn.setToolTip("Delete")
            delete_btn.setFixedSize(28, 28)
            delete_btn.setStyleSheet(
                "QPushButton { border: none; font-size: 14px; color: #c62828; }"
                " QPushButton:hover { background: #FFEBEE; border-radius: 4px; }"
            )
            delete_btn.clicked.connect(lambda _checked=False, _r=row: self._delete_label(_r))
            actions_layout.addWidget(delete_btn)

            self._table.setCellWidget(row, self._actions_col, actions_widget)

    # ------------------------------------------------------------------
    # Add / Edit / Delete
    # ------------------------------------------------------------------

    def _add_label(self):
        default_color = self._pick_default_color()
        default_tool = DEFAULT_ROI_DRAWING_TOOL if self._include_drawing_tool else ""
        result = self._open_label_dialog("Add Label", "", default_color, "", default_tool)
        if result is None:
            return
        if self._include_drawing_tool:
            name, color, description, drawing_tool = result
        else:
            name, color, description = result
            drawing_tool = ""
        if not self._validate_name(name):
            return
        self._insert_row(name, color, description, drawing_tool=drawing_tool)

    def _edit_label(self, row):
        if row < 0 or row >= self._table.rowCount:
            return
        old_name = self._table.item(row, 1).text()
        old_color = self._table.item(row, 0).data(qt.Qt.UserRole)
        old_desc = self._table.item(row, 2).text()
        old_tool = ""
        if self._include_drawing_tool:
            tool_item = self._table.item(row, self._tool_col)
            old_tool = tool_item.data(qt.Qt.UserRole) if tool_item else DEFAULT_ROI_DRAWING_TOOL

        result = self._open_label_dialog("Edit Label", old_name, old_color, old_desc, old_tool)
        if result is None:
            return
        if self._include_drawing_tool:
            name, color, description, drawing_tool = result
        else:
            name, color, description = result
            drawing_tool = ""
        if not self._validate_name(name, exclude_row=row):
            return

        self._table.item(row, 1).setText(name)
        self._table.item(row, 2).setText(description)
        color = normalize_hex_color(color) or normalize_hex_color(old_color) or DEFAULT_LABEL_COLOR
        color_item = self._table.item(row, 0)
        color_item.setBackground(qt.QColor(color))
        color_item.setData(qt.Qt.UserRole, color)
        if self._include_drawing_tool:
            tool_item = self._table.item(row, self._tool_col)
            drawing_tool = normalize_drawing_tool(drawing_tool) or DEFAULT_ROI_DRAWING_TOOL
            tool_item.setText(drawing_tool_display_name(drawing_tool))
            tool_item.setData(qt.Qt.UserRole, drawing_tool)

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

    def _open_label_dialog(self, title, name, color, description, drawing_tool=""):
        dialog = qt.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(340)

        layout = qt.QVBoxLayout(dialog)

        form_layout = qt.QFormLayout()
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

        tool_combo = None
        if self._include_drawing_tool:
            tool_combo = qt.QComboBox()
            selected_tool = normalize_drawing_tool(drawing_tool) or DEFAULT_ROI_DRAWING_TOOL
            selected_index = 0
            for index, (tool_id, display_name) in enumerate(ROI_DRAWING_TOOLS):
                tool_combo.addItem(display_name, tool_id)
                if tool_id == selected_tool:
                    selected_index = index
            tool_combo.setCurrentIndex(selected_index)
            form_layout.addRow("Drawing Tool:", tool_combo)

        layout.addLayout(form_layout)

        btn_box = qt.QDialogButtonBox()
        save_btn = btn_box.addButton("Save", qt.QDialogButtonBox.AcceptRole)
        cancel_btn = btn_box.addButton("Cancel", qt.QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec_() != qt.QDialog.Accepted:
            return None
        if self._include_drawing_tool and tool_combo is not None:
            tool_id = tool_combo.itemData(tool_combo.currentIndex)
            if callable(tool_id):
                tool_id = tool_id()
            return (
                name_edit.text.strip(),
                chosen_color["value"],
                desc_edit.text.strip(),
                normalize_drawing_tool(tool_id) or DEFAULT_ROI_DRAWING_TOOL,
            )
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
        self._preset_changed_callback = None
        self._current_preset_name = None

        outer_layout = qt.QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        outer_layout.addWidget(scroll)

        content = qt.QWidget()
        self._content_layout = qt.QVBoxLayout()
        self._content_layout.setSpacing(8)
        self._content_layout.setContentsMargins(6, 6, 6, 6)
        content.setLayout(self._content_layout)
        scroll.setWidget(content)

        # ------ Header ------
        header = qt.QLabel("Label Configuration")
        header.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 2px;")
        self._content_layout.addWidget(header)

        tagline = qt.QLabel(
            "Define annotation categories for classification, ROI, and segmentation."
        )
        tagline.setStyleSheet("color: #666; margin-bottom: 8px;")
        self._content_layout.addWidget(tagline)

        # ------ Preset bar ------
        preset_group = qt.QGroupBox("Presets")
        preset_group_layout = qt.QVBoxLayout()
        preset_group_layout.setContentsMargins(6, 4, 6, 4)
        preset_group_layout.setSpacing(6)
        preset_group.setLayout(preset_group_layout)

        preset_layout = qt.QHBoxLayout()
        preset_layout.setSpacing(6)

        self._preset_combo = qt.QComboBox()
        preset_layout.addWidget(self._preset_combo)

        save_preset_btn = qt.QPushButton("Save as Preset")
        save_preset_btn.clicked.connect(self._on_save_preset)
        preset_layout.addWidget(save_preset_btn)

        self._delete_preset_btn = qt.QPushButton("Delete Preset")
        self._delete_preset_btn.setEnabled(False)
        self._delete_preset_btn.setStyleSheet(
            "QPushButton { color: #c62828; }"
            " QPushButton:disabled { color: #bbb; }"
        )
        self._delete_preset_btn.clicked.connect(self._on_delete_preset)
        preset_layout.addWidget(self._delete_preset_btn)

        import_btn = qt.QPushButton("Import from JSON")
        import_btn.clicked.connect(self._on_import_preset)
        preset_layout.addWidget(import_btn)

        preset_group_layout.addLayout(preset_layout)

        clear_everything_row = qt.QHBoxLayout()
        clear_everything_row.addStretch()
        self._clear_everything_btn = qt.QPushButton("Clear Everything")
        self._clear_everything_btn.setStyleSheet(
            "QPushButton { color: #c62828; border: 1px solid #ef9a9a; border-radius: 4px;"
            " padding: 4px 12px; }"
            " QPushButton:hover { background: #FFEBEE; }"
        )
        self._clear_everything_btn.clicked.connect(self._on_clear_everything)
        clear_everything_row.addWidget(self._clear_everything_btn)
        preset_group_layout.addLayout(clear_everything_row)

        self._content_layout.addWidget(preset_group)

        # ------ Three category sections ------
        self._class_section = LabelCategoryWidget(
            "Classification Labels",
            "Slice-level classification labels (e.g. Normal / Abnormal).",
            category_key="classification",
        )
        self._class_section.set_clear_handler(
            lambda: self._clear_category_labels(
                self._class_section,
                "Remove all classification labels?",
            )
        )
        self._content_layout.addWidget(self._class_section)

        self._roi_section = LabelCategoryWidget(
            "ROI Categories",
            "Categories for regions of interest drawn on image slices.",
            include_drawing_tool=True,
            category_key="roi",
        )
        self._roi_section.set_clear_handler(
            lambda: self._clear_category_labels(
                self._roi_section,
                "Remove all ROI labels?",
            )
        )
        self._content_layout.addWidget(self._roi_section)

        self._seg_section = LabelCategoryWidget(
            "Segment Labels",
            "Voxel-level segment labels for segmentation.",
            category_key="segmentation",
        )
        self._seg_section.set_clear_handler(
            lambda: self._clear_category_labels(
                self._seg_section,
                "Remove all segmentation labels?",
            )
        )
        self._content_layout.addWidget(self._seg_section)

        # ------ Confirm button ------
        self._confirm_btn = qt.QPushButton("Confirm && Start Annotation")
        self._confirm_btn.setMinimumHeight(32)
        self._confirm_btn.setStyleSheet(
            "QPushButton { background-color: #1976D2; color: white; font-size: 14px;"
            " font-weight: bold; border: none; border-radius: 4px; padding: 4px 16px; }"
            " QPushButton:hover { background-color: #1565C0; }"
            " QPushButton:pressed { background-color: #0D47A1; }"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._content_layout.addWidget(self._confirm_btn)

        self._content_layout.addStretch()

        try:
            self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
            self._preset_combo.currentIndexChanged.connect(self._update_delete_preset_button)
            self._refresh_preset_combo()
            self._update_delete_preset_button()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Preset dropdown could not be initialized: %s", exc
            )

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

    def apply_imported_config(self, config, preset_name):
        """Load imported label configuration and register it as the active preset."""
        self._load_preset_config(config, preset_name)
        self._refresh_preset_combo(select_name=preset_name)

    def set_confirm_callback(self, callback):
        """Register a callback invoked when the user confirms. Receives a LabelConfig."""
        self._on_confirm_callback = callback

    def set_preset_changed_callback(self, callback):
        """Register a callback invoked when the active preset identity changes."""
        self._preset_changed_callback = callback

    def get_current_preset_name(self):
        return self._current_preset_name

    def set_current_preset_name(self, preset_name):
        self._current_preset_name = normalize_preset_name(preset_name) or None

    def _load_preset_config(self, config, preset_name):
        """Load label tables and notify when the preset identity changes."""
        old_name = self._current_preset_name
        new_name = normalize_preset_name(preset_name) or None
        self.load_config(config)
        if preset_name_key(old_name) != preset_name_key(new_name):
            self._current_preset_name = new_name
            if self._preset_changed_callback:
                self._preset_changed_callback(new_name, old_name)
        else:
            self._current_preset_name = new_name

    @staticmethod
    def _file_dialog_path(result):
        if isinstance(result, (tuple, list)):
            return result[0] if result else ""
        return result or ""

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
        if not self._is_configuration_saved_as_preset():
            qt.QMessageBox.warning(
                self,
                "Preset Required",
                "Please save your configuration as a preset before continuing.",
            )
            return
        if self._on_confirm_callback:
            self._on_confirm_callback(config)

    @staticmethod
    def _label_configs_equal(left, right):
        """True when two LabelConfig instances describe the same label definitions."""
        categories = [
            (left.class_labels, right.class_labels, False),
            (left.roi_labels, right.roi_labels, True),
            (left.segmentation_classes, right.segmentation_classes, False),
        ]
        for left_labels, right_labels, include_drawing_tool in categories:
            if len(left_labels) != len(right_labels):
                return False
            left_by_id = {lbl.id: lbl for lbl in left_labels}
            right_by_id = {lbl.id: lbl for lbl in right_labels}
            if set(left_by_id) != set(right_by_id):
                return False
            for label_id, left_label in left_by_id.items():
                right_label = right_by_id[label_id]
                if left_label.name != right_label.name:
                    return False
                if normalize_hex_color(left_label.color) != normalize_hex_color(right_label.color):
                    return False
                if left_label.description != right_label.description:
                    return False
                if include_drawing_tool and (
                    left_label.resolved_drawing_tool() != right_label.resolved_drawing_tool()
                ):
                    return False
        return True

    def _is_configuration_saved_as_preset(self):
        """True when the current tables match a preset saved on disk."""
        preset_name = self._current_preset_name
        if not preset_name or not find_preset_name(preset_name):
            return False
        try:
            saved_config = LabelConfig.from_dict(load_preset(preset_name))
        except FileNotFoundError:
            return False
        return self._label_configs_equal(self.get_config(), saved_config)

    def _clear_category_labels(self, section, message):
        reply = qt.QMessageBox.question(
            self,
            "Clear Labels",
            message,
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if reply != qt.QMessageBox.Yes:
            return
        section.clear_labels()

    def _on_clear_everything(self):
        reply = qt.QMessageBox.question(
            self,
            "Clear Everything",
            "This will remove all configured labels from all categories.\n\nContinue?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if reply != qt.QMessageBox.Yes:
            return
        self._class_section.clear_labels()
        self._roi_section.clear_labels()
        self._seg_section.clear_labels()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @staticmethod
    def _combo_current_text(combo):
        text = combo.currentText
        return text() if callable(text) else (text or "")

    def _refresh_preset_combo(self, select_name=None):
        self._preset_combo.blockSignals(True)
        previous = select_name or self._combo_current_text(self._preset_combo)
        self._preset_combo.clear()
        try:
            preset_names = list_preset_names()
        except Exception:
            preset_names = []
        for name in preset_names:
            self._preset_combo.addItem(name)
        if select_name:
            index = self._preset_combo.findText(select_name)
            if index >= 0:
                self._preset_combo.setCurrentIndex(index)
        elif previous:
            index = self._preset_combo.findText(previous)
            if index >= 0:
                self._preset_combo.setCurrentIndex(index)
            else:
                self._clear_preset_selection()
        elif self._preset_combo.count > 0:
            self._clear_preset_selection()
        self._preset_combo.blockSignals(False)
        self._update_delete_preset_button()

    def _update_delete_preset_button(self, _index=None):
        if not hasattr(self, "_delete_preset_btn"):
            return
        index = self._preset_combo.currentIndex
        if callable(index):
            index = index()
        enabled = index >= 0 and bool(self._combo_current_text(self._preset_combo))
        self._delete_preset_btn.setEnabled(enabled)

    def _clear_preset_selection(self):
        try:
            self._preset_combo.setCurrentIndex(-1)
        except Exception:
            pass

    def _has_any_labels(self):
        config = self.get_config()
        return bool(config.class_labels or config.roi_labels or config.segmentation_classes)

    def _on_preset_selected(self, index):
        if index < 0 or not hasattr(self, "_class_section"):
            return
        preset_name = self._preset_combo.itemText(index)
        if not preset_name:
            return

        if self._has_any_labels():
            reply = qt.QMessageBox.question(
                self,
                "Load Preset",
                f'Load preset "{preset_name}"?\n\n'
                "This replaces all labels in the configuration tables. "
                "Existing annotations will be cleared because label mappings "
                "from another preset are not compatible.",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if reply != qt.QMessageBox.Yes:
                self._clear_preset_selection()
                return

        try:
            data = load_preset(preset_name)
            config = LabelConfig.from_dict(data)
            display_name = data.get("preset_name") or preset_name
            self._load_preset_config(config, display_name)
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to load preset:\n{exc}")
            self._refresh_preset_combo()

    def _open_save_preset_dialog(self):
        presets_dir = get_presets_dir()

        while True:
            dialog = qt.QDialog(self)
            dialog.setWindowTitle("Save Preset")
            dialog.setMinimumWidth(360)

            layout = qt.QVBoxLayout(dialog)
            form_layout = qt.QFormLayout()
            name_edit = qt.QLineEdit()
            name_edit.setPlaceholderText("Required — must be unique")
            form_layout.addRow("Preset name:", name_edit)
            layout.addLayout(form_layout)

            hint = qt.QLabel(f"Presets are saved to:\n{presets_dir}")
            hint.setStyleSheet("color: #666; font-size: 11px;")
            hint.setWordWrap(True)
            layout.addWidget(hint)

            btn_box = qt.QDialogButtonBox()
            btn_box.addButton("Save", qt.QDialogButtonBox.AcceptRole)
            btn_box.addButton("Cancel", qt.QDialogButtonBox.RejectRole)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)

            if dialog.exec_() != qt.QDialog.Accepted:
                return None

            name = normalize_preset_name(_qt_line_text(name_edit))
            if not name:
                qt.QMessageBox.warning(self, "Validation", "Preset name is required.")
                continue
            if is_preset_name_taken(name):
                qt.QMessageBox.warning(
                    self,
                    "Validation",
                    f'A preset named "{name}" already exists. Choose a unique name.',
                )
                continue
            return name

    def _on_save_preset(self):
        config = self.get_config()
        if not self._has_any_labels():
            qt.QMessageBox.warning(
                self,
                "No Labels",
                "Add at least one label before saving a preset.",
            )
            return

        preset_name = self._open_save_preset_dialog()
        if not preset_name:
            return

        try:
            path = save_preset(preset_name, config.to_dict())
            saved_name = os.path.splitext(os.path.basename(path))[0]
            self._load_preset_config(config, saved_name)
            self._refresh_preset_combo(select_name=saved_name)
            qt.QMessageBox.information(
                self,
                "Saved",
                f'Preset "{preset_name}" saved to:\n{path}',
            )
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to save preset:\n{exc}")

    def _on_delete_preset(self):
        index = self._preset_combo.currentIndex
        if callable(index):
            index = index()
        if index < 0:
            return
        preset_name = self._preset_combo.itemText(index)
        if not preset_name:
            return

        reply = qt.QMessageBox.question(
            self,
            "Delete Preset",
            "Are you sure you want to delete the selected preset?\n\n"
            "This action cannot be undone.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if reply != qt.QMessageBox.Yes:
            return

        try:
            delete_preset(preset_name)
        except FileNotFoundError:
            qt.QMessageBox.warning(self, "Not Found", f'Preset "{preset_name}" was not found.')
            self._refresh_preset_combo()
            return
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to delete preset:\n{exc}")
            return

        if preset_name_key(self._current_preset_name) == preset_name_key(preset_name):
            self._current_preset_name = None

        self._refresh_preset_combo()
        self._clear_preset_selection()
        qt.QMessageBox.information(self, "Deleted", f'Preset "{preset_name}" was deleted.')

    def _on_import_preset(self):
        path = self._file_dialog_path(
            qt.QFileDialog.getOpenFileName(
                self, "Import Preset", "", "JSON Files (*.json)"
            )
        )
        if not path:
            return

        if self._has_any_labels():
            reply = qt.QMessageBox.question(
                self,
                "Import Preset",
                "Importing will replace all labels in the configuration tables. "
                "Existing annotations will be cleared because label mappings "
                "from another preset are not compatible.\n\nContinue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if reply != qt.QMessageBox.Yes:
                return

        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            config = LabelConfig.from_dict(data)
            display_name = data.get("preset_name") or os.path.splitext(os.path.basename(path))[0]
            self._load_preset_config(config, display_name)
        except Exception as exc:
            qt.QMessageBox.critical(self, "Error", f"Failed to import preset:\n{exc}")
