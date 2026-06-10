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
from SliceInfo import capture_slice_info, get_active_slice_view, ras_to_voxel_ijk
from RadiologyTerms import roi_geometry_type_export, plane_to_slice_view, slice_view_to_plane

logger = logging.getLogger(__name__)

# Maps ROI type names to their Slicer MRML node class names.
# Checked at runtime; unavailable types get their button disabled.
MARKUP_NODE_CLASSES = {
    "rectangle_2d": "vtkMRMLMarkupsPlaneNode",
    "rectangle_3d": "vtkMRMLMarkupsROINode",
    "rectangle": "vtkMRMLMarkupsROINode",  # backward compat
    "polygon": "vtkMRMLMarkupsClosedCurveNode",
    "freehand_curve": "vtkMRMLMarkupsCurveNode",
    "line": "vtkMRMLMarkupsLineNode",
}

PLANE_RECTANGLE_TOOL_IDS = ("rectangle_2d",)
RECTANGLE_TOOL_IDS = ("rectangle_3d", "rectangle")

EXTENDABLE_ROI_TYPES = frozenset({"polygon", "freehand_curve", "line"})


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

    def __init__(self, annotation_record=None, parent=None):
        super().__init__(parent)
        self._record = annotation_record
        self._roi_labels = []  # List[LabelDefinition] from config
        self._roi_annotations = []  # List[ROIAnnotation]
        self._volume_node = None
        self._current_color = "#ff0000"
        self._active_tool = None
        self._observers = []  # (subject, tag) pairs for cleanup
        self._node_observers = {}  # node_id -> [(subject, tag), ...]
        self._available_tools = {}
        self._placement_node = None
        self._rectangle_finalize_scheduled = set()
        self._extend_roi = None
        self._extend_mode_active = False

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
            ("rectangle_2d", "Bounding Box 2D"),
            ("rectangle_3d", "Bounding Box"),
            ("polygon", "Polygon Contour"),
            ("freehand_curve", "Freehand Contour"),
            ("line", "Linear Measurement"),
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

        self._extend_hint_label = qt.QLabel("")
        self._extend_hint_label.setStyleSheet("color: #1565C0; font-size: 11px; font-style: italic;")
        self._extend_hint_label.setWordWrap(True)
        self._extend_hint_label.hide()
        toolbar_layout.addWidget(self._extend_hint_label)

        parent_layout.addWidget(toolbar_frame)

    def _build_label_section(self, parent_layout):
        label_frame = qt.QFrame()
        label_frame.setFrameShape(qt.QFrame.StyledPanel)
        label_layout = qt.QVBoxLayout(label_frame)

        row1 = qt.QHBoxLayout()
        row1.addWidget(qt.QLabel("ROI category:"))
        self._label_combo = qt.QComboBox()
        self._label_combo.currentIndexChanged.connect(self._on_label_selection_changed)
        row1.addWidget(self._label_combo)
        row1.addStretch()
        label_layout.addLayout(row1)

        row2 = qt.QHBoxLayout()
        row2.addWidget(qt.QLabel("Color:"))
        self._color_swatch = qt.QLabel("")
        self._color_swatch.setFixedSize(32, 24)
        self._color_swatch.setStyleSheet(
            f"background-color: {self._current_color}; border: 1px solid #333;"
        )
        row2.addWidget(self._color_swatch)
        row2.addStretch()
        label_layout.addLayout(row2)

        parent_layout.addWidget(label_frame)

    def _build_roi_table(self, parent_layout):
        self._table = qt.QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["#", "Actions", "Geometry", "Category", "Color", "Plane", "Slice #"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(1, 150)
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
            if tool_id not in self._tool_buttons:
                continue
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
            self._deactivate_tool()
            for tid, btn in self._tool_buttons.items():
                if tid != tool_id:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)

            extend_row = self._selected_table_row()
            if extend_row >= 0 and self._can_extend_with_tool(extend_row, tool_id):
                self._begin_extend_roi(extend_row, from_tool=True)
                self._check_tool_button(tool_id)
            else:
                self._activate_tool(tool_id)
        else:
            if self._extend_mode_active:
                self._finish_extend_mode(sync=True)
            self._deactivate_tool()

    def _configure_roi_node(self, node):
        """Set ROI node type to Box for 3D rectangle placement."""
        if not hasattr(node, "SetROIType"):
            return
        try:
            if hasattr(node, "GetROITypeFromString"):
                node.SetROIType(node.GetROITypeFromString("Box"))
            elif hasattr(node, "ROITypeBox"):
                node.SetROIType(node.ROITypeBox)
            else:
                node.SetROIType(0)
        except Exception as e:
            logger.warning(f"Could not configure ROI box type: {e}")

    def _configure_plane_node(self, node):
        """Use Slicer Markups defaults for slice-aligned plane rectangles."""
        try:
            if hasattr(node, "SetNormalPointRequired"):
                node.SetNormalPointRequired(False)
        except Exception as e:
            logger.warning(f"Could not configure plane markup node: {e}")

    def _enter_plane_placement(self, node):
        """Enter placement mode the same way the Markups module does for planes."""
        selection_node = slicer.app.applicationLogic().GetSelectionNode()
        interaction_node = slicer.app.applicationLogic().GetInteractionNode()
        try:
            slicer.modules.markups.logic().SetActiveList(node)
        except Exception:
            selection_node.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsPlaneNode")
            selection_node.SetActivePlaceNodeID(node.GetID())
        interaction_node.SetPlaceModePersistence(False)
        interaction_node.SetCurrentInteractionMode(interaction_node.Place)
        return interaction_node

    def _sync_plane_geometry(self, node):
        """Refresh plane rectangle geometry from its control points."""
        for method_name in ("UpdatePlaneFromControlPoints", "UpdatePlaneSize"):
            try:
                method = getattr(node, method_name, None)
                if callable(method):
                    method()
            except Exception:
                pass

    def _get_defined_control_point_count(self, node):
        """Return how many plane control points have been placed."""
        try:
            if hasattr(node, "GetNumberOfDefinedControlPoints"):
                return int(node.GetNumberOfDefinedControlPoints())
        except Exception:
            pass
        try:
            return int(node.GetNumberOfControlPoints())
        except Exception:
            return 0

    def _control_point_distance(self, node, index_a, index_b):
        """Euclidean distance between two markup control points."""
        pos_a = [0.0, 0.0, 0.0]
        pos_b = [0.0, 0.0, 0.0]
        if hasattr(node, "GetNthControlPointPositionWorld"):
            node.GetNthControlPointPositionWorld(index_a, pos_a)
            node.GetNthControlPointPositionWorld(index_b, pos_b)
        else:
            node.GetNthControlPointPosition(index_a, pos_a)
            node.GetNthControlPointPosition(index_b, pos_b)
        return (
            (pos_a[0] - pos_b[0]) ** 2
            + (pos_a[1] - pos_b[1]) ** 2
            + (pos_a[2] - pos_b[2]) ** 2
        ) ** 0.5

    def _has_plane_size(self, node):
        """True if the plane rectangle has a non-degenerate extent."""
        self._sync_plane_geometry(node)
        try:
            if hasattr(node, "GetIsPlaneValid") and bool(node.GetIsPlaneValid()):
                return True
        except Exception:
            pass
        defined = self._get_defined_control_point_count(node)
        if defined >= 2 and self._control_point_distance(node, 0, 1) > 1e-3:
            return True
        for method_name in ("GetSizeWorld", "GetSize"):
            try:
                method = getattr(node, method_name, None)
                if not callable(method):
                    continue
                size = [0.0, 0.0]
                method(size)
                if float(size[0]) > 1e-3 and float(size[1]) > 1e-3:
                    return True
            except Exception:
                pass
        return False

    def _plane_placement_complete(self, node):
        """True once Slicer has finished a Markups-style plane placement."""
        try:
            if hasattr(node, "GetControlPointPlacementComplete"):
                if bool(node.GetControlPointPlacementComplete()):
                    return self._has_plane_size(node)
        except Exception:
            pass
        return (
            self._get_defined_control_point_count(node) >= 1
            and self._has_plane_size(node)
        )

    def _finish_plane_rectangle(self, node, tool_id):
        """Finalize a completed plane rectangle and exit placement mode."""
        if node is None:
            return
        self._remove_node_observers(node.GetID())
        self._active_tool = None
        self._placement_node = None
        self._remove_interaction_observer()
        try:
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetCurrentInteractionMode(interaction_node.ViewTransform)
        except Exception:
            pass
        self._schedule_plane_finalize(node, tool_id)
        self._uncheck_all_tools()

    def _cancel_plane_rectangle(self, node=None):
        """Discard an in-progress plane rectangle and exit placement mode."""
        if node:
            self._remove_node_observers(node.GetID())
        self._active_tool = None
        self._placement_node = None
        self._remove_interaction_observer()
        try:
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetCurrentInteractionMode(interaction_node.ViewTransform)
        except Exception:
            pass
        if node:
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception:
                pass
        self._uncheck_all_tools()

    def _extract_plane_corner_points(self, node):
        """Return plane rectangle corners as [{x,y,z}, ...] in RAS."""
        import vtk

        self._sync_plane_geometry(node)
        points = []
        if hasattr(node, "GetPlaneCornerPoints"):
            try:
                corner_points = vtk.vtkPoints()
                node.GetPlaneCornerPoints(corner_points)
                for i in range(corner_points.GetNumberOfPoints()):
                    pt = [0.0, 0.0, 0.0]
                    corner_points.GetPoint(i, pt)
                    points.append({"x": pt[0], "y": pt[1], "z": pt[2]})
            except Exception:
                points = []

        if not points and hasattr(node, "GetPlaneBounds") and hasattr(node, "GetPlaneToWorldMatrix"):
            try:
                bounds = [0.0, 0.0, 0.0, 0.0]
                node.GetPlaneBounds(bounds)
                matrix = vtk.vtkMatrix4x4()
                node.GetPlaneToWorldMatrix(matrix)
                for lx, ly in (
                    (bounds[0], bounds[2]),
                    (bounds[1], bounds[2]),
                    (bounds[1], bounds[3]),
                    (bounds[0], bounds[3]),
                ):
                    world = matrix.MultiplyPoint([lx, ly, 0.0, 1.0])
                    points.append({"x": world[0], "y": world[1], "z": world[2]})
            except Exception:
                points = []

        if not points:
            for i in range(node.GetNumberOfControlPoints()):
                pos = [0.0, 0.0, 0.0]
                node.GetNthControlPointPosition(i, pos)
                points.append({"x": pos[0], "y": pos[1], "z": pos[2]})
        return points

    def _apply_plane_geometry_metadata(self, roi, node):
        """Populate ROI fields from a vtkMRMLMarkupsPlaneNode."""
        import vtk

        roi.mrml_node_name = node.GetName() if node else ""
        roi.control_points = self._extract_plane_corner_points(node)
        roi.number_of_control_points = len(roi.control_points)

        if hasattr(node, "GetSize"):
            try:
                size = [0.0, 0.0]
                node.GetSize(size)
                roi.bounding_box_dimensions = [float(size[0]), float(size[1]), 0.0]
                roi.radii = [float(size[0]) / 2.0, float(size[1]) / 2.0, 0.0]
            except Exception:
                pass

        if hasattr(node, "GetCenter"):
            try:
                center = [0.0, 0.0, 0.0]
                node.GetCenter(center)
                roi.center_ras = list(center)
                if self._volume_node:
                    roi.center_voxel_ijk = ras_to_voxel_ijk(self._volume_node, roi.center_ras)
            except Exception:
                pass
        elif roi.control_points:
            xs = [pt["x"] for pt in roi.control_points]
            ys = [pt["y"] for pt in roi.control_points]
            zs = [pt["z"] for pt in roi.control_points]
            roi.center_ras = [
                sum(xs) / len(xs),
                sum(ys) / len(ys),
                sum(zs) / len(zs),
            ]
            if self._volume_node:
                roi.center_voxel_ijk = ras_to_voxel_ijk(self._volume_node, roi.center_ras)

        if hasattr(node, "GetPlaneToWorldMatrix"):
            try:
                matrix = vtk.vtkMatrix4x4()
                node.GetPlaneToWorldMatrix(matrix)
                roi.orientation = [
                    matrix.GetElement(row, col) for row in range(3) for col in range(3)
                ]
            except Exception:
                pass

    def _schedule_plane_finalize(self, node, tool_id):
        """Defer planar rectangle finalization until plane geometry is ready."""
        if node is None:
            return
        node_id = node.GetID()
        if node_id in self._rectangle_finalize_scheduled:
            return
        self._rectangle_finalize_scheduled.add(node_id)

        def cleanup():
            self._rectangle_finalize_scheduled.discard(node_id)

        def attempt(retry=0):
            n = slicer.mrmlScene.GetNodeByID(node_id)
            if not n:
                cleanup()
                return

            if not self._has_plane_size(n):
                if retry < 30:
                    qt.QTimer.singleShot(100, lambda r=retry + 1: attempt(r))
                    return
                logger.warning("Discarding incomplete plane rectangle ROI")
                try:
                    slicer.mrmlScene.RemoveNode(n)
                except Exception:
                    pass
                cleanup()
                return

            self._finalize_roi(n, tool_id)
            cleanup()

        qt.QTimer.singleShot(50, lambda: attempt(0))

    def _sync_roi_geometry(self, node, tool_id=None):
        """Ask a 3D ROI node to refresh geometry from its internal state."""
        if hasattr(node, "UpdateBoxROIFromControlPoints"):
            try:
                node.UpdateBoxROIFromControlPoints()
            except Exception:
                pass
        if hasattr(node, "UpdateROIFromControlPoints"):
            try:
                node.UpdateROIFromControlPoints()
            except Exception:
                pass

    def _has_roi_size(self, node):
        """True if the ROI box has meaningful extent (not a zero-size placement artifact)."""
        try:
            bounds = [0.0] * 6
            node.GetRASBounds(bounds)
            dims = [
                abs(bounds[1] - bounds[0]),
                abs(bounds[3] - bounds[2]),
                abs(bounds[5] - bounds[4]),
            ]
            significant = sorted(d for d in dims if d > 1e-3)
            if len(significant) >= 2:
                return True
        except Exception:
            pass

        if not hasattr(node, "GetSize"):
            return False
        try:
            size = [0.0, 0.0, 0.0]
            node.GetSize(size)
            significant = sorted(float(s) for s in size if float(s) > 1e-3)
            return len(significant) >= 2
        except Exception:
            pass
        return False

    def _rectangle_placement_complete(self, node):
        """True once Slicer has converted the two corners into a box ROI."""
        self._sync_roi_geometry(node)
        return self._has_roi_size(node)

    def _resume_rectangle_placement(self, node, tool_id):
        """Re-enter placement when only the first corner has been placed."""
        try:
            self._active_tool = tool_id
            self._placement_node = node
            selection_node = slicer.app.applicationLogic().GetSelectionNode()
            selection_node.SetActivePlaceNodeID(node.GetID())
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetPlaceModePersistence(False)
            interaction_node.SetCurrentInteractionMode(interaction_node.Place)
            self._observe_interaction_mode_change(interaction_node)
        except Exception as e:
            logger.warning(f"Could not resume rectangle placement: {e}")

    def _roi_ready_to_finalize(self, node, tool_id):
        """Return True if a box ROI has enough geometry to finalize."""
        if tool_id not in RECTANGLE_TOOL_IDS:
            return False
        self._sync_roi_geometry(node, tool_id)
        return self._has_roi_size(node)

    def _schedule_rectangle_finalize(self, node, tool_id):
        """
        Defer rectangle finalization until Slicer finishes updating ROI geometry.
        Only called after placement mode exits with a complete box.
        """
        if node is None:
            return
        node_id = node.GetID()
        if node_id in self._rectangle_finalize_scheduled:
            return
        self._rectangle_finalize_scheduled.add(node_id)

        def cleanup():
            self._rectangle_finalize_scheduled.discard(node_id)

        def attempt(retry=0):
            n = slicer.mrmlScene.GetNodeByID(node_id)
            if not n:
                cleanup()
                return

            if not self._roi_ready_to_finalize(n, tool_id):
                if retry < 30:
                    qt.QTimer.singleShot(100, lambda r=retry + 1: attempt(r))
                    return
                if not self._has_roi_size(n):
                    logger.warning("Discarding incomplete rectangle ROI")
                    try:
                        slicer.mrmlScene.RemoveNode(n)
                    except Exception:
                        pass
                else:
                    logger.warning("Could not register rectangle ROI — keeping node in scene")
                cleanup()
                return

            self._finalize_roi(n, tool_id)
            cleanup()

        qt.QTimer.singleShot(50, lambda: attempt(0))

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

        if tool_id in RECTANGLE_TOOL_IDS:
            self._configure_roi_node(node)
        elif tool_id in PLANE_RECTANGLE_TOOL_IDS:
            self._configure_plane_node(node)

        # Set color on display node
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(self._current_color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)
            self._configure_markup_display(display_node, transform_handles=False)

        self._placement_node = node

        if tool_id == "line":
            self._add_node_observer(
                node,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                self._on_point_placed,
            )
        elif tool_id in PLANE_RECTANGLE_TOOL_IDS:
            self._add_node_observer(
                node,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                self._on_plane_point_placed,
            )

        if tool_id in PLANE_RECTANGLE_TOOL_IDS:
            interaction_node = self._enter_plane_placement(node)
        else:
            selection_node = slicer.app.applicationLogic().GetSelectionNode()
            selection_node.SetActivePlaceNodeID(node.GetID())
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetCurrentInteractionMode(interaction_node.Place)
            if tool_id in RECTANGLE_TOOL_IDS or tool_id == "line":
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
        if interaction_node.GetCurrentInteractionMode() == interaction_node.Place:
            return

        self._remove_interaction_observer()

        if self._extend_mode_active:
            self._finish_extend_mode(sync=True)
            return

        if not self._placement_node or not self._active_tool:
            return

        active = self._active_tool
        node = self._placement_node

        if active in RECTANGLE_TOOL_IDS:
            try:
                cp_count = node.GetNumberOfControlPoints()
            except Exception:
                cp_count = 0

            if self._rectangle_placement_complete(node):
                self._active_tool = None
                self._placement_node = None
                self._schedule_rectangle_finalize(node, active)
                self._uncheck_all_tools()
            elif cp_count >= 1:
                qt.QTimer.singleShot(
                    0, lambda n=node, t=active: self._resume_rectangle_placement(n, t)
                )
            else:
                # Box ROI removes control points when done; geometry may lag behind.
                self._active_tool = None
                self._placement_node = None
                self._schedule_rectangle_finalize(node, active)
                self._uncheck_all_tools()
            return

        if active in PLANE_RECTANGLE_TOOL_IDS:
            if self._plane_placement_complete(node):
                self._finish_plane_rectangle(node, active)
            else:
                self._cancel_plane_rectangle(node)
            return

        self._active_tool = None
        self._placement_node = None

        if active in ("polygon", "freehand_curve") and node.GetNumberOfControlPoints() >= 3:
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

        # 3D box: finalize only when the box is complete
        if active in RECTANGLE_TOOL_IDS:
            node = self._placement_node
            self._placement_node = None
            if self._rectangle_placement_complete(node):
                self._schedule_rectangle_finalize(node, active)
            else:
                try:
                    slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
            return

        if active in PLANE_RECTANGLE_TOOL_IDS:
            node = self._placement_node
            if self._plane_placement_complete(node):
                self._finish_plane_rectangle(node, active)
            else:
                self._cancel_plane_rectangle(node)
            return

        # Ellipse/Polygon/freehand: finalize if enough points exist
        if active in ("polygon", "freehand_curve"):
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

    def _on_plane_point_placed(self, caller, event):
        """Finalize a plane rectangle once Slicer finishes building the plane."""
        if caller is None or self._active_tool not in PLANE_RECTANGLE_TOOL_IDS:
            return
        if caller is not self._placement_node:
            return

        def attempt(retry=0):
            if caller is not self._placement_node or not self._active_tool:
                return
            if self._plane_placement_complete(caller):
                self._finish_plane_rectangle(caller, self._active_tool)
            elif retry < 20:
                qt.QTimer.singleShot(50, lambda r=retry + 1: attempt(r))

        qt.QTimer.singleShot(0, lambda: attempt(0))

    def _guess_tool_type(self, node):
        """Infer tool type from the node class."""
        class_name = node.GetClassName()
        if "ClosedCurve" in class_name:
            return "polygon"
        elif "Curve" in class_name:
            return "freehand_curve"
        elif "Line" in class_name:
            return "line"
        elif "Plane" in class_name:
            return "rectangle_2d"
        elif "ROI" in class_name:
            return "rectangle_3d"
        return "unknown"

    # ─── Extend / edit existing ROIs ─────────────────────────────────────

    def _check_tool_button(self, tool_id):
        btn = self._tool_buttons.get(tool_id)
        if btn:
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)

    def _selected_table_row(self):
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return -1
        row = indexes[0].row()
        if 0 <= row < len(self._roi_annotations):
            return row
        return -1

    def _can_extend_with_tool(self, row, tool_id):
        if row < 0 or row >= len(self._roi_annotations):
            return False
        roi = self._roi_annotations[row]
        return (
            self._is_extendable(roi)
            and roi.roi_type == tool_id
            and bool(roi.mrml_node_id)
        )

    def _is_extendable(self, roi):
        return roi.roi_type in EXTENDABLE_ROI_TYPES

    def _set_curve_linear(self, node):
        if node is None:
            return
        for method_name in ("SetCurveTypeToLinear",):
            try:
                method = getattr(node, method_name, None)
                if callable(method):
                    method()
                    return
            except Exception:
                pass
        try:
            if hasattr(node, "CurveTypeLinear"):
                node.CurveType = node.CurveTypeLinear
        except Exception:
            pass

    def _copy_markup_display(self, source_node, target_node, transform_handles=False):
        source_display = source_node.GetDisplayNode() if source_node else None
        target_display = target_node.GetDisplayNode() if target_node else None
        if not source_display or not target_display:
            return
        try:
            target_display.SetSelectedColor(source_display.GetSelectedColor())
            target_display.SetColor(source_display.GetColor())
            self._configure_markup_display(target_display, transform_handles=transform_handles)
        except Exception:
            pass

    def _prepare_line_for_extension(self, node, roi):
        """Convert a 2-point line node to a linear open curve so it can grow."""
        if node is None:
            return None
        if "Line" not in node.GetClassName():
            return node

        points = []
        for i in range(node.GetNumberOfControlPoints()):
            pos = [0.0, 0.0, 0.0]
            node.GetNthControlPointPosition(i, pos)
            points.append(pos)

        curve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
        if not curve:
            return node
        curve.SetName(node.GetName())
        self._copy_markup_display(node, curve, roi.transform_handles_enabled)
        for pos in points:
            curve.AddControlPoint(pos[0], pos[1], pos[2])
        self._set_curve_linear(curve)

        old_id = node.GetID()
        self._remove_node_observers(old_id)
        try:
            slicer.mrmlScene.RemoveNode(node)
        except Exception:
            pass

        roi.mrml_node_id = curve.GetID()
        return curve

    def _sync_roi_from_node(self, roi, node):
        if roi is None or node is None:
            return
        points = []
        for i in range(node.GetNumberOfControlPoints()):
            pos = [0.0, 0.0, 0.0]
            node.GetNthControlPointPosition(i, pos)
            points.append({"x": pos[0], "y": pos[1], "z": pos[2]})
        roi.control_points = points
        self._apply_geometry_metadata(roi, node)
        self._update_table()
        self._sync_to_record()

    def _ensure_extend_observers(self, node):
        for event in (
            slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
            slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
        ):
            self._add_node_observer(node, event, self._on_extend_node_modified)

    def _on_extend_node_modified(self, caller, event):
        if self._extend_roi and caller is not None:
            self._sync_roi_from_node(self._extend_roi, caller)

    def _show_extend_hint(self, roi):
        self._extend_hint_label.setText(
            f"Extending {roi_geometry_type_export(roi.roi_type)} \"{roi.label or 'ROI'}\" "
            "from the latest point: click on the slice to add points. Right-click to finish."
        )
        self._extend_hint_label.show()

    def _hide_extend_hint(self):
        self._extend_hint_label.hide()
        self._extend_hint_label.setText("")

    def _begin_extend_roi(self, row, from_tool=False):
        if row < 0 or row >= len(self._roi_annotations):
            return

        roi = self._roi_annotations[row]
        if not self._is_extendable(roi) or not roi.mrml_node_id:
            return

        if from_tool:
            self._finish_extend_mode(sync=True)
        else:
            self._deactivate_tool()
            self._finish_extend_mode(sync=True)
            self._uncheck_all_tools()

        node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
        if not node:
            return

        if roi.roi_type == "line":
            node = self._prepare_line_for_extension(node, roi)
            if not node:
                return

        self._extend_roi = roi
        self._extend_mode_active = True
        self._table.selectRow(row)
        self._show_extend_hint(roi)

        display_node = node.GetDisplayNode()
        if display_node:
            self._configure_markup_display(
                display_node, transform_handles=roi.transform_handles_enabled
            )

        try:
            slicer.modules.markups.logic().SetActiveList(node)
        except Exception:
            pass

        selection_node = slicer.app.applicationLogic().GetSelectionNode()
        selection_node.SetActivePlaceNodeID(node.GetID())

        interaction_node = slicer.app.applicationLogic().GetInteractionNode()
        interaction_node.SetPlaceModePersistence(True)
        interaction_node.SetCurrentInteractionMode(interaction_node.Place)
        self._observe_interaction_mode_change(interaction_node)
        self._ensure_extend_observers(node)

        if node.GetNumberOfControlPoints() > 0:
            pos = [0.0, 0.0, 0.0]
            node.GetNthControlPointPosition(node.GetNumberOfControlPoints() - 1, pos)
            try:
                slicer.modules.markups.logic().JumpSlicesToLocation(
                    pos[0], pos[1], pos[2], True
                )
            except Exception:
                pass

    def _finish_extend_mode(self, sync=False):
        if not self._extend_mode_active and not self._extend_roi:
            return

        roi = self._extend_roi
        if sync and roi and roi.mrml_node_id:
            node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
            if node:
                self._sync_roi_from_node(roi, node)
                self._configure_markup_display(
                    node.GetDisplayNode(),
                    transform_handles=roi.transform_handles_enabled,
                )

        self._extend_mode_active = False
        self._extend_roi = None
        self._hide_extend_hint()
        self._remove_interaction_observer()
        self._uncheck_all_tools()
        try:
            interaction_node = slicer.app.applicationLogic().GetInteractionNode()
            interaction_node.SetCurrentInteractionMode(interaction_node.ViewTransform)
        except Exception:
            pass

    # ─── ROI Finalization ────────────────────────────────────────────────

    def _selected_label_definition(self):
        text = self._get_selected_label()
        for label_def in self._roi_labels:
            if label_def.name == text:
                return label_def
        return None

    def _apply_slice_context(self, roi, slice_info):
        roi.slice_view = slice_info.get("plane", slice_info.get("slice_view", ""))
        roi.slice_index = slice_info.get("slice_number", slice_info.get("slice_index", 0))
        roi.slice_offset_mm = float(slice_info.get("slice_offset_mm", 0) or 0)
        roi.slice_position_ras = list(
            slice_info.get("position_ras", slice_info.get("slice_position_ras", []))
        )
        roi.volume_slice_ijk = list(
            slice_info.get("voxel_index_ijk", slice_info.get("volume_slice_ijk", []))
        )
        roi.slicer_slice_view = slice_info.get("slicer_slice_view", "")
        roi.slice_to_ras_matrix = list(slice_info.get("slice_to_ras_matrix", []))
        roi.field_of_view = list(slice_info.get("field_of_view", []))
        roi.slice_spacing = float(slice_info.get("slice_spacing", 0.0) or 0.0)
        roi.slice_normal_ras = list(slice_info.get("slice_normal_ras", []))
        roi.volume_node_id = slice_info.get("volume_node_id", "")
        roi.volume_name = slice_info.get("volume_name", "")

    def _apply_category_metadata(self, roi):
        label_def = self._selected_label_definition()
        if label_def:
            roi.category_id = label_def.id
            roi.category_description = label_def.description

    def _apply_geometry_metadata(self, roi, node):
        roi.mrml_node_name = node.GetName() if node else ""
        roi.number_of_control_points = len(roi.control_points)
        if roi.control_points:
            first = roi.control_points[0]
            roi.center_ras = [first.get("x", 0.0), first.get("y", 0.0), first.get("z", 0.0)]
            if self._volume_node:
                roi.center_voxel_ijk = ras_to_voxel_ijk(self._volume_node, roi.center_ras)
        if roi.radii:
            roi.bounding_box_dimensions = [float(r) * 2.0 for r in roi.radii[:3]]

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
        slice_info = capture_slice_info(self._volume_node)
        self._apply_slice_context(roi, slice_info)
        self._apply_category_metadata(roi)

        if tool_id in PLANE_RECTANGLE_TOOL_IDS:
            self._apply_plane_geometry_metadata(roi, node)
        else:
            # Extract control points
            points = []
            for i in range(node.GetNumberOfControlPoints()):
                pos = [0.0, 0.0, 0.0]
                node.GetNthControlPointPosition(i, pos)
                points.append({"x": pos[0], "y": pos[1], "z": pos[2]})
            if not points and hasattr(node, "GetXYZ"):
                try:
                    center = [0.0, 0.0, 0.0]
                    node.GetXYZ(center)
                    points.append({"x": center[0], "y": center[1], "z": center[2]})
                except Exception:
                    pass
            roi.control_points = points

            # Extract size/radii for 3D ROI nodes
            if hasattr(node, "GetSize"):
                try:
                    size = [0.0, 0.0, 0.0]
                    node.GetSize(size)
                    roi.radii = [size[0] / 2.0, size[1] / 2.0, size[2] / 2.0]
                except Exception:
                    pass

            # Extract orientation for 3D ROI nodes
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

            self._apply_geometry_metadata(roi, node)
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(roi.color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)
            self._configure_markup_display(
                display_node, transform_handles=roi.transform_handles_enabled
            )
        self._roi_annotations.append(roi)
        self._update_table()
        self._sync_to_record()

    # ─── Public API ──────────────────────────────────────────────────────

    def set_annotation_record(self, record):
        self._record = record

    def get_roi_annotations(self):
        """Return the list of ROIAnnotation objects."""
        return list(self._roi_annotations)

    def set_labels(self, labels):
        """Populate the ROI label dropdown from configured labels (LabelDefinition list)."""
        self._roi_labels = list(labels)
        self._label_combo.blockSignals(True)
        self._label_combo.clear()
        for label_def in self._roi_labels:
            self._label_combo.addItem(label_def.name)
        self._label_combo.blockSignals(False)
        if self._roi_labels:
            self._current_color = self._roi_labels[0].color
            self._update_color_swatch()

    def apply_label_config(self, old_labels, new_labels):
        """Update existing ROI annotations and MRML nodes when labels are edited or deleted."""
        old_by_id = {lbl.id: lbl for lbl in old_labels}
        new_by_id = {lbl.id: lbl for lbl in new_labels}
        removed_ids = set(old_by_id) - set(new_by_id)
        removed_names = {old_by_id[lid].name for lid in removed_ids}

        surviving = []
        for roi in self._roi_annotations:
            if roi.label in removed_names:
                self._remove_roi_node(roi)
                continue

            for lid, old_lbl in old_by_id.items():
                if lid not in new_by_id:
                    continue
                new_lbl = new_by_id[lid]
                if roi.label in (old_lbl.name, new_lbl.name):
                    roi.label = new_lbl.name
                    roi.color = new_lbl.color
                    self._apply_roi_appearance(roi)
                    break

            surviving.append(roi)

        self._roi_annotations = surviving
        self._update_table()
        self._sync_to_record()

    def _update_color_swatch(self):
        self._color_swatch.setStyleSheet(
            f"background-color: {self._current_color}; border: 1px solid #333;"
        )

    def _on_label_selection_changed(self, index):
        """Auto-set color from the selected label's configured color."""
        if 0 <= index < len(self._roi_labels):
            label_def = self._roi_labels[index]
            self._current_color = label_def.color
            self._update_color_swatch()

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

    def set_volume(self, volume_node):
        """Store the shared volume reference used for slice context capture."""
        self._volume_node = volume_node

    def clear_and_unbind(self):
        """Remove all ROI nodes from the scene, clear table, reset state.
        Labels persist from config — only annotations are cleared."""
        self.cancel_placement()
        self._remove_interaction_observer()
        for node_id in list(self._node_observers.keys()):
            self._remove_node_observers(node_id)
        for roi in self._roi_annotations:
            if roi.mrml_node_id:
                try:
                    node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                    if node:
                        slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
        self._roi_annotations = []
        self._update_table()
        self._volume_node = None

    def cancel_placement(self):
        """Cancel any active placement or extend mode."""
        self._finish_extend_mode(sync=True)
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

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _configure_markup_display(self, display_node, transform_handles=False):
        """Apply visibility settings; transform_handles controls move/rotate widget."""
        if not display_node:
            return
        try:
            display_node.SetVisibility(True)
            display_node.SetHandlesInteractive(bool(transform_handles))
        except Exception:
            pass
        for method_name, value in (
            ("SetTranslationHandleVisibility", transform_handles),
            ("SetRotationHandleVisibility", transform_handles),
            ("SetScaleHandleVisibility", transform_handles),
        ):
            try:
                method = getattr(display_node, method_name, None)
                if callable(method):
                    method(bool(value))
            except Exception:
                pass
        try:
            markups_dn = slicer.vtkMRMLMarkupsDisplayNode
            if hasattr(display_node, "SetHandleVisibility"):
                for handle_name in ("TranslateHandle", "RotateHandle", "ScaleHandle"):
                    handle_type = getattr(markups_dn, handle_name, None)
                    if handle_type is not None:
                        display_node.SetHandleVisibility(handle_type, bool(transform_handles))
        except Exception:
            pass

    def _apply_roi_display_handles(self, roi):
        if not roi or not roi.mrml_node_id:
            return
        node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
        if node:
            self._configure_markup_display(
                node.GetDisplayNode(),
                transform_handles=roi.transform_handles_enabled,
            )

    def _on_roi_transform_handles_toggled(self, roi, checked):
        roi.transform_handles_enabled = bool(checked)
        self._apply_roi_display_handles(roi)

    def _get_selected_label(self):
        text = self._label_combo.currentText
        return text if text else ""

    def _get_active_slice_view(self):
        """Return the name of the currently active slice view."""
        return get_active_slice_view()

    def _get_current_slice_index(self, slice_name=None):
        """Get the current anatomical slice index from a slice widget."""
        if slice_name:
            slicer_name = plane_to_slice_view(slice_name)
            from SliceInfo import capture_slice_info_for_view
            info = capture_slice_info_for_view(slicer_name, self._volume_node)
            return info.get("slice_index", 0)
        info = capture_slice_info(self._volume_node)
        return info.get("slice_index", 0)

    def _uncheck_all_tools(self):
        for btn in self._tool_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)

    def _sync_to_record(self):
        """Sync the ROI annotations list to the bound AnnotationRecord."""
        if self._record:
            self._record.rois = list(self._roi_annotations)

    def _apply_roi_appearance(self, roi):
        """Apply label name and color to the MRML markup node for an ROI."""
        if not roi.mrml_node_id:
            return
        node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
        if not node:
            return
        node.SetName(f"ROI_{roi.label}_{roi.roi_type}" if roi.label else f"ROI_{roi.roi_type}")
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(roi.color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)
            self._configure_markup_display(
                display_node, transform_handles=roi.transform_handles_enabled
            )

    # ─── Table Management ────────────────────────────────────────────────

    def _update_table(self):
        """Rebuild the ROI list table from self._roi_annotations."""
        self._table.setRowCount(len(self._roi_annotations))
        for row, roi in enumerate(self._roi_annotations):
            # Column 0: row number
            self._table.setItem(row, 0, qt.QTableWidgetItem(str(row + 1)))

            # Column 1: action buttons
            action_widget = qt.QWidget()
            action_layout = qt.QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            delete_btn = qt.QPushButton("\u2715")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setToolTip("Delete this ROI")
            delete_btn.clicked.connect(lambda checked, r=row: self._on_delete_roi(r))
            action_layout.addWidget(delete_btn)

            if self._is_extendable(roi):
                extend_btn = qt.QPushButton("\u270E")
                extend_btn.setFixedSize(24, 24)
                extend_btn.setToolTip("Extend from the latest control point")
                extend_btn.clicked.connect(lambda checked, r=row: self._begin_extend_roi(r))
                action_layout.addWidget(extend_btn)

            handles_cb = qt.QCheckBox("Move")
            handles_cb.setToolTip("Show move/rotate handles for this ROI")
            handles_cb.blockSignals(True)
            handles_cb.setChecked(roi.transform_handles_enabled)
            handles_cb.blockSignals(False)
            handles_cb.toggled.connect(
                lambda checked, target=roi: self._on_roi_transform_handles_toggled(target, checked)
            )
            action_layout.addWidget(handles_cb)

            self._table.setCellWidget(row, 1, action_widget)

            # Column 2: geometry type
            self._table.setItem(
                row, 2, qt.QTableWidgetItem(roi_geometry_type_export(roi.roi_type))
            )

            # Column 3: category
            self._table.setItem(row, 3, qt.QTableWidgetItem(roi.label or "(none)"))

            # Column 4: color swatch
            color_item = qt.QTableWidgetItem("")
            color_item.setBackground(qt.QColor(roi.color))
            self._table.setItem(row, 4, color_item)

            # Column 5: plane
            plane = slice_view_to_plane(roi.slice_view) if roi.slice_view else ""
            self._table.setItem(row, 5, qt.QTableWidgetItem(plane or "—"))

            # Column 6: slice number
            self._table.setItem(row, 6, qt.QTableWidgetItem(str(roi.slice_index)))

        self._count_label.setText(f"ROI count: {len(self._roi_annotations)}")

    def _on_table_row_clicked(self, row, col):
        """Select and highlight the corresponding markup node in the scene."""
        if row >= len(self._roi_annotations):
            return
        self._table.selectRow(row)
        roi = self._roi_annotations[row]
        if roi.mrml_node_id:
            try:
                node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
                if node:
                    node.SetDisplayVisibility(True)
                    display_node = node.GetDisplayNode()
                    if display_node:
                        self._configure_markup_display(
                            display_node, transform_handles=roi.transform_handles_enabled
                        )
                    try:
                        slicer.modules.markups.logic().SetActiveList(node)
                    except Exception:
                        pass
                    # Jump to the ROI in the slice view
                    if node.GetNumberOfControlPoints() > 0:
                        pos = [0.0, 0.0, 0.0]
                        node.GetNthControlPointPosition(0, pos)
                        slicer.modules.markups.logic().JumpSlicesToLocation(
                            pos[0], pos[1], pos[2], True
                        )
            except Exception:
                pass

    def _on_delete_roi(self, row):
        """Delete a single ROI from the table and the MRML scene."""
        if row >= len(self._roi_annotations):
            return
        roi = self._roi_annotations[row]
        self._remove_roi_node(roi)
        self._roi_annotations.pop(row)
        self._update_table()
        self._sync_to_record()

    def _remove_roi_node(self, roi):
        """Remove an ROI's MRML node and observers from the scene."""
        if not roi.mrml_node_id:
            return
        self._remove_node_observers(roi.mrml_node_id)
        try:
            node = slicer.mrmlScene.GetNodeByID(roi.mrml_node_id)
            if node:
                slicer.mrmlScene.RemoveNode(node)
        except Exception:
            pass
        roi.mrml_node_id = ""

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
                self._remove_roi_node(roi)

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
        roi_type = roi.roi_type
        if roi_type == "rectangle":
            roi_type = "rectangle_3d"

        class_name = MARKUP_NODE_CLASSES.get(roi_type)

        if roi_type == "line" and len(roi.control_points) > 2:
            class_name = "vtkMRMLMarkupsCurveNode"

        # Legacy ROI types no longer in the toolbar
        if not class_name and roi.roi_type == "ellipse":
            class_name = "vtkMRMLMarkupsClosedCurveNode"

        # Legacy planar saves may be closed curves with four corners
        if (
            roi.roi_type == "rectangle_2d"
            and class_name == "vtkMRMLMarkupsPlaneNode"
            and len(roi.control_points) == 4
            and not roi.radii
            and not roi.bounding_box_dimensions
            and not roi.orientation
        ):
            class_name = "vtkMRMLMarkupsClosedCurveNode"

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

        if class_name == "vtkMRMLMarkupsROINode":
            self._configure_roi_node(node)
        elif class_name == "vtkMRMLMarkupsPlaneNode":
            self._configure_plane_node(node)

        if class_name == "vtkMRMLMarkupsPlaneNode":
            if roi.center_ras and len(roi.center_ras) == 3 and hasattr(node, "SetCenter"):
                try:
                    node.SetCenter(roi.center_ras[0], roi.center_ras[1], roi.center_ras[2])
                except Exception:
                    pass
            placement_points = roi.control_points[:1] if roi.center_ras else roi.control_points[:3]
            for pt in placement_points:
                node.AddControlPoint(pt.get("x", 0), pt.get("y", 0), pt.get("z", 0))
        else:
            for pt in roi.control_points:
                node.AddControlPoint(pt.get("x", 0), pt.get("y", 0), pt.get("z", 0))

        if class_name == "vtkMRMLMarkupsCurveNode" and roi_type == "line":
            self._set_curve_linear(node)

        if class_name == "vtkMRMLMarkupsPlaneNode":
            self._sync_plane_geometry(node)
            if roi.bounding_box_dimensions and hasattr(node, "SetSize"):
                try:
                    node.SetSize(
                        float(roi.bounding_box_dimensions[0]),
                        float(roi.bounding_box_dimensions[1]),
                    )
                except Exception:
                    pass
            elif roi.radii and hasattr(node, "SetSize"):
                try:
                    node.SetSize(float(roi.radii[0]) * 2.0, float(roi.radii[1]) * 2.0)
                except Exception:
                    pass
            self._sync_plane_geometry(node)

        if class_name == "vtkMRMLMarkupsROINode" and roi.radii and hasattr(node, "SetSize"):
            try:
                size = [roi.radii[0] * 2, roi.radii[1] * 2, 0.0]
                if len(roi.radii) > 2:
                    size[2] = roi.radii[2] * 2
                node.SetSize(size)
            except Exception:
                pass

            if roi.orientation and len(roi.orientation) == 9 and hasattr(node, "SetObjectToWorldMatrix"):
                try:
                    import vtk
                    matrix = vtk.vtkMatrix4x4()
                    for row in range(3):
                        for col in range(3):
                            matrix.SetElement(row, col, roi.orientation[row * 3 + col])
                    if roi.control_points:
                        pt = roi.control_points[0]
                        matrix.SetElement(0, 3, pt.get("x", 0))
                        matrix.SetElement(1, 3, pt.get("y", 0))
                        matrix.SetElement(2, 3, pt.get("z", 0))
                    elif hasattr(node, "GetXYZ"):
                        center = [0.0, 0.0, 0.0]
                        node.GetXYZ(center)
                        for i in range(3):
                            matrix.SetElement(i, 3, center[i])
                    if hasattr(node, "SetAndObserveObjectToWorldMatrix"):
                        node.SetAndObserveObjectToWorldMatrix(matrix)
                    else:
                        node.SetObjectToWorldMatrix(matrix)
                except Exception:
                    pass

            self._sync_roi_geometry(node)

        # Set color
        display_node = node.GetDisplayNode()
        if display_node:
            r, g, b = hex_to_rgb_float(roi.color)
            display_node.SetSelectedColor(r, g, b)
            display_node.SetColor(r, g, b)
            self._configure_markup_display(
                display_node, transform_handles=roi.transform_handles_enabled
            )

        return node

    # ─── Finalize on tool deactivation (for polygon/freehand) ────────────

    def complete_current_placement(self):
        """
        Finalize the current placement (for polygon/freehand which need
        explicit completion). Called when switching tabs or deactivating tool.
        """
        self._finish_extend_mode(sync=True)
        if self._placement_node and self._active_tool in ("polygon", "freehand_curve"):
            if self._placement_node.GetNumberOfControlPoints() >= 2:
                self._finalize_roi(self._placement_node, self._active_tool)
        self._deactivate_tool()
        self._uncheck_all_tools()
