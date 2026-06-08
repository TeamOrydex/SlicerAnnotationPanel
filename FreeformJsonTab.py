"""
Freeform JSON metadata tab: structured form builder and raw JSON editor.
Allows annotators to attach arbitrary key-value data to an annotation.
"""
import qt
import json

TEMPLATES = {
    "Radiology Findings": {
        "finding_type": "",
        "location": "",
        "size_mm": 0,
        "confidence": "",
        "notes": "",
    },
    "Pathology Report": {
        "tissue_type": "",
        "grade": "",
        "margins": "",
        "lymph_nodes_examined": 0,
        "lymph_nodes_positive": 0,
        "notes": "",
    },
}

FIELD_TYPES = ["String", "Text", "Number", "Boolean", "Object", "Array"]
ARRAY_ITEM_TYPES = ["String", "Number", "Boolean"]
MAX_NESTING_DEPTH = 3


class FieldRowWidget(qt.QFrame):
    """A single key-value field row in the form builder."""

    def __init__(self, parent_list, depth=0, parent=None):
        super().__init__(parent)
        self._parent_list = parent_list
        self._depth = depth
        self._value_widget = None
        self._nested_widget = None
        self._array_widget = None
        self.setFrameShape(qt.QFrame.StyledPanel)
        self.setStyleSheet("FieldRowWidget { margin: 2px; padding: 4px; }")
        self._setup_ui()

    def _setup_ui(self):
        self._layout = qt.QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(4)

        top_row = qt.QHBoxLayout()

        top_row.addWidget(qt.QLabel("Key:"))
        self._key_edit = qt.QLineEdit()
        self._key_edit.setPlaceholderText("field_name")
        self._key_edit.setMaximumWidth(200)
        top_row.addWidget(self._key_edit)

        top_row.addWidget(qt.QLabel("Type:"))
        self._type_combo = qt.QComboBox()
        available_types = list(FIELD_TYPES)
        if self._depth >= MAX_NESTING_DEPTH:
            available_types = [t for t in available_types if t not in ("Object", "Array")]
        for t in available_types:
            self._type_combo.addItem(t)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_row.addWidget(self._type_combo)

        top_row.addStretch()

        self._delete_btn = qt.QPushButton("\u2715")
        self._delete_btn.setFixedSize(24, 24)
        self._delete_btn.setToolTip("Remove this field")
        self._delete_btn.clicked.connect(self._on_delete)
        top_row.addWidget(self._delete_btn)

        self._layout.addLayout(top_row)

        self._value_container = qt.QVBoxLayout()
        self._layout.addLayout(self._value_container)

        self._create_value_widget("String")

    def _on_type_changed(self, index):
        new_type = self._type_combo.currentText

        has_content = False
        if self._value_widget:
            if hasattr(self._value_widget, 'text') and self._value_widget.text:
                has_content = True
            elif hasattr(self._value_widget, 'toPlainText') and self._value_widget.toPlainText():
                has_content = True

        if has_content:
            result = qt.QMessageBox.question(
                self, "Change Type",
                "Changing the type will clear the current value. Continue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if result != qt.QMessageBox.Yes:
                self._type_combo.blockSignals(True)
                self._type_combo.setCurrentText(self._get_current_type_for_widget())
                self._type_combo.blockSignals(False)
                return

        self._clear_value_widget()
        self._create_value_widget(new_type)

    def _get_current_type_for_widget(self):
        if self._nested_widget:
            return "Object"
        if self._array_widget:
            return "Array"
        if self._value_widget:
            if isinstance(self._value_widget, qt.QCheckBox):
                return "Boolean"
            if isinstance(self._value_widget, qt.QTextEdit):
                return "Text"
        return "String"

    def _clear_value_widget(self):
        if self._value_widget:
            self._value_widget.setParent(None)
            self._value_widget.deleteLater()
            self._value_widget = None
        if self._nested_widget:
            self._nested_widget.setParent(None)
            self._nested_widget.deleteLater()
            self._nested_widget = None
        if self._array_widget:
            self._array_widget.setParent(None)
            self._array_widget.deleteLater()
            self._array_widget = None

    def _create_value_widget(self, type_name):
        if type_name == "String":
            w = qt.QLineEdit()
            w.setPlaceholderText("value")
            self._value_container.addWidget(w)
            self._value_widget = w

        elif type_name == "Text":
            w = qt.QTextEdit()
            w.setPlaceholderText("Multi-line text...")
            w.setMaximumHeight(80)
            self._value_container.addWidget(w)
            self._value_widget = w

        elif type_name == "Number":
            w = qt.QLineEdit()
            w.setPlaceholderText("0")
            validator = qt.QDoubleValidator()
            w.setValidator(validator)
            self._value_container.addWidget(w)
            self._value_widget = w

        elif type_name == "Boolean":
            w = qt.QCheckBox("True / False")
            self._value_container.addWidget(w)
            self._value_widget = w

        elif type_name == "Object":
            self._nested_widget = NestedFieldList(depth=self._depth + 1)
            self._value_container.addWidget(self._nested_widget)

        elif type_name == "Array":
            self._array_widget = ArrayFieldWidget(depth=self._depth)
            self._value_container.addWidget(self._array_widget)

    def _on_delete(self):
        self._parent_list.remove_field(self)

    # ─── Public API ──────────────────────────────────────────────────────

    def get_key(self):
        return self._key_edit.text.strip()

    def set_key(self, key):
        self._key_edit.setText(key)

    def get_type(self):
        return self._type_combo.currentText

    def set_type(self, type_name):
        self._type_combo.setCurrentText(type_name)

    def get_string_value(self):
        if self._value_widget and hasattr(self._value_widget, 'text'):
            return self._value_widget.text
        return ""

    def set_string_value(self, val):
        if self._value_widget and hasattr(self._value_widget, 'setText'):
            self._value_widget.setText(str(val))

    def get_text_value(self):
        if self._value_widget and hasattr(self._value_widget, 'toPlainText'):
            return self._value_widget.toPlainText()
        return ""

    def set_text_value(self, val):
        if self._value_widget and hasattr(self._value_widget, 'setPlainText'):
            self._value_widget.setPlainText(str(val))

    def get_number_value(self):
        if self._value_widget and hasattr(self._value_widget, 'text'):
            text = self._value_widget.text.strip()
            if not text:
                return 0
            try:
                if '.' in text:
                    return float(text)
                return int(text)
            except ValueError:
                return 0
        return 0

    def set_number_value(self, val):
        if self._value_widget and hasattr(self._value_widget, 'setText'):
            if isinstance(val, float) and val == int(val):
                self._value_widget.setText(str(int(val)))
            else:
                self._value_widget.setText(str(val))

    def get_bool_value(self):
        if self._value_widget and isinstance(self._value_widget, qt.QCheckBox):
            return self._value_widget.isChecked()
        return False

    def set_bool_value(self, val):
        if self._value_widget and isinstance(self._value_widget, qt.QCheckBox):
            self._value_widget.setChecked(bool(val))

    def get_nested_widget(self):
        return self._nested_widget

    def get_array_values(self):
        if self._array_widget:
            return self._array_widget.get_values()
        return []

    def load_array(self, values):
        if self._array_widget:
            self._array_widget.load_values(values)

    def set_read_only(self, enabled):
        self._key_edit.setReadOnly(enabled)
        self._delete_btn.setVisible(not enabled)
        self._type_combo.setEnabled(not enabled)

        if self._value_widget:
            if isinstance(self._value_widget, qt.QCheckBox):
                self._value_widget.setEnabled(not enabled)
            elif hasattr(self._value_widget, 'setReadOnly'):
                self._value_widget.setReadOnly(enabled)

        if self._nested_widget:
            self._nested_widget.set_read_only(enabled)

        if self._array_widget:
            self._array_widget.set_read_only(enabled)


class ArrayFieldWidget(qt.QFrame):
    """Widget for editing a typed array of simple values."""

    def __init__(self, depth=0, parent=None):
        super().__init__(parent)
        self._items = []
        self._read_only = False
        self.setFrameShape(qt.QFrame.Box)
        self._setup_ui()

    def _setup_ui(self):
        self._layout = qt.QVBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(2)

        type_row = qt.QHBoxLayout()
        type_row.addWidget(qt.QLabel("Array of:"))
        self._item_type_combo = qt.QComboBox()
        for t in ARRAY_ITEM_TYPES:
            self._item_type_combo.addItem(t)
        type_row.addWidget(self._item_type_combo)
        type_row.addStretch()
        self._layout.addLayout(type_row)

        self._items_layout = qt.QVBoxLayout()
        self._layout.addLayout(self._items_layout)

        self._add_item_btn = qt.QPushButton("+ Add Item")
        self._add_item_btn.clicked.connect(self._on_add_item)
        self._layout.addWidget(self._add_item_btn)

    def _on_add_item(self):
        self._add_item_row("")

    def _add_item_row(self, value):
        item_type = self._item_type_combo.currentText
        row_widget = qt.QWidget()
        row_layout = qt.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        if item_type == "Boolean":
            val_widget = qt.QCheckBox("True / False")
            if isinstance(value, bool):
                val_widget.setChecked(value)
            row_layout.addWidget(val_widget)
        else:
            val_widget = qt.QLineEdit()
            if item_type == "Number":
                val_widget.setValidator(qt.QDoubleValidator())
            val_widget.setText(str(value) if value != "" else "")
            row_layout.addWidget(val_widget)

        del_btn = qt.QPushButton("\u2715")
        del_btn.setFixedSize(20, 20)
        del_btn.clicked.connect(lambda checked, w=row_widget: self._remove_item(w))
        if self._read_only:
            del_btn.hide()
        row_layout.addWidget(del_btn)

        self._items_layout.addWidget(row_widget)
        self._items.append((row_widget, val_widget, del_btn))

        if self._read_only:
            if isinstance(val_widget, qt.QCheckBox):
                val_widget.setEnabled(False)
            else:
                val_widget.setReadOnly(True)

    def _remove_item(self, widget):
        self._items = [(w, v, d) for w, v, d in self._items if w != widget]
        widget.setParent(None)
        widget.deleteLater()

    def get_values(self):
        item_type = self._item_type_combo.currentText
        values = []
        for _, val_widget, _ in self._items:
            if item_type == "Boolean":
                values.append(val_widget.isChecked())
            elif item_type == "Number":
                text = val_widget.text.strip()
                if not text:
                    values.append(0)
                elif '.' in text:
                    try:
                        values.append(float(text))
                    except ValueError:
                        values.append(0)
                else:
                    try:
                        values.append(int(text))
                    except ValueError:
                        values.append(0)
            else:
                values.append(val_widget.text)
        return values

    def load_values(self, values):
        for w, _, _ in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items = []

        if not values:
            return

        # Infer array item type from values
        sample = values[0]
        if isinstance(sample, bool):
            self._item_type_combo.setCurrentText("Boolean")
        elif isinstance(sample, (int, float)):
            self._item_type_combo.setCurrentText("Number")
        else:
            self._item_type_combo.setCurrentText("String")

        for val in values:
            self._add_item_row(val)

    def set_read_only(self, enabled):
        self._read_only = enabled
        self._add_item_btn.setVisible(not enabled)
        self._item_type_combo.setEnabled(not enabled)
        for _, val_widget, del_btn in self._items:
            del_btn.setVisible(not enabled)
            if isinstance(val_widget, qt.QCheckBox):
                val_widget.setEnabled(not enabled)
            elif hasattr(val_widget, 'setReadOnly'):
                val_widget.setReadOnly(enabled)


class NestedFieldList(qt.QFrame):
    """A container for nested field rows (used by Object type and as top-level)."""

    def __init__(self, depth=0, parent=None):
        super().__init__(parent)
        self._depth = depth
        self._field_rows = []
        self._read_only = False
        if depth > 0:
            self.setFrameShape(qt.QFrame.Box)
            self.setStyleSheet("NestedFieldList { margin-left: 12px; }")
        self._setup_ui()

    def _setup_ui(self):
        self._layout = qt.QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)

        self._fields_layout = qt.QVBoxLayout()
        self._layout.addLayout(self._fields_layout)

        self._add_btn = qt.QPushButton("+ Add Field" if self._depth == 0 else "+ Add Nested Field")
        self._add_btn.clicked.connect(self._on_add_field)
        self._layout.addWidget(self._add_btn)

    def _on_add_field(self):
        self.add_field("", "String")

    def add_field(self, key, type_name):
        row = FieldRowWidget(parent_list=self, depth=self._depth)
        if key:
            row.set_key(key)
        row._type_combo.blockSignals(True)
        row.set_type(type_name)
        row._type_combo.blockSignals(False)
        row._clear_value_widget()
        row._create_value_widget(type_name)
        self._fields_layout.addWidget(row)
        self._field_rows.append(row)
        if self._read_only:
            row.set_read_only(True)
        return row

    def remove_field(self, row):
        if row in self._field_rows:
            self._field_rows.remove(row)
            row.setParent(None)
            row.deleteLater()

    def clear_all(self):
        for row in list(self._field_rows):
            row.setParent(None)
            row.deleteLater()
        self._field_rows = []

    def build_dict(self):
        result = {}
        for row in self._field_rows:
            key = row.get_key()
            if not key:
                continue
            value_type = row.get_type()
            if value_type == "String":
                result[key] = row.get_string_value()
            elif value_type == "Text":
                result[key] = row.get_text_value()
            elif value_type == "Number":
                result[key] = row.get_number_value()
            elif value_type == "Boolean":
                result[key] = row.get_bool_value()
            elif value_type == "Object":
                nested = row.get_nested_widget()
                if nested:
                    result[key] = nested.build_dict()
                else:
                    result[key] = {}
            elif value_type == "Array":
                result[key] = row.get_array_values()
        return result

    def load_dict(self, data):
        self.clear_all()
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if isinstance(value, dict):
                row = self.add_field(key, "Object")
                nested = row.get_nested_widget()
                if nested:
                    nested.load_dict(value)
            elif isinstance(value, list):
                row = self.add_field(key, "Array")
                row.load_array(value)
            elif isinstance(value, bool):
                row = self.add_field(key, "Boolean")
                row.set_bool_value(value)
            elif isinstance(value, (int, float)):
                row = self.add_field(key, "Number")
                row.set_number_value(value)
            else:
                text = str(value)
                if "\n" in text or len(text) > 200:
                    row = self.add_field(key, "Text")
                    row.set_text_value(text)
                else:
                    row = self.add_field(key, "String")
                    row.set_string_value(text)

    def get_field_count(self):
        return len(self._field_rows)

    def set_read_only(self, enabled):
        self._read_only = enabled
        self._add_btn.setVisible(not enabled)
        for row in self._field_rows:
            row.set_read_only(enabled)


class FreeformJsonTab(qt.QWidget):
    """Freeform JSON tab with dual-view: structured form and raw JSON editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._read_only = False
        self._validation_timer = None
        self._setup_ui()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)
        layout.setSpacing(6)

        self._build_view_toggle(layout)
        self._build_template_selector(layout)
        self._build_form_view(layout)
        self._build_raw_json_view(layout)
        self._build_bottom_bar(layout)

        self._show_form_view()

    def _build_view_toggle(self, parent_layout):
        toggle_row = qt.QHBoxLayout()
        self._view_group = qt.QButtonGroup(self)
        self._form_radio = qt.QRadioButton("Form View")
        self._raw_radio = qt.QRadioButton("Raw JSON")
        self._form_radio.setChecked(True)
        self._view_group.addButton(self._form_radio, 0)
        self._view_group.addButton(self._raw_radio, 1)
        self._form_radio.toggled.connect(self._on_view_toggled)
        toggle_row.addWidget(self._form_radio)
        toggle_row.addWidget(self._raw_radio)
        toggle_row.addStretch()
        parent_layout.addLayout(toggle_row)

    def _build_template_selector(self, parent_layout):
        self._template_row = qt.QHBoxLayout()
        self._template_row_widget = qt.QWidget()
        row_layout = qt.QHBoxLayout(self._template_row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        row_layout.addWidget(qt.QLabel("Load Template:"))
        self._template_combo = qt.QComboBox()
        self._template_combo.addItem("(No template)")
        for name in TEMPLATES:
            self._template_combo.addItem(name)
        self._template_combo.addItem("Custom (from file)...")
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        row_layout.addWidget(self._template_combo)
        row_layout.addStretch()

        parent_layout.addWidget(self._template_row_widget)

    def _build_form_view(self, parent_layout):
        self._form_scroll = qt.QScrollArea()
        self._form_scroll.setWidgetResizable(True)

        self._field_list = NestedFieldList(depth=0)
        self._form_scroll.setWidget(self._field_list)
        parent_layout.addWidget(self._form_scroll)

    def _build_raw_json_view(self, parent_layout):
        self._raw_container = qt.QWidget()
        raw_layout = qt.QVBoxLayout(self._raw_container)
        raw_layout.setContentsMargins(0, 0, 0, 0)

        self._json_editor = qt.QPlainTextEdit()
        font = qt.QFont("Courier New", 10)
        self._json_editor.setFont(font)
        self._json_editor.setPlaceholderText('{\n  "key": "value"\n}')
        self._json_editor.textChanged.connect(self._on_json_text_changed)
        raw_layout.addWidget(self._json_editor)

        self._validation_label = qt.QLabel("\u2713 Valid JSON")
        self._validation_label.setStyleSheet("color: green;")
        raw_layout.addWidget(self._validation_label)

        parent_layout.addWidget(self._raw_container)

    def _build_bottom_bar(self, parent_layout):
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        parent_layout.addWidget(separator)

        btn_row = qt.QHBoxLayout()

        self._load_file_btn = qt.QPushButton("Load from File")
        self._load_file_btn.clicked.connect(self._on_load_file)
        btn_row.addWidget(self._load_file_btn)

        self._export_file_btn = qt.QPushButton("Export to File")
        self._export_file_btn.clicked.connect(self._on_export_file)
        btn_row.addWidget(self._export_file_btn)

        self._clear_btn = qt.QPushButton("Clear All")
        self._clear_btn.clicked.connect(self._on_clear_all)
        btn_row.addWidget(self._clear_btn)

        btn_row.addStretch()

        self._field_count_label = qt.QLabel("Field count: 0")
        btn_row.addWidget(self._field_count_label)

        parent_layout.addLayout(btn_row)

    # ─── View Switching ──────────────────────────────────────────────────

    def _on_view_toggled(self, checked):
        if self._form_radio.isChecked():
            self._switch_to_form_view()
        else:
            self._switch_to_raw_view()

    def _switch_to_form_view(self):
        """Switch from raw JSON to form view, syncing data."""
        if self._raw_container.isVisible():
            text = self._json_editor.toPlainText().strip()
            if text:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        self._field_list.load_dict(data)
                except json.JSONDecodeError as e:
                    result = qt.QMessageBox.question(
                        self, "Invalid JSON",
                        f"The JSON has errors (line {e.lineno}): {e.msg}\n\n"
                        "Switch to Form View anyway? (Invalid data will be discarded)",
                        qt.QMessageBox.Yes | qt.QMessageBox.No,
                    )
                    if result != qt.QMessageBox.Yes:
                        self._raw_radio.setChecked(True)
                        return
        self._show_form_view()

    def _switch_to_raw_view(self):
        """Switch from form to raw JSON view, syncing data."""
        data = self._field_list.build_dict()
        self._json_editor.setPlainText(json.dumps(data, indent=2))
        self._show_raw_view()

    def _show_form_view(self):
        self._form_scroll.show()
        self._template_row_widget.show()
        self._raw_container.hide()
        self._update_field_count()

    def _show_raw_view(self):
        self._form_scroll.hide()
        self._template_row_widget.hide()
        self._raw_container.show()

    # ─── JSON Validation ─────────────────────────────────────────────────

    def _on_json_text_changed(self):
        qt.QTimer.singleShot(500, self._validate_json)

    def _validate_json(self):
        text = self._json_editor.toPlainText().strip()
        if not text:
            self._validation_label.setText("\u2713 Valid JSON (empty)")
            self._validation_label.setStyleSheet("color: green;")
            return
        try:
            json.loads(text)
            self._validation_label.setText("\u2713 Valid JSON")
            self._validation_label.setStyleSheet("color: green;")
        except json.JSONDecodeError as e:
            self._validation_label.setText(
                f"\u2717 Invalid JSON (line {e.lineno}): {e.msg}"
            )
            self._validation_label.setStyleSheet("color: red;")

    # ─── Templates ───────────────────────────────────────────────────────

    def _on_template_selected(self, index):
        text = self._template_combo.currentText
        if text == "(No template)":
            return

        if text == "Custom (from file)...":
            self._template_combo.blockSignals(True)
            self._template_combo.setCurrentIndex(0)
            self._template_combo.blockSignals(False)
            filepath = qt.QFileDialog.getOpenFileName(
                self, "Load Template", "", "JSON Files (*.json)"
            )
            if not filepath:
                return
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                qt.QMessageBox.critical(self, "Error", f"Failed to load template: {e}")
                return
            if not isinstance(data, dict):
                qt.QMessageBox.critical(self, "Error", "Template must be a JSON object.")
                return
            self._apply_template(data)
            return

        template_data = TEMPLATES.get(text)
        if template_data:
            self._template_combo.blockSignals(True)
            self._template_combo.setCurrentIndex(0)
            self._template_combo.blockSignals(False)
            self._apply_template(template_data)

    def _apply_template(self, data):
        if self._field_list.get_field_count() > 0:
            result = qt.QMessageBox.question(
                self, "Load Template",
                "Loading a template will replace all existing fields. Continue?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
            )
            if result != qt.QMessageBox.Yes:
                return
        self._field_list.load_dict(data)
        self._update_field_count()

    # ─── Bottom Bar Actions ──────────────────────────────────────────────

    def _on_load_file(self):
        filepath = qt.QFileDialog.getOpenFileName(
            self, "Load JSON Data", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            qt.QMessageBox.critical(
                self, "Parse Error", f"Invalid JSON: {e}"
            )
            return
        except IOError as e:
            qt.QMessageBox.critical(self, "File Error", str(e))
            return

        if not isinstance(data, dict):
            qt.QMessageBox.critical(
                self, "Error", "Top-level JSON must be an object (dict)."
            )
            return

        self._field_list.load_dict(data)
        if self._raw_radio.isChecked():
            self._json_editor.setPlainText(json.dumps(data, indent=2))
        self._update_field_count()

    def _on_export_file(self):
        data = self.get_data()
        filepath = qt.QFileDialog.getSaveFileName(
            self, "Export JSON Data", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            qt.QMessageBox.critical(self, "File Error", str(e))

    def _on_clear_all(self):
        result = qt.QMessageBox.question(
            self, "Clear All",
            "Remove all fields? This cannot be undone.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if result == qt.QMessageBox.Yes:
            self._field_list.clear_all()
            if self._raw_radio.isChecked():
                self._json_editor.setPlainText("{}")
            self._update_field_count()

    def _update_field_count(self):
        count = self._field_list.get_field_count()
        self._field_count_label.setText(f"Field count: {count}")

    # ─── Public API ──────────────────────────────────────────────────────

    def get_data(self):
        """Return the current freeform data as a Python dict."""
        if self._raw_radio.isChecked():
            text = self._json_editor.toPlainText().strip()
            if text:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
        return self._field_list.build_dict()

    def load_data(self, data):
        """Load a dict into the form (and raw editor)."""
        if not isinstance(data, dict):
            data = {}
        self._field_list.load_dict(data)
        if self._raw_radio.isChecked():
            self._json_editor.setPlainText(json.dumps(data, indent=2))
        self._update_field_count()

    def set_read_only(self, enabled):
        """Toggle read-only mode for reviewer workflow."""
        self._read_only = enabled
        self._field_list.set_read_only(enabled)
        self._json_editor.setReadOnly(enabled)
        self._load_file_btn.setEnabled(not enabled)
        self._clear_btn.setEnabled(not enabled)
        self._template_combo.setEnabled(not enabled)
        # Export remains enabled for reviewers

    def cleanup(self):
        """Nothing to clean up for this tab."""
        pass
