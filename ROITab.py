"""
ROI (Region of Interest) annotation tab.
Wraps Slicer's vtkMRMLMarkups infrastructure to let annotators draw
geometric shapes on slices and assign class labels to each shape.
"""
import qt
import slicer
import logging
from datetime import datetime, timezone

from AnnotationModel import ROIAnnotation

logger = logging.getLogger(__name__)

# Maps ROI type names to their Slicer MRML node class names.
# Checked at runtime; unavailable types get their button disabled.
MARKUP_NODE_CLASSES = {
    "ellipse": "vtkMRMLMarkupsClosedCurveNode",
    "rectangle": "vtkMRMLMarkupsROINode",
    "polygon": "vtkMRMLMarkupsClosedCurveNode",
    "freehand_curve": "vtkMRMLMarkupsCurveNode",
    "line": "vtkMRMLMarkupsLineNode",
}

DEFAULT_ROI_LABELS = [
    "Normal",
    "Pathological",
    "Artifact",
    "Motion Blur",
    "Incomplete Coverage",
]


def hex_to_rgb_float(hex_color):
    """Convert '#rrggbb' to (r, g, b) floats in [0, 1]."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def rgb_float_to_hex(r, g, b):
    """Convert (r, g, b) floats in [0, 1] to '#rrggbb'."""
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))




class ROITab(qt.QWidget):
    """
    ROI annotation tab: tool bar, label/color picker, ROI list table, and actions.
    Acts as a controller over Slicer's Markups nodes.
    """

    def __init__(self, annotation_record=None, labels=None, parent=None):
        super().__init__(parent)
        self._record = annotation_record
        self._labels = list(labels) if labels else list(DEFAULT_ROI_LABELS)
        self._roi_annotations = []  # List[ROIAnnotation]
        self._read_only = False
        self._current_color = "#ff0000"
        self._active_tool = None
        self._observers = []  # (subject, tag) pairs for cleanup
        self._node_observers = {}  # node_id -> [(subject, tag), ...]
        self._available_tools = {}
        self._placement_node = None

        self._setup_ui()
        self._check_available_tools()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._build_toolbar(layout)
        self._build_label_section(layout)
        self._build_roi_table(layout)
        self._build_actions(layout)

    def _build_toolbar(self, parent_layout):
        toolbar_frame = qt.QFrame()
        toolbar_frame.setFrameShape(qt.QFrame.StyledPanel)
        toolbar_layout = qt.QVBoxLayout(toolbar_frame)

        heading = qt.QLabel("Drawing Tools")
        heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        toolbar_layout.addWidget(heading)

        btn_row = qt.QHBoxLayout()
        self._tool_group = qt.QButtonGroup(self)
        self._tool_group.setExclusive(False)

        self._tool_buttons = {}
        tool_names = [
            ("ellipse", "Ellipse"),
            ("rectangle", "Rectangle"),
            ("polygon", "Polygon"),
            ("freehand_curve", "Freehand"),
            ("line", "Line"),
        ]

        for tool_id, display_name in tool_names:
            btn = qt.QPushButton(display_name)
            btn.setCheckable(True)
            btn.setProperty("tool_id", tool_id)
            btn.setStyleSheet(
                "QPushButton { padding: 6px 12px; }"
                "QPushButton:checked { background-color: #2196F3; color: white; }"
            )
            btn.toggled.connect(lambda checked, tid=tool_id: self._on_tool_toggled(tid, checked))
            btn_row.addWidget(btn)
            self._tool_buttons[tool_id] = btn
            self._tool_group.addButton(btn)

        btn_row.addStretch()
        toolbar_layout.addLayout(btn_row)
        parent_layout.addWidget(toolbar_frame)

    def _build_label_section(self, parent_layout):
        label_frame = qt.QFrame()
        label_frame.setFrameShape(qt.QFrame.StyledPanel)
        label_layout = qt.QVBoxLayout(label_frame)

        row1 = qt.QHBoxLayout()
        row1.addWidget(qt.QLabel("Label for next ROI:"))
        self._label_combo = qt.QComboBox()
        self._label_combo.addItem("(No label)")
        for lbl in self._labels:
            self._label_combo.addItem(lbl)
        row1.addWidget(self._label_combo)
        row1.addStretch()
        label_layout.addLayout(row1)

        row2 = qt.QHBoxLayout()
        row2.addWidget(qt.QLabel("Color:"))
        self._color_btn = qt.QPushButton("")
        self._color_btn.setFixedSize(32, 24)
        self._color_btn.setStyleSheet(
            f"background-color: {self._current_color}; border: 1px solid #333;"
        )
        self._color_btn.clicked.connect(self._on_pick_color)
        row2.addWidget(self._color_btn)
        row2.addStretch()
        label_layout.addLayout(row2)

        parent_layout.addWidget(label_frame)

    def _build_roi_table(self, parent_layout):
        self._table = qt.QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["#", "Type", "Label", "Color", "Slice", "Actions"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(qt.QTableWidget.SelectRows)
        self._table.setSelectionMode(qt.QTableWidget.SingleSelection)
        self._table.setEditTriggers(qt.QTableWidget.NoEditTriggers)
        self._table.cellClicked.connect(self._on_table_row_clicked)
        parent_layout.addWidget(self._table)

    def _build_actions(self, parent_layout):
        action_row = qt.QHBoxLayout()

        self._delete_all_btn = qt.QPushButton("Delete All ROIs")
        self._delete_all_btn.clicked.connect(self._on_delete_all)
        action_row.addWidget(self._delete_all_btn)

        self._export_btn = qt.QPushButton("Export ROIs to JSON")
        self._export_btn.clicked.connect(self._on_export_json)
        action_row.addWidget(self._export_btn)

        action_row.addStretch()

        self._count_label = qt.QLabel("ROI count: 0")
        action_row.addWidget(self._count_label)

        parent_layout.addLayout(action_row)

    # ─── Tool Availability ───────────────────────────────────────────────

    def _check_available_tools(self):
        """Verify which markup node classes are available in this Slicer version."""
        for tool_id, class_name in MARKUP_NODE_CLASSES.items():
            try:
                node = slicer.mrmlScene.CreateNodeByClass(class_name)
                if node:
                    self._available_tools[tool_id] = True
                    node.UnRegister(None)
                else:
                    self._available_tools[tool_id] = False
                    self._tool_buttons[tool_id].setEnabled(False)
                    self._tool_buttons[tool_id].setToolTip("Not available in this Slicer version")
            except Exception:
                self._available_tools[tool_id] = False
                self._tool_buttons[tool_id].setEnabled(False)
                self._tool_buttons[tool_id].setToolTip("Not available in this Slicer version")
                logger.warning(f"Markup class {class_name} not available for tool '{tool_id}'")

    # ─── Tool Activation ─────────────────────────────────────────────────

    def _on_tool_toggled(self, tool_id, checked):
        if checked:
            # Finalize any pending placement from the previous tool
            self._deactivate_tool()
            # Uncheck other buttons
            for tid, btn in self._tool_buttons.items():
                if tid != tool_id:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            self._activate_tool(tool_id)
        else:
            self._deactivate_tool()

    def _activate_tool(self, tool_id):
        """Create a markup node and enter placement mode."""
        if not self._available_tools.get(tool_id, False):
            return

        self._active_tool = tool_id
        class_name = MARKUP_NODE_CLASSES[tool_id]

        node = slicer.mrmlScene.AddNewNodeByClass(class_name)
        if not node:
            logger.error(f"Failed to create node of class {class_name}")
            return

        # Configure the node
        selected_label = self._get_selected_label()
        node.SetName(f"ROI_{selected_label}_{tool_id}" if selected_label else f"ROI_{tool_id}")

        # Set color on display node
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(self._current_color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)

        self._placement_node = node

        # Observe the node for placement completion
        self._add_node_observer(
            node,
            slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
            self._on_point_placed,
        )

        # Enter placement mode
        selection_node = slicer.app.applicationLogic().GetSelectionNode()
        selection_node.SetActivePlaceNodeID(node.GetID())
        interaction_node = slicer.app.applicationLogic().GetInteractionNode()
        interaction_node.SetCurrentInteractionMode(interaction_node.Place)
        # Rectangle/line: single placement (Slicer exits placement after shape is complete)
        # Polygon/ellipse/freehand: persistent (user places multiple points, right-clicks to finish)
        if tool_id in ("rectangle", "line"):
            interaction_node.SetPlaceModePersistence(False)
        else:
            interaction_node.SetPlaceModePersistence(True)

        # Observe interaction node: when user right-clicks, Slicer exits
        # placement mode — we detect this and finalize the shape.
        self._observe_interaction_mode_change(interaction_node)

    def _observe_interaction_mode_change(self, interaction_node):
        """Watch for Slicer exiting placement mode (e.g. user right-clicks)."""
        # Remove any previous interaction observer
        self._remove_interaction_observer()
        tag = interaction_node.AddObserver(
            interaction_node.InteractionModeChangedEvent,
            self._on_interaction_mode_changed,
        )
        self._interaction_observer = (interaction_node, tag)

    def _remove_interaction_observer(self):
        """Remove the interaction mode observer if active."""
        if hasattr(self, "_interaction_observer") and self._interaction_observer:
            node, tag = self._interaction_observer
            try:
                node.RemoveObserver(tag)
            except Exception:
                pass
            self._interaction_observer = None

    def _on_interaction_mode_changed(self, caller, event):
        """Called when Slicer's interaction mode changes (e.g. right-click exits placement)."""
        interaction_node = caller
        if interaction_node.GetCurrentInteractionMode() != interaction_node.Place:
            # Placement mode was exited (user right-clicked to finish)
            self._remove_interaction_observer()
            if self._placement_node and self._active_tool:
                active = self._active_tool
                self._active_tool = None
                node = self._placement_node
                self._placement_node = None

                # Finalize based on tool type
                if active == "rectangle" and node.GetNumberOfControlPoints() > 0:
                    self._finalize_roi(node, active)
                elif active in ("ellipse", "polygon", "freehand_curve") and node.GetNumberOfControlPoints() >= 3:
                    self._finalize_roi(node, active)
                elif node.GetNumberOfControlPoints() == 0:
                    try:
                        slicer.mrmlScene.RemoveNode(node)
                    except Exception:
                        pass

                self._uncheck_all_tools()

    def _deactivate_tool(self):
        """Cancel placement mode and finalize pending shapes."""
        self._remove_interaction_observer()
        active = self._active_tool
        self._active_tool = None
        try:
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetCurrentInteractionMode(interaction_node.ViewTransform)
        except Exception:
            pass

        if not self._placement_node:
            return

        # Rectangle: finalize the ROI node as-is
        if active == "rectangle":
            try:
                if self._placement_node.GetNumberOfControlPoints() > 0:
                    self._finalize_roi(self._placement_node, active)
                    self._placement_node = None
                    return
            except Exception:
                pass

        # Ellipse/Polygon/freehand: finalize if enough points exist
        if active in ("ellipse", "polygon", "freehand_curve"):
            try:
                if self._placement_node.GetNumberOfControlPoints() >= 3:
                    self._finalize_roi(self._placement_node, active)
                    self._placement_node = None
                    return
            except Exception:
                pass

        # If the placement node has no control points, remove it
        try:
            if self._placement_node.GetNumberOfControlPoints() == 0:
                slicer.mrmlScene.RemoveNode(self._placement_node)
        except Exception:
            pass
        self._placement_node = None

    # ─── Node Observation ────────────────────────────────────────────────

    def _add_node_observer(self, node, event, callback):
        tag = node.AddObserver(event, callback)
        node_id = node.GetID()
        if node_id not in self._node_observers:
            self._node_observers[node_id] = []
        self._node_observers[node_id].append((node, tag))

    def _remove_node_observers(self, node_id):
        if node_id in self._node_observers:
            for node, tag in self._node_observers[node_id]:
                try:
                    node.RemoveObserver(tag)
                except Exception:
                    pass
            del self._node_observers[node_id]

    def _on_point_placed(self, caller, event):
        """Called when a control point is placed on a markup node."""
        node = caller
        if node is None:
            return

        tool_id = self._active_tool
        if tool_id == "line" and node.GetNumberOfControlPoints() >= 2:
            self._finalize_roi(node, tool_id)
            self._deactivate_tool()
            self._uncheck_all_tools()
        elif tool_id == "rectangle":
            # ROI node: finalize on deactivation
            pass


    def _guess_tool_type(self, node):
        """Infer tool type from the node class."""
        class_name = node.GetClassName()
        if "ClosedCurve" in class_name:
            return "polygon"
        elif "Curve" in class_name:
            return "freehand_curve"
        elif "Line" in class_name:
            return "line"
        elif "ROI" in class_name:
            return "ellipse"
        return "unknown"

    # ─── ROI Finalization ────────────────────────────────────────────────

    def _finalize_roi(self, node, tool_id):
        """Extract geometry from a placed markup node and register it as an ROIAnnotation."""
        # Avoid double-registration
        for existing in self._roi_annotations:
            if existing.mrml_node_id == node.GetID():
                return

        roi = ROIAnnotation()
        roi.roi_type = tool_id
        roi.label = self._get_selected_label()
        roi.color = self._current_color
        roi.mrml_node_id = node.GetID()
        roi.slice_view = self._get_active_slice_view()
        roi.slice_index = self._get_current_slice_index()

        # Extract control points
        points = []
        for i in range(node.GetNumberOfControlPoints()):
            pos = [0.0, 0.0, 0.0]
            node.GetNthControlPointPosition(i, pos)
            points.append({"x": pos[0], "y": pos[1], "z": pos[2]})
        roi.control_points = points

        # Extract size/radii for ROI nodes (ellipse/rectangle)
        if hasattr(node, "GetSize"):
            try:
                size = [0.0, 0.0, 0.0]
                node.GetSize(size)
                roi.radii = [size[0] / 2.0, size[1] / 2.0]
            except Exception:
                pass

        # Extract orientation for ROI nodes
        if hasattr(node, "GetObjectToWorldMatrix"):
            try:
                import vtk
                matrix = vtk.vtkMatrix4x4()
                node.GetObjectToWorldMatrix(matrix)
                orientation = []
                for row in range(3):
                    for col in range(3):
                        orientation.append(matrix.GetElement(row, col))
                roi.orientation = orientation
            except Exception:
                pass

        self._roi_annotations.append(roi)
        self._update_table()
        self._sync_to_record()

    # ─── Public API ──────────────────────────────────────────────────────

    def set_annotation_record(self, record):
        self._record = record

    def get_roi_annotations(self):
        """Return the list of ROIAnnotation objects."""
        return list(self._roi_annotations)

    def refresh_labels(self, labels):
        """Update the label combo box with a new set of labels."""
        self._labels = list(labels)
        current_text = self._label_combo.currentText
        self._label_combo.clear()
        self._label_combo.addItem("(No label)")
        for lbl in self._labels:
            self._label_combo.addItem(lbl)
        # Restore selection if still available
        idx = self._label_combo.findText(current_text)
        if idx >= 0:
            self._label_combo.setCurrentIndex(idx)

    def load_rois(self, rois):
        """
        Load ROIAnnotation objects: create corresponding MRML nodes in the scene
        and populate the table.
        """
        for roi in rois:
            node = self._create_node_from_roi(roi)
            if node:
                roi.mrml_node_id = node.GetID()
            self._roi_annotations.append(roi)
        self._update_table()

    def cancel_placement(self):
        """Cancel any active placement mode."""
        self._deactivate_tool()
        self._uncheck_all_tools()

    def cleanup(self):
        """Remove all observers. Called on tab switch or module unload."""
        self.cancel_placement()
        self._remove_interaction_observer()
        # Remove all node observers
        for node_id in list(self._node_observers.keys()):
            self._remove_node_observers(node_id)
        # Remove scene-level observers
        for subject, tag in self._observers:
            try:
                subject.RemoveObserver(tag)
            except Exception:
                pass
        self._observers.clear()

    def set_read_only(self, enabled):
        """Toggle read-only mode."""
        self._read_only = enabled

        # Tool buttons
        for tool_id, btn in self._tool_buttons.items():
            btn.setEnabled(not enabled and self._available_tools.get(tool_id, False))

        # Label/color
        self._label_combo.setEnabled(not enabled)
        self._color_btn.setEnabled(not enabled)

        # Actions
        self._delete_all_btn.setEnabled(not enabled)

        # Cancel active placement
        if enabled:
            self.cancel_placement()

        # Update table action buttons
        self._update_table()

        # Disable markup interaction handles in the scene
        for roi in self._roi_annotations:
            if roi.mrml_node_id:
                try:
                    node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                    if node:
                        display_node = node.GetDisplayNode()
                        if display_node and hasattr(display_node, "SetHandlesInteractive"):
                            display_node.SetHandlesInteractive(not enabled)
                except Exception:
                    pass

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _get_selected_label(self):
        text = self._label_combo.currentText
        if text == "(No label)":
            return ""
        return text

    def _on_pick_color(self):
        initial = qt.QColor(self._current_color)
        color = qt.QColorDialog.getColor(initial, self, "Select ROI Color")
        if color.isValid():
            self._current_color = color.name()
            self._color_btn.setStyleSheet(
                f"background-color: {self._current_color}; border: 1px solid #333;"
            )

    def _get_active_slice_view(self):
        """Return the name of the currently active slice view."""
        try:
            layout_manager = slicer.app.layoutManager()
            for name in ["Red", "Green", "Yellow"]:
                widget = layout_manager.sliceWidget(name)
                if widget and widget.hasFocus():
                    return name
            return "Red"
        except Exception:
            return ""

    def _get_current_slice_index(self):
        """Get the current slice offset index from the active slice widget."""
        try:
            layout_manager = slicer.app.layoutManager()
            slice_widget = layout_manager.sliceWidget("Red")
            if slice_widget:
                logic = slice_widget.sliceLogic()
                return int(logic.GetSliceOffset())
        except Exception:
            pass
        return 0

    def _uncheck_all_tools(self):
        for btn in self._tool_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)

    def _sync_to_record(self):
        """Sync the ROI annotations list to the bound AnnotationRecord."""
        if self._record:
            self._record.rois = list(self._roi_annotations)

    # ─── Table Management ────────────────────────────────────────────────

    def _update_table(self):
        """Rebuild the ROI list table from self._roi_annotations."""
        self._table.setRowCount(len(self._roi_annotations))
        for row, roi in enumerate(self._roi_annotations):
            # Column 0: row number
            self._table.setItem(row, 0, qt.QTableWidgetItem(str(row + 1)))

            # Column 1: type
            self._table.setItem(row, 1, qt.QTableWidgetItem(roi.roi_type))

            # Column 2: label
            self._table.setItem(row, 2, qt.QTableWidgetItem(roi.label or "(none)"))

            # Column 3: color swatch
            color_item = qt.QTableWidgetItem("")
            color_item.setBackground(qt.QColor(roi.color))
            self._table.setItem(row, 3, color_item)

            # Column 4: slice
            self._table.setItem(row, 4, qt.QTableWidgetItem(str(roi.slice_index)))

            # Column 5: action buttons
            action_widget = qt.QWidget()
            action_layout = qt.QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            edit_btn = qt.QPushButton("\u270e")
            edit_btn.setFixedSize(24, 24)
            edit_btn.setToolTip("Edit this ROI")
            edit_btn.clicked.connect(lambda checked, r=row: self._on_edit_roi(r))
            action_layout.addWidget(edit_btn)

            delete_btn = qt.QPushButton("\u2715")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setToolTip("Delete this ROI")
            delete_btn.clicked.connect(lambda checked, r=row: self._on_delete_roi(r))
            action_layout.addWidget(delete_btn)

            if self._read_only:
                edit_btn.hide()
                delete_btn.hide()

            self._table.setCellWidget(row, 5, action_widget)

        self._count_label.setText(f"ROI count: {len(self._roi_annotations)}")

    def _on_table_row_clicked(self, row, col):
        """Select and highlight the corresponding markup node in the scene."""
        if row >= len(self._roi_annotations):
            return
        roi = self._roi_annotations[row]
        if roi.mrml_node_id:
            try:
                node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                if node:
                    node.SetDisplayVisibility(True)
                    # Jump to the ROI in the slice view
                    if node.GetNumberOfControlPoints() > 0:
                        pos = [0.0, 0.0, 0.0]
                        node.GetNthControlPointPosition(0, pos)
                        slicer.modules.markups.logic().JumpSlicesToLocation(
                            pos[0], pos[1], pos[2], True
                        )
            except Exception:
                pass

    def _on_edit_roi(self, row):
        """Show a dialog to re-label and re-color an ROI."""
        if row >= len(self._roi_annotations):
            return
        roi = self._roi_annotations[row]

        dialog = qt.QDialog(self)
        dialog.setWindowTitle("Edit ROI")
        dlg_layout = qt.QVBoxLayout(dialog)

        # Label combo
        dlg_layout.addWidget(qt.QLabel("Label:"))
        combo = qt.QComboBox()
        combo.addItem("(No label)")
        for lbl in self._labels:
            combo.addItem(lbl)
        if roi.label:
            idx = combo.findText(roi.label)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        dlg_layout.addWidget(combo)

        # Color button
        color_row = qt.QHBoxLayout()
        color_row.addWidget(qt.QLabel("Color:"))
        edit_color = [roi.color]
        color_btn = qt.QPushButton("")
        color_btn.setFixedSize(32, 24)
        color_btn.setStyleSheet(f"background-color: {roi.color}; border: 1px solid #333;")

        def pick():
            c = qt.QColorDialog.getColor(qt.QColor(edit_color[0]), dialog, "Select Color")
            if c.isValid():
                edit_color[0] = c.name()
                color_btn.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #333;")

        color_btn.clicked.connect(pick)
        color_row.addWidget(color_btn)
        color_row.addStretch()
        dlg_layout.addLayout(color_row)

        # Save / Cancel
        btn_box = qt.QDialogButtonBox()
        save_btn = btn_box.addButton("Save", qt.QDialogButtonBox.AcceptRole)
        cancel_btn = btn_box.addButton("Cancel", qt.QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        dlg_layout.addWidget(btn_box)

        if dialog.exec_() == qt.QDialog.Accepted:
            new_label = combo.currentText
            if new_label == "(No label)":
                new_label = ""
            roi.label = new_label
            roi.color = edit_color[0]

            # Update the MRML node display
            if roi.mrml_node_id:
                try:
                    node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                    if node:
                        node.SetName(f"ROI_{new_label}_{roi.roi_type}" if new_label else f"ROI_{roi.roi_type}")
                        dn = node.GetDisplayNode()
                        if dn:
                            r, g, b = hex_to_rgb_float(roi.color)
                            dn.SetSelectedColor(r, g, b)
                            dn.SetColor(r, g, b)
                except Exception:
                    pass

            self._update_table()
            self._sync_to_record()

    def _on_delete_roi(self, row):
        """Delete a single ROI from the table and the MRML scene."""
        if row >= len(self._roi_annotations):
            return
        roi = self._roi_annotations[row]

        # Remove MRML node
        if roi.mrml_node_id:
            self._remove_node_observers(roi.mrml_node_id)
            try:
                node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                if node:
                    slicer.mrmlScene.RemoveNode(node)
            except Exception:
                pass

        self._roi_annotations.pop(row)
        self._update_table()
        self._sync_to_record()

    def _on_delete_all(self):
        """Delete all ROIs after confirmation."""
        result = qt.QMessageBox.question(
            self, "Confirm Delete All",
            "Are you sure you want to delete all ROIs?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if result != qt.QMessageBox.Yes:
            return

        for roi in self._roi_annotations:
            if roi.mrml_node_id:
                self._remove_node_observers(roi.mrml_node_id)
                try:
                    node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                    if node:
                        slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass

        self._roi_annotations.clear()
        self._update_table()
        self._sync_to_record()

    def _on_export_json(self):
        """Export ROI annotations to a JSON file."""
        filepath = qt.QFileDialog.getSaveFileName(
            self, "Export ROIs", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        data = [roi.to_dict() for roi in self._roi_annotations]
        import json
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    # ─── Create MRML nodes from loaded annotations ──────────────────────

    def _create_node_from_roi(self, roi):
        """Create a Slicer markup node from an ROIAnnotation (for loading saved data)."""
        class_name = MARKUP_NODE_CLASSES.get(roi.roi_type)

        if not class_name:
            logger.warning(f"Unknown ROI type: {roi.roi_type}")
            return None

        try:
            node = slicer.mrmlScene.AddNewNodeByClass(class_name)
        except Exception:
            logger.error(f"Failed to create node for ROI type: {roi.roi_type}")
            return None

        if not node:
            return None

        node.SetName(f"ROI_{roi.label}_{roi.roi_type}" if roi.label else f"ROI_{roi.roi_type}")

        # Set control points
        for pt in roi.control_points:
            node.AddControlPoint(pt.get("x", 0), pt.get("y", 0), pt.get("z", 0))

        # Set size for ROI nodes (rectangle)
        if roi.radii and hasattr(node, "SetSize"):
            try:
                size = [roi.radii[0] * 2, roi.radii[1] * 2, 0.0]
                if len(roi.radii) > 2:
                    size[2] = roi.radii[2] * 2
                node.SetSize(size)
            except Exception:
                pass

        # Set color
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(roi.color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)

        # Disable interaction in read-only mode
        if self._read_only and display_node and hasattr(display_node, "SetHandlesInteractive"):
            display_node.SetHandlesInteractive(False)

        return node

    # ─── Finalize on tool deactivation (for polygon/freehand) ────────────

    def complete_current_placement(self):
        """
        Finalize the current placement (for polygon/freehand which need
        explicit completion). Called when switching tabs or deactivating tool.
        """
        if self._placement_node and self._active_tool in ("polygon", "freehand_curve"):
            if self._placement_node.GetNumberOfControlPoints() >= 2:
                self._finalize_roi(self._placement_node, self._active_tool)
        self._deactivate_tool()
        self._uncheck_all_tools()
