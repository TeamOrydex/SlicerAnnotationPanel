"""
Segmentation tab: pixel-level painting using Slicer's Segment Editor.
Embeds qMRMLSegmentEditorWidget with opacity adjustment.
The source volume and segment classes are set externally by the panel.
"""
import os
import qt
import slicer
import logging

from AnnotationModel import (
    SegmentationData,
    SegmentLabel,
    SegmentSpatialExtent,
    SegmentModificationEvent,
    PlaneSliceContext,
    VOLUME_SCOPED_EFFECTS,
    should_record_segment_modification,
    segment_label_def_for_label_value,
)
from SliceInfo import (
    capture_slice_info,
    capture_slice_info_for_view,
    capture_slice_context_at_cursor,
    get_active_slice_view,
    install_slice_tracking,
    remember_slice_view_interaction,
    set_active_slice_view,
)

logger = logging.getLogger(__name__)

# Effect names must match Slicer's qMRMLSegmentEditorWidget defaults exactly.
SEGMENT_EDITOR_EFFECT_ORDER = [
    "Threshold",
    "Paint",
    "Draw",
    "Erase",
    "Level tracing",
    "Grow from seeds",
    "Fill between slices",
    "Margin",
    "Hollow",
    "Smoothing",
    "Scissors",
    "Islands",
    "Logical operators",
    "Mask volume",
]

# Fallback parameter names when MRML attribute enumeration is unavailable.
EFFECT_KNOWN_PARAMS = {
    "Threshold": [
        "MinimumThreshold",
        "MaximumThreshold",
        "AutoThresholdMethod",
        "AutoThresholdMode",
        "BrushType",
        "HistogramSetLower",
        "HistogramSetUpper",
    ],
    "Paint": [
        "BrushSize",
        "BrushType",
        "ColorSmudge",
        "IntensityMask",
        "IntensityMaskRange",
    ],
    "Erase": [
        "BrushSize",
        "BrushType",
    ],
    "Level tracing": [
        "MinimumThreshold",
        "MaximumThreshold",
    ],
    "Grow from seeds": [
        "SeedLocalityFactor",
        "AutoUpdate",
    ],
    "Fill between slices": [
        "AutoUpdate",
    ],
    "Margin": [
        "ApplyToAllVisibleSegments",
        "MarginSizeMm",
    ],
    "Hollow": [
        "ApplyToAllVisibleSegments",
        "ShellMode",
        "ShellThicknessMm",
    ],
    "Smoothing": [
        "ApplyToAllVisibleSegments",
        "SmoothingMethod",
        "KernelSizeMm",
        "GaussianStandardDeviationMm",
        "JointTaubinSmoothingFactor",
    ],
    "Scissors": [
        "Operation",
        "Shape",
    ],
    "Islands": [
        "Operation",
        "MinimumSize",
    ],
    "Logical operators": [
        "Operation",
        "ModifierSegmentID",
        "BypassMasking",
    ],
    "Mask volume": [
        "FillValue",
        "BinaryMaskFillValueOutside",
        "BinaryMaskFillValueInside",
        "Operation",
        "SoftEdgeMm",
    ],
}

# Brush parameters shared across Paint, Draw, and Erase effects.
COMMON_BRUSH_PARAMS = [
    "BrushMinimumAbsoluteDiameter",
    "BrushMaximumAbsoluteDiameter",
    "BrushAbsoluteDiameter",
    "BrushRelativeDiameter",
    "BrushSphere",
    "EditIn3DViews",
    "BrushPixelMode",
    "ColorSmudge",
    "EraseAllSegments",
]


def hex_to_rgb_float(hex_color):
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16) / 255.0,
        int(hex_color[2:4], 16) / 255.0,
        int(hex_color[4:6], 16) / 255.0,
    )


def rgb_float_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


class SegmentationTab(qt.QWidget):
    """Segmentation tab wrapping Slicer's qMRMLSegmentEditorWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segmentation_node = None
        self._segment_editor_node = None
        self._volume_node = None
        self._seg_labels = []  # List[LabelDefinition] from config
        self._label_to_segment_map = {}  # label_def.id -> segment_id in segmentation
        self._modification_events = []
        self._segmentation_observer = None
        self._segmentation_core_observer = None
        self._cached_effect_name = ""
        self._cached_effect_params = {}
        self._cached_segment_id = ""
        self._cached_slice_context = {}
        self._last_interaction_slice_context = {}
        self._pending_slice_contexts = {}
        self._segment_effect_summary = {}
        self._segment_voxel_snapshots = {}
        self._segment_labelmap_mtimes = {}
        self._recorded_modification_mtimes = {}
        self._effect_params_by_name = {}
        self._context_timer = None
        self._last_export_error = ""
        self._segment_editor_observer = None
        self._editor_slice_observers = []
        self._setup_ui()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)
        self._build_segment_editor(layout)

    def _build_segment_editor(self, parent_layout):
        frame = qt.QFrame()
        frame.setFrameShape(qt.QFrame.StyledPanel)
        fl = qt.QVBoxLayout(frame)

        self._segment_editor_widget = slicer.qMRMLSegmentEditorWidget()
        self._segment_editor_widget.setMRMLScene(slicer.mrmlScene)
        self._segment_editor_widget.setEffectNameOrder(SEGMENT_EDITOR_EFFECT_ORDER)
        self._segment_editor_widget.unorderedEffectsVisible = False
        self._segment_editor_widget.setAddRemoveSegmentButtonsVisible(False)
        try:
            self._segment_editor_widget.setSourceVolumeNodeSelectorVisible(False)
        except AttributeError:
            pass
        try:
            self._segment_editor_widget.setSegmentationNodeSelectorVisible(False)
        except AttributeError:
            pass
        fl.addWidget(self._segment_editor_widget)

        qt.QTimer.singleShot(0, self._hide_segment_editor_navigation_button)

        opacity_row = qt.QHBoxLayout()
        opacity_row.addWidget(qt.QLabel("Overlay opacity:"))
        self._opacity_slider = qt.QSlider(qt.Qt.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self._opacity_slider)
        fl.addLayout(opacity_row)

        parent_layout.addWidget(frame)

    def _hide_segment_editor_navigation_button(self):
        """Hide the unused green arrow next to Show 3D in Slicer's segment editor."""
        widget = self._segment_editor_widget
        if not widget:
            return

        hidden = False
        arrow_labels = {">", "→", "▶", "➤", "»", "↗", "➔"}
        jump_tokens = ("jump", "go to", "fly to", "center on", "scroll to", "slice offset")

        for button in widget.findChildren(qt.QAbstractButton):
            if not isinstance(button, (qt.QPushButton, qt.QToolButton)):
                continue
            tip = (button.toolTip or "").lower()
            label = (button.text or "").strip().lower()
            if label in {text.lower() for text in arrow_labels} or label in arrow_labels:
                button.setVisible(False)
                hidden = True
                continue
            if any(token in tip for token in jump_tokens):
                button.setVisible(False)
                hidden = True

        show_3d_widget = None
        for checkbox in widget.findChildren(qt.QCheckBox):
            text = f"{checkbox.text or ''} {checkbox.toolTip or ''}".lower()
            if "show 3d" in text or "edit in 3d" in text or "3d view" in text:
                show_3d_widget = checkbox
                break

        if show_3d_widget:
            parent = show_3d_widget.parentWidget()
            layout = parent.layout() if parent else None
            if layout:
                found_show_3d = False
                for index in range(layout.count()):
                    item = layout.itemAt(index)
                    item_widget = item.widget() if item else None
                    if item_widget is show_3d_widget:
                        found_show_3d = True
                        continue
                    if found_show_3d and isinstance(item_widget, qt.QAbstractButton):
                        item_widget.setVisible(False)
                        hidden = True
                        break

        if not hidden:
            logger.debug("Segment editor navigation button not found to hide")

    # ─── Volume Binding (called by panel) ────────────────────────────────

    def set_volume(self, volume_node, create_segments=True):
        """Bind a shared volume as the source for segmentation."""
        self._volume_node = volume_node
        if volume_node:
            install_slice_tracking()
        self._ensure_segmentation_node(volume_node)
        self._link_editor_to_nodes(volume_node)
        if create_segments and self._seg_labels:
            self._create_segments_from_config()
        self._start_context_timer()

    def initialize_without_volume(self, labels, create_segments=True):
        """Create a segmentation workspace that does not require a loaded series."""
        self._seg_labels = list(labels)
        if self._volume_node:
            self.set_volume(self._volume_node, create_segments=create_segments)
            return
        if self._segmentation_node is not None:
            if create_segments and self._seg_labels:
                self._create_segments_from_config()
            return

        install_slice_tracking()
        self._ensure_segmentation_node(None)
        self._link_editor_to_nodes(None)
        if create_segments and self._seg_labels:
            self._create_segments_from_config()
        self._start_context_timer()

    def has_segmentation_workspace(self):
        """Return True when a segmentation node has been created for this tab."""
        return self._segmentation_node is not None

    def detach_volume_reference(self):
        """Keep segmentation data but stop referencing a source volume."""
        self._volume_node = None
        if self._segmentation_node is None:
            return
        self._apply_default_reference_geometry()
        self._link_editor_to_nodes(None)

    def bind_volume_reference(self, volume_node):
        """Attach a source volume to existing segmentation without recreating segments."""
        self._volume_node = volume_node
        if volume_node:
            install_slice_tracking()
        if self._segmentation_node and volume_node:
            self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
                volume_node
            )
            self._link_editor_to_nodes(volume_node)
        elif volume_node:
            self._ensure_segmentation_node(volume_node)
            self._link_editor_to_nodes(volume_node)

    def clear_and_unbind(self):
        """Remove segmentation data and unbind the volume.
        Labels persist from config — only segmentation nodes are cleared."""
        self.deactivate_effect()
        if self._segmentation_node:
            try:
                slicer.mrmlScene.RemoveNode(self._segmentation_node)
            except Exception:
                pass
            self._segmentation_node = None
        if self._segment_editor_node:
            try:
                slicer.mrmlScene.RemoveNode(self._segment_editor_node)
            except Exception:
                pass
            self._segment_editor_node = None
        self._volume_node = None
        self._label_to_segment_map = {}
        self._modification_events = []
        self._segment_effect_summary = {}
        self._segment_voxel_snapshots = {}
        self._segment_labelmap_mtimes = {}
        self._recorded_modification_mtimes = {}
        self._cached_slice_context = {}
        self._last_interaction_slice_context = {}
        self._pending_slice_contexts = {}
        self._effect_params_by_name = {}
        self._stop_context_timer()
        self._remove_segmentation_observer()
        self._remove_segment_editor_observer()
        self._remove_editor_slice_tracking()

    # ─── Label Config (called by panel) ──────────────────────────────────

    def set_labels(self, labels, create_segments=True):
        """Receive segmentation class labels from config."""
        self._seg_labels = list(labels)
        if not create_segments or not self._seg_labels:
            return

        if self._segmentation_node is None:
            self._ensure_segmentation_node(self._volume_node)
            self._link_editor_to_nodes(self._volume_node)
            self._start_context_timer()
        self._create_segments_from_config()

    def reconcile_imported_segment_labels(self, seg_labels, label_to_segment_map=None):
        """Associate configured segmentation classes with imported MRML segments."""
        self._seg_labels = list(seg_labels)
        if self._segmentation_node is None:
            return

        segmentation = self._segmentation_node.GetSegmentation()
        label_by_id = {label_def.id: label_def for label_def in seg_labels}
        label_by_name = {label_def.name: label_def for label_def in seg_labels}
        self._label_to_segment_map = {}

        if label_to_segment_map:
            for label_id, segment_id in label_to_segment_map.items():
                if not label_id or not segment_id:
                    continue
                label_def = label_by_id.get(label_id)
                segment = segmentation.GetSegment(segment_id)
                if not label_def or not segment:
                    continue
                segment.SetName(label_def.name)
                r, g, b = hex_to_rgb_float(label_def.color)
                segment.SetColor(r, g, b)
                self._label_to_segment_map[label_id] = segment_id

        mapped_segment_ids = set(self._label_to_segment_map.values())
        for i in range(segmentation.GetNumberOfSegments()):
            segment_id = segmentation.GetNthSegmentID(i)
            if segment_id in mapped_segment_ids:
                continue
            segment = segmentation.GetSegment(segment_id)
            if not segment:
                continue

            label_def = None
            try:
                label_value = int(segment.GetLabelValue())
                label_def = segment_label_def_for_label_value(label_value, seg_labels)
            except Exception:
                label_def = None

            if label_def is None:
                label_def = label_by_name.get(segment.GetName())

            if not label_def:
                continue

            segment.SetName(label_def.name)
            r, g, b = hex_to_rgb_float(label_def.color)
            segment.SetColor(r, g, b)
            self._label_to_segment_map[label_def.id] = segment_id
            mapped_segment_ids.add(segment_id)

        for i in range(segmentation.GetNumberOfSegments() - 1, -1, -1):
            segment_id = segmentation.GetNthSegmentID(i)
            if segment_id not in mapped_segment_ids:
                segmentation.RemoveSegment(segment_id)

        for label_def in seg_labels:
            if label_def.id in self._label_to_segment_map:
                continue
            r, g, b = hex_to_rgb_float(label_def.color)
            segment_id = segmentation.AddEmptySegment(
                label_def.name, label_def.name, [r, g, b]
            )
            self._label_to_segment_map[label_def.id] = segment_id

        self._select_first_segment()
        self._reset_modification_snapshots()
        try:
            self._segment_editor_widget.refresh()
        except Exception:
            pass

    def update_labels_from_config(self, old_labels, new_labels):
        """Update segment names/colors in place without wiping painted data."""
        self._seg_labels = list(new_labels)
        if self._segmentation_node is None:
            return

        if not self._label_to_segment_map:
            self._rebuild_label_segment_map(old_labels, new_labels)

        old_by_id = {lbl.id: lbl for lbl in old_labels}
        new_by_id = {lbl.id: lbl for lbl in new_labels}
        segmentation = self._segmentation_node.GetSegmentation()

        for lid, new_def in new_by_id.items():
            seg_id = self._label_to_segment_map.get(lid)
            if not seg_id:
                continue
            segment = segmentation.GetSegment(seg_id)
            if segment:
                segment.SetName(new_def.name)
                r, g, b = hex_to_rgb_float(new_def.color)
                segment.SetColor(r, g, b)

        for lid in set(old_by_id) - set(new_by_id):
            seg_id = self._label_to_segment_map.pop(lid, None)
            if seg_id:
                segmentation.RemoveSegment(seg_id)

        for lid, new_def in new_by_id.items():
            if lid in self._label_to_segment_map:
                continue
            r, g, b = hex_to_rgb_float(new_def.color)
            seg_id = segmentation.AddEmptySegment(
                new_def.name, new_def.name, [r, g, b]
            )
            self._label_to_segment_map[lid] = seg_id

        try:
            self._segment_editor_widget.refresh()
        except Exception:
            pass
        self._select_first_segment()

    def _rebuild_label_segment_map(self, old_labels, new_labels):
        """Match existing MRML segments to config label ids by name."""
        if self._segmentation_node is None:
            return

        segmentation = self._segmentation_node.GetSegmentation()
        seg_by_name = {}
        for i in range(segmentation.GetNumberOfSegments()):
            seg_id = segmentation.GetNthSegmentID(i)
            segment = segmentation.GetSegment(seg_id)
            if segment:
                seg_by_name[segment.GetName()] = seg_id

        for lbl in list(old_labels) + list(new_labels):
            if lbl.id in self._label_to_segment_map:
                continue
            if lbl.name in seg_by_name:
                self._label_to_segment_map[lbl.id] = seg_by_name[lbl.name]

    def _create_segments_from_config(self):
        """Create one segment per configured segmentation class."""
        if self._segmentation_node is None:
            return

        segmentation = self._segmentation_node.GetSegmentation()
        segmentation.RemoveAllSegments()
        self._label_to_segment_map = {}

        for label_def in self._seg_labels:
            r, g, b = hex_to_rgb_float(label_def.color)
            seg_id = segmentation.AddEmptySegment(
                label_def.name, label_def.name, [r, g, b]
            )
            self._label_to_segment_map[label_def.id] = seg_id

        self._select_first_segment()
        self._reset_modification_snapshots()

    def _select_first_segment(self):
        """Select the first configured segment in the segment editor."""
        if self._segmentation_node is None:
            return
        segmentation = self._segmentation_node.GetSegmentation()
        if segmentation.GetNumberOfSegments() > 0:
            segment_id = segmentation.GetNthSegmentID(0)
            try:
                self._segment_editor_widget.setCurrentSegmentID(segment_id)
            except Exception:
                pass

    # ─── Internal volume linking ─────────────────────────────────────────

    def _ensure_segmentation_node(self, volume_node):
        """Create or reuse a segmentation node for this annotation."""
        if self._segmentation_node is None:
            self._segmentation_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode"
            )
            self._segmentation_node.CreateDefaultDisplayNodes()
            self._segmentation_node.SetName("AnnotationSegmentation")

        if volume_node:
            self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
                volume_node
            )
        else:
            self._apply_default_reference_geometry()
        self._install_segmentation_observer()

        display_node = self._segmentation_node.GetDisplayNode()
        if display_node:
            display_node.SetVisibility(True)
            display_node.SetAllSegmentsVisibility(True)
            display_node.SetOpacity(self._opacity_slider.value / 100.0)

    def _apply_default_reference_geometry(self):
        """Use a default reference geometry when no source volume is available."""
        if self._segmentation_node is None:
            return

        try:
            import vtk

            direction = vtk.vtkMatrix4x4()
            direction.Identity()
            self._segmentation_node.SetReferenceImageGeometryParameter(
                [256, 256, 256],
                [1.0, 1.0, 1.0],
                [0.0, 0.0, 0.0],
                direction,
            )
        except Exception as e:
            logger.warning(f"Could not set default segmentation reference geometry: {e}")

    def _link_editor_to_nodes(self, volume_node):
        """Connect the segment editor widget to the segmentation and volume."""
        if self._segment_editor_node is None:
            self._segment_editor_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentEditorNode"
            )

        self._segment_editor_widget.setMRMLSegmentEditorNode(self._segment_editor_node)
        self._segment_editor_widget.setSegmentationNode(self._segmentation_node)
        self._install_segment_editor_observer()
        self._install_editor_slice_tracking()

        try:
            self._segment_editor_widget.setSourceVolumeNode(volume_node)
        except AttributeError:
            try:
                self._segment_editor_widget.setMasterVolumeNode(volume_node)
            except AttributeError:
                logger.warning("Could not set source volume on segment editor widget")

        qt.QTimer.singleShot(0, self._hide_segment_editor_navigation_button)

    # ─── Opacity ─────────────────────────────────────────────────────────

    def _on_opacity_changed(self, value):
        if self._segmentation_node:
            display_node = self._segmentation_node.GetDisplayNode()
            if display_node:
                display_node.SetOpacity(value / 100.0)

    def _export_segments_to_labelmap(self, labelmap_node):
        """Export segmentation segments into a labelmap aligned to the source volume."""
        logic = slicer.modules.segmentations.logic()
        if self._volume_node:
            self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
                self._volume_node
            )

        extent_mode = getattr(
            slicer.vtkSegmentation, "EXTENT_REFERENCE_GEOMETRY", None
        )
        if extent_mode is not None:
            exported = logic.ExportAllSegmentsToLabelmapNode(
                self._segmentation_node, labelmap_node, extent_mode
            )
            if exported:
                return True

        exported = logic.ExportAllSegmentsToLabelmapNode(
            self._segmentation_node, labelmap_node
        )
        if exported:
            return True

        if hasattr(logic, "ExportVisibleSegmentsToLabelmapNode"):
            return logic.ExportVisibleSegmentsToLabelmapNode(
                self._segmentation_node, labelmap_node, self._volume_node
            )

        return False

    def export_mask_to_file(self, filepath, fmt="nrrd"):
        """Export the segmentation labelmap to a file. Returns True on success."""
        if self._segmentation_node is None:
            self._last_export_error = "Segmentation is not available."
            return False

        labelmap_node = None
        scalar_node = None
        self._last_export_error = ""
        try:
            labelmap_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            exported = self._export_segments_to_labelmap(labelmap_node)
            if not exported:
                self._last_export_error = "Could not export segmentation segments to a labelmap."
                return False

            export_path = filepath
            if fmt == "nifti":
                if not export_path.lower().endswith((".nii", ".nii.gz")):
                    export_path = f"{export_path}.nii.gz"
                scalar_node = self._labelmap_as_scalar_volume(labelmap_node)
                slicer.util.saveNode(scalar_node, export_path)
            else:
                if not export_path.lower().endswith(".nrrd"):
                    export_path = f"{export_path}.nrrd"
                slicer.util.saveNode(labelmap_node, export_path)

            if not os.path.exists(export_path):
                self._last_export_error = f"Export file was not created: {export_path}"
                return False
            return True
        except Exception as e:
            self._last_export_error = str(e)
            logger.error(f"Export failed: {e}")
            return False
        finally:
            if scalar_node is not None:
                slicer.mrmlScene.RemoveNode(scalar_node)
            if labelmap_node is not None:
                slicer.mrmlScene.RemoveNode(labelmap_node)

    def export_segmentation_node_to_file(self, filepath):
        """Export the segmentation node as Slicer .seg.nrrd with segment names and colors."""
        if self._segmentation_node is None:
            self._last_export_error = "Segmentation is not available."
            return False

        self._last_export_error = ""
        try:
            export_path = filepath
            if not export_path.lower().endswith(".seg.nrrd"):
                if export_path.lower().endswith(".nrrd"):
                    export_path = f"{export_path[:-5]}.seg.nrrd"
                else:
                    export_path = f"{export_path}.seg.nrrd"

            if self._volume_node:
                self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
                    self._volume_node
                )

            if not slicer.util.saveNode(self._segmentation_node, export_path):
                self._last_export_error = f"Could not write segmentation to {export_path}"
                return False
            if not os.path.exists(export_path):
                self._last_export_error = f"Export file was not created: {export_path}"
                return False
            return True
        except Exception as e:
            self._last_export_error = str(e)
            logger.error(f"Segmentation node export failed: {e}")
            return False

    def _load_segmentation_from_seg_nrrd(self, filepath, volume_node):
        """Load a Slicer-native segmentation file that preserves names and colors."""
        loaded_node_ids = slicer.util.load(filepath) or []
        segmentation_node = None
        for node_id in loaded_node_ids:
            node = slicer.mrmlScene.GetNodeByID(node_id)
            if node and node.IsA("vtkMRMLSegmentationNode"):
                segmentation_node = node
                break
        if segmentation_node is None:
            segmentation_node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLSegmentationNode")
        if segmentation_node is None:
            raise RuntimeError(f"No segmentation node loaded from {filepath}")

        segmentation_node.SetName("AnnotationSegmentation")
        segmentation_node.CreateDefaultDisplayNodes()
        if volume_node:
            segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        self._segmentation_node = segmentation_node
        self._install_segmentation_observer()
        display_node = self._segmentation_node.GetDisplayNode()
        if display_node:
            display_node.SetVisibility(True)
            display_node.SetAllSegmentsVisibility(True)
            display_node.SetOpacity(self._opacity_slider.value / 100.0)
        self._link_editor_to_nodes(volume_node)

    def _labelmap_as_scalar_volume(self, labelmap_node):
        """Copy a labelmap into a scalar volume node so NIfTI writers can persist it."""
        import vtk

        scalar_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        scalar_node.SetName(labelmap_node.GetName())
        scalar_node.SetSpacing(labelmap_node.GetSpacing())
        scalar_node.SetOrigin(labelmap_node.GetOrigin())
        ijk_to_ras = vtk.vtkMatrix4x4()
        labelmap_node.GetIJKToRASMatrix(ijk_to_ras)
        scalar_node.SetIJKToRASMatrix(ijk_to_ras)
        image_data = vtk.vtkImageData()
        image_data.DeepCopy(labelmap_node.GetImageData())
        scalar_node.SetAndObserveImageData(image_data)
        return scalar_node

    # ─── Modification tracking ───────────────────────────────────────────

    def _start_context_timer(self):
        if self._context_timer is None:
            self._context_timer = qt.QTimer()
            self._context_timer.timeout.connect(self._poll_editor_context_and_changes)
        if not self._context_timer.isActive():
            self._context_timer.start(250)

    def _stop_context_timer(self):
        if self._context_timer is not None:
            self._context_timer.stop()

    def _normalize_slice_context(self, slice_info):
        if not slice_info:
            return {}
        return PlaneSliceContext.from_slice_info(slice_info).to_export_dict()

    def _remember_slice_interaction(self, view_name):
        """Capture slice context when the user interacts with a specific slice view."""
        ctx = remember_slice_view_interaction(view_name, self._volume_node)
        if not ctx.get("plane") and not ctx.get("slicer_slice_view"):
            return
        self._last_interaction_slice_context = dict(ctx)
        self._cached_slice_context = dict(ctx)
        segment_id = self._cached_segment_id or self._resolve_current_segment_id()
        if segment_id:
            self._pending_slice_contexts[segment_id] = dict(ctx)

    def _capture_editor_slice_context(self):
        ctx = capture_slice_context_at_cursor(self._volume_node)
        if ctx.get("plane") or ctx.get("slicer_slice_view"):
            return ctx
        if self._last_interaction_slice_context:
            return dict(self._last_interaction_slice_context)
        slicer_view = get_active_slice_view()
        if slicer_view and self._volume_node:
            return capture_slice_info_for_view(slicer_view, self._volume_node)
        return capture_slice_info(self._volume_node)

    def _install_editor_slice_tracking(self):
        """Track slice-view interactions during segment editing."""
        self._remove_editor_slice_tracking()
        self._editor_slice_observers = []
        try:
            import qt
            import vtk
            layout_manager = slicer.app.layoutManager()
            if not layout_manager:
                return

            for name in layout_manager.sliceViewNames():
                slice_widget = layout_manager.sliceWidget(name)
                if not slice_widget:
                    continue

                class _EditorSliceTracker(qt.QObject):
                    def __init__(self, tab, view_name):
                        super().__init__()
                        self._tab = tab
                        self._view_name = view_name

                    def eventFilter(self, obj, event):
                        if event.type() == qt.QEvent.MouseButtonPress:
                            self._tab._remember_slice_interaction(self._view_name)
                        elif event.type() == qt.QEvent.MouseMove:
                            if event.buttons() & qt.Qt.LeftButton:
                                self._tab._remember_slice_interaction(self._view_name)
                        return False

                tracker = _EditorSliceTracker(self, name)
                slice_widget.installEventFilter(tracker)
                self._editor_slice_observers.append((slice_widget, tracker))

                slice_view = slice_widget.sliceView()
                if not slice_view:
                    continue
                interactor = slice_view.interactor()
                if not interactor:
                    try:
                        interactor = slice_view.renderWindow().GetInteractor()
                    except Exception:
                        interactor = None
                if not interactor:
                    continue

                def _on_view_interaction(caller, event, view_name=name):
                    self._remember_slice_interaction(view_name)

                for event_id in (
                    vtk.vtkCommand.LeftButtonPressEvent,
                    vtk.vtkCommand.RightButtonPressEvent,
                    vtk.vtkCommand.MouseMoveEvent,
                ):
                    tag = interactor.AddObserver(event_id, _on_view_interaction)
                    self._editor_slice_observers.append((interactor, tag))
        except Exception as e:
            logger.warning(f"Could not install editor slice tracking: {e}")

    def _remove_editor_slice_tracking(self):
        for target, tag in getattr(self, "_editor_slice_observers", []):
            try:
                import qt
                if isinstance(tag, qt.QObject):
                    target.removeEventFilter(tag)
                else:
                    target.RemoveObserver(tag)
            except Exception:
                pass
        self._editor_slice_observers = []

    def _cache_editor_context(self):
        segment_id = self._resolve_current_segment_id()
        if segment_id:
            self._cached_segment_id = segment_id

        # Do not overwrite interaction-captured slice context during polling.
        if not self._last_interaction_slice_context:
            slice_info = self._capture_editor_slice_context()
            if slice_info.get("plane") or slice_info.get("slicer_slice_view"):
                self._cached_slice_context = dict(slice_info)

        effect_name = self._resolve_active_effect_name()
        if not effect_name or effect_name == "None":
            return
        self._cached_effect_name = effect_name
        effect = self._get_active_effect()
        if effect is not None:
            self._cached_effect_params = self._collect_effect_parameters(effect)
        else:
            self._cached_effect_params = self._collect_effect_parameters_for_name(effect_name)
        if self._cached_effect_params:
            self._effect_params_by_name[effect_name] = dict(self._cached_effect_params)

    def _poll_editor_context_and_changes(self):
        self._cache_editor_context()
        segment_id = self._cached_segment_id or self._resolve_current_segment_id()
        effect_name = self._cached_effect_name
        if not segment_id or not effect_name or effect_name == "None":
            return
        self._check_segment_modification(segment_id)

    def _get_segment_labelmap_mtime(self, segment_id):
        if self._segmentation_node is None or not segment_id:
            return 0
        try:
            import vtkSegmentationCore
            segmentation = self._segmentation_node.GetSegmentation()
            segment = segmentation.GetSegment(segment_id)
            if not segment:
                return 0
            repr_name = (
                vtkSegmentationCore.vtkSegmentationConverter
                .GetSegmentationBinaryLabelmapRepresentationName()
            )
            labelmap = segment.GetRepresentation(repr_name)
            if labelmap:
                return int(labelmap.GetMTime())
        except Exception as e:
            logger.debug(f"Could not read labelmap mtime for {segment_id}: {e}")
        return 0

    def _reset_modification_snapshots(self):
        self._segment_voxel_snapshots = {}
        self._segment_labelmap_mtimes = {}
        self._recorded_modification_mtimes = {}
        if self._segmentation_node is None:
            return
        segmentation = self._segmentation_node.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            segment_id = segmentation.GetNthSegmentID(i)
            count = self._compute_labelmap_metrics(segment_id).get("voxel_count", 0)
            self._segment_voxel_snapshots[segment_id] = int(count)
            self._segment_labelmap_mtimes[segment_id] = self._get_segment_labelmap_mtime(segment_id)

    def _update_modification_snapshot(self, segment_id, mtime, count):
        self._segment_labelmap_mtimes[segment_id] = mtime
        self._segment_voxel_snapshots[segment_id] = count

    def _check_all_segments_for_changes(self):
        """Check segments after a volume-scoped effect."""
        if self._segmentation_node is None:
            return
        self._cache_editor_context()
        segmentation = self._segmentation_node.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            self._check_segment_modification(segmentation.GetNthSegmentID(i))

    def _flush_pending_segment_changes(self):
        """Pick up any pending edit on the currently selected segment before export."""
        self._cache_editor_context()
        segment_id = self._cached_segment_id or self._resolve_current_segment_id()
        if segment_id:
            self._check_segment_modification(segment_id)

    def _resolve_modification_slice_context(self, segment_id, effect_name):
        slice_info = capture_slice_context_at_cursor(self._volume_node)
        if not slice_info.get("plane") and not slice_info.get("slicer_slice_view"):
            slice_info = (
                self._pending_slice_contexts.get(segment_id)
                or self._last_interaction_slice_context
                or self._cached_slice_context
                or self._capture_editor_slice_context()
            )
        normalized = self._normalize_slice_context(slice_info)
        if effect_name in VOLUME_SCOPED_EFFECTS:
            normalized["edit_scope"] = "volume"
        else:
            normalized["edit_scope"] = "plane"
        return normalized

    def _collect_modification_parameters(self, effect_name):
        params = dict(self._cached_effect_params)
        if not params:
            params = dict(self._effect_params_by_name.get(effect_name, {}))
        if not params:
            params = self._collect_effect_parameters_for_name(effect_name)
        common = self._collect_common_brush_parameters()
        if common:
            merged = dict(common)
            merged.update(params)
            params = merged
        return params

    def _check_segment_modification(self, segment_id):
        if not segment_id:
            return

        mtime = self._get_segment_labelmap_mtime(segment_id)
        count = int(self._compute_labelmap_metrics(segment_id).get("voxel_count", 0))
        previous_mtime = self._segment_labelmap_mtimes.get(segment_id)
        previous_count = self._segment_voxel_snapshots.get(segment_id)

        if previous_mtime is None:
            self._update_modification_snapshot(segment_id, mtime, count)
            return

        effect_name = self._cached_effect_name or self._resolve_active_effect_name()
        if not effect_name or effect_name == "None":
            effect_name = "SegmentEditor"

        selected_id = self._cached_segment_id or self._resolve_current_segment_id()
        if not should_record_segment_modification(
            effect_name,
            segment_id,
            selected_id,
            count,
            previous_count,
            mtime,
            previous_mtime,
        ):
            self._update_modification_snapshot(segment_id, mtime, count)
            return

        if mtime and self._recorded_modification_mtimes.get(segment_id) == mtime:
            self._update_modification_snapshot(segment_id, mtime, count)
            return

        params = self._collect_modification_parameters(effect_name)
        slice_context = self._resolve_modification_slice_context(segment_id, effect_name)

        self._append_modification_event(
            segment_id,
            effect_name,
            params,
            slice_context,
        )
        self._recorded_modification_mtimes[segment_id] = mtime
        self._update_modification_snapshot(segment_id, mtime, count)

    def _remove_segment_editor_observer(self):
        if self._segment_editor_node and self._segment_editor_observer:
            try:
                self._segment_editor_node.RemoveObserver(self._segment_editor_observer)
            except Exception:
                pass
        self._segment_editor_observer = None

    def _install_segment_editor_observer(self):
        self._remove_segment_editor_observer()
        if self._segment_editor_node is None:
            return

        def _on_editor_modified(caller, event):
            self._cache_editor_context()

        try:
            self._segment_editor_observer = self._segment_editor_node.AddObserver(
                slicer.vtkMRMLSegmentEditorNode.ModifiedEvent,
                _on_editor_modified,
            )
        except Exception as e:
            logger.warning(f"Could not install segment editor observer: {e}")

    def _remove_segmentation_observer(self):
        if self._segmentation_node and self._segmentation_observer:
            try:
                self._segmentation_node.RemoveObserver(self._segmentation_observer)
            except Exception:
                pass
        if self._segmentation_node and self._segmentation_core_observer:
            try:
                segmentation = self._segmentation_node.GetSegmentation()
                segmentation.RemoveObserver(self._segmentation_core_observer)
            except Exception:
                pass
        self._segmentation_observer = None
        self._segmentation_core_observer = None

    def _install_segmentation_observer(self):
        self._remove_segmentation_observer()
        if self._segmentation_node is None:
            return

        def _on_segment_modified(caller, event):
            self._on_segment_modified()

        try:
            self._segmentation_observer = self._segmentation_node.AddObserver(
                slicer.vtkMRMLSegmentationNode.SegmentModified,
                _on_segment_modified,
            )
            segmentation = self._segmentation_node.GetSegmentation()
            self._segmentation_core_observer = segmentation.AddObserver(
                segmentation.GetSegmentModifiedEvent(),
                _on_segment_modified,
            )
        except Exception as e:
            logger.warning(f"Could not install segmentation observer: {e}")

    def _effect_name(self, effect):
        if effect is None:
            return ""
        for attr in ("name", "Name"):
            value = getattr(effect, attr, None)
            if value:
                return str(value)
        try:
            return str(effect.objectName())
        except Exception:
            return ""

    def _get_active_effect(self):
        try:
            effect = self._segment_editor_widget.activeEffect()
            if effect:
                return effect
        except Exception:
            pass
        try:
            effect = self._segment_editor_widget.currentEffect()
            if effect:
                return effect
        except Exception:
            pass
        effect_name = self._resolve_active_effect_name()
        if effect_name and effect_name != "None":
            try:
                return self._segment_editor_widget.effectByName(effect_name)
            except Exception:
                pass
        return None

    def _resolve_active_effect_name(self):
        effect = None
        try:
            effect = self._segment_editor_widget.activeEffect()
        except Exception:
            pass
        name = self._effect_name(effect)
        if name and name != "None":
            return name
        if self._segment_editor_node:
            try:
                name = self._segment_editor_node.GetActiveEffectName()
                if name:
                    return str(name)
            except Exception:
                pass
        return self._cached_effect_name or ""

    def _parse_node_attribute_value(self, value):
        if value is None:
            return value
        text = str(value)
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def _resolve_current_segment_id(self):
        if self._segment_editor_node:
            try:
                segment_id = self._segment_editor_node.GetSelectedSegmentID()
                if segment_id:
                    return segment_id
            except Exception:
                pass
        for getter in (
            lambda: self._segment_editor_widget.currentSegmentID(),
            lambda: self._segment_editor_widget.currentSegmentID,
        ):
            try:
                segment_id = getter()
                if segment_id:
                    return segment_id
            except Exception:
                pass
        return self._cached_segment_id or ""

    def _collect_effect_parameters_for_name(self, effect_name):
        if not effect_name:
            return {}
        params = self._collect_effect_parameters_from_node(effect_name)
        if params:
            return params
        try:
            effect = self._segment_editor_widget.effectByName(effect_name)
            if effect:
                return self._collect_effect_parameters(effect)
        except Exception:
            pass
        return {}

    def _read_effect_parameter(self, effect, name):
        for getter_name in (
            "doubleParameter",
            "integerParameter",
            "parameter",
            "stringParameter",
        ):
            try:
                getter = getattr(effect, getter_name)
                value = getter(name) if callable(getter) else None
                if value is not None and value != "":
                    return value
            except Exception:
                pass
        return None

    def _collect_effect_parameters(self, effect):
        params = {}
        if effect is None:
            return params

        names = []
        for names_attr in ("parameterNames", "ParameterNames"):
            try:
                value = getattr(effect, names_attr, None)
                if value:
                    names = list(value() if callable(value) else value)
                    break
            except Exception:
                pass

        if not names:
            for method_name in (
                "integerParameterNames",
                "doubleParameterNames",
                "stringParameterNames",
            ):
                try:
                    method = getattr(effect, method_name, None)
                    if method:
                        extra = list(method() if callable(method) else method)
                        names.extend(extra)
                except Exception:
                    pass

        for name in dict.fromkeys(names):
            value = self._read_effect_parameter(effect, name)
            if value is not None:
                params[name] = value

        if not params:
            effect_name = self._effect_name(effect)
            if effect_name:
                params = self._collect_effect_parameters_from_node(effect_name)
        return params

    def _iter_node_attribute_names(self, node):
        try:
            import vtk
            attr_names = vtk.vtkStringArray()
            node.GetAttributeNames(attr_names)
            for i in range(attr_names.GetNumberOfValues()):
                yield attr_names.GetValue(i)
            return
        except Exception:
            pass
        try:
            names = node.GetAttributeNames()
        except Exception:
            return
        if not names:
            return
        if hasattr(names, "GetNumberOfValues"):
            for i in range(names.GetNumberOfValues()):
                yield names.GetValue(i)
            return
        for name in names:
            yield name

    def _collect_common_brush_parameters(self):
        params = {}
        node = self._segment_editor_node
        if not node:
            return params
        for param_name in COMMON_BRUSH_PARAMS:
            value = node.GetAttribute(param_name)
            if value is not None and value != "":
                params[param_name] = self._parse_node_attribute_value(value)
        effect = self._get_active_effect()
        if effect is None:
            return params
        for getter_name in ("doubleParameter", "integerParameter", "parameter", "stringParameter"):
            for param_name in COMMON_BRUSH_PARAMS:
                if param_name in params:
                    continue
                try:
                    getter = getattr(effect, getter_name)
                    value = getter(param_name) if callable(getter) else None
                    if value is not None and value != "":
                        params[param_name] = value
                except Exception:
                    pass
        return params

    def _collect_effect_parameters_from_node(self, effect_name):
        params = {}
        node = self._segment_editor_node
        if not effect_name or not node:
            return params
        prefix = f"{effect_name}."
        for full_name in self._iter_node_attribute_names(node):
            if full_name.startswith(prefix):
                param_name = full_name[len(prefix):]
                params[param_name] = self._parse_node_attribute_value(
                    node.GetAttribute(full_name)
                )
        if not params:
            for param_name in EFFECT_KNOWN_PARAMS.get(effect_name, []):
                value = node.GetAttribute(f"{prefix}{param_name}")
                if value is not None and value != "":
                    params[param_name] = self._parse_node_attribute_value(value)
        return params

    def _segment_display_name(self, segment_id):
        if not segment_id or self._segmentation_node is None:
            return segment_id or ""
        segment = self._segmentation_node.GetSegmentation().GetSegment(segment_id)
        if segment:
            return segment.GetName()
        return segment_id

    def _append_modification_event(self, segment_id, effect_name, params, slice_context):
        if not segment_id or not effect_name:
            return

        normalized_slice = self._normalize_slice_context(slice_context)
        if normalized_slice.get("edit_scope") is None:
            normalized_slice["edit_scope"] = (
                "volume" if effect_name in VOLUME_SCOPED_EFFECTS else "plane"
            )

        event = SegmentModificationEvent(
            effect_name=effect_name,
            segment_id=segment_id,
            segment_name=self._segment_display_name(segment_id),
            slice_context=normalized_slice,
            effect_parameters=dict(params or {}),
        )
        self._modification_events.append(event)
        self._segment_effect_summary[segment_id] = {
            "effect_name": effect_name,
            "effect_parameters": dict(params or {}),
            "slice_context": dict(normalized_slice),
            "timestamp": event.timestamp,
        }
        self._pending_slice_contexts.pop(segment_id, None)

    def _on_segment_modified(self):
        self._cache_editor_context()
        ctx = capture_slice_context_at_cursor(self._volume_node)
        if ctx.get("plane") or ctx.get("slicer_slice_view"):
            self._last_interaction_slice_context = dict(ctx)
            segment_id = self._cached_segment_id or self._resolve_current_segment_id()
            if segment_id:
                self._pending_slice_contexts[segment_id] = dict(ctx)
        effect_name = self._cached_effect_name or self._resolve_active_effect_name()
        if effect_name in VOLUME_SCOPED_EFFECTS:
            self._check_all_segments_for_changes()
            return
        segment_id = self._cached_segment_id or self._resolve_current_segment_id()
        if segment_id:
            self._check_segment_modification(segment_id)

    def _record_modification_event(self):
        self._cache_editor_context()
        self._on_segment_modified()

    def _collect_editor_state(self):
        self._cache_editor_context()
        effect = self._get_active_effect()
        slice_context = self._normalize_slice_context(
            capture_slice_context_at_cursor(self._volume_node)
            or self._last_interaction_slice_context
            or self._cached_slice_context
        )
        state = {
            "active_effect": self._effect_name(effect) or self._cached_effect_name,
            "current_segment_id": self._resolve_current_segment_id(),
            "slice_context": slice_context,
        }
        if effect:
            state["effect_parameters"] = self._collect_effect_parameters(effect)
        elif self._cached_effect_params:
            state["effect_parameters"] = dict(self._cached_effect_params)
        common = self._collect_common_brush_parameters()
        if common:
            merged = dict(common)
            merged.update(state.get("effect_parameters", {}))
            state["effect_parameters"] = merged
        return state

    def _extent_ijk_to_bounds_ras(self, extent_ijk):
        if not extent_ijk or len(extent_ijk) != 6 or self._volume_node is None:
            return []
        try:
            import vtk
            ijk_to_ras = vtk.vtkMatrix4x4()
            self._volume_node.GetIJKToRASMatrix(ijk_to_ras)
            corners = []
            for i in (extent_ijk[0], extent_ijk[1]):
                for j in (extent_ijk[2], extent_ijk[3]):
                    for k in (extent_ijk[4], extent_ijk[5]):
                        inp = [float(i), float(j), float(k), 1.0]
                        out = [0.0, 0.0, 0.0, 0.0]
                        ijk_to_ras.MultiplyPoint(inp, out)
                        corners.append(out[:3])
            xs = [point[0] for point in corners]
            ys = [point[1] for point in corners]
            zs = [point[2] for point in corners]
            return [min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)]
        except Exception as e:
            logger.warning(f"Could not convert IJK extent to RAS bounds: {e}")
            return []

    def _compute_labelmap_metrics(self, segment_id):
        metrics = {
            "voxel_count": 0,
            "extent_ijk": [],
            "bounds_ras": [],
            "center_ras": [],
            "center_voxel_ijk": [],
            "volume_mm3": 0.0,
        }
        if self._segmentation_node is None or self._volume_node is None:
            return metrics
        try:
            import numpy as np
            arr = slicer.util.arrayFromSegmentBinaryLabelmap(
                self._segmentation_node, segment_id, self._volume_node
            )
            count = int(np.count_nonzero(arr))
            metrics["voxel_count"] = count
            if count == 0:
                return metrics

            nz = np.nonzero(arr)
            extent = [
                int(nz[0].min()), int(nz[0].max()),
                int(nz[1].min()), int(nz[1].max()),
                int(nz[2].min()), int(nz[2].max()),
            ]
            metrics["extent_ijk"] = extent
            metrics["bounds_ras"] = self._extent_ijk_to_bounds_ras(extent)
            if metrics["bounds_ras"]:
                bounds = metrics["bounds_ras"]
                metrics["center_ras"] = [
                    (bounds[0] + bounds[1]) / 2.0,
                    (bounds[2] + bounds[3]) / 2.0,
                    (bounds[4] + bounds[5]) / 2.0,
                ]
            metrics["center_voxel_ijk"] = [
                int((extent[0] + extent[1]) / 2),
                int((extent[2] + extent[3]) / 2),
                int((extent[4] + extent[5]) / 2),
            ]
            spacing = self._volume_node.GetSpacing()
            metrics["volume_mm3"] = count * spacing[0] * spacing[1] * spacing[2]
        except Exception as e:
            logger.warning(f"Could not compute labelmap metrics for {segment_id}: {e}")
        return metrics

    def _compute_segment_ijk_extent(self, segment_id):
        return self._compute_labelmap_metrics(segment_id).get("extent_ijk", [])

    def _build_segment_spatial_extent(self, segment_id, stats, segment_name, labelmap_metrics):
        prefix = f"{segment_id}.LabelmapSegmentStatisticsPlugin"
        extent = SegmentSpatialExtent()

        def _stat_float(key):
            value = stats.get(f"{prefix}.{key}")
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        extent.volume_mm3 = _stat_float("volume_mm3") or float(labelmap_metrics.get("volume_mm3", 0.0))
        extent.surface_area_mm2 = _stat_float("surface_area_mm2")

        for key, attr in (
            ("obb_origin_ras", "oriented_bounding_box_origin_ras"),
            ("obb_diameter_mm", "oriented_bounding_box_diameter_mm"),
        ):
            value = stats.get(f"{prefix}.{key}")
            if value is not None:
                setattr(extent, attr, list(value) if not isinstance(value, list) else value)

        extent.extent_ijk = list(labelmap_metrics.get("extent_ijk", []))
        extent.bounds_ras = list(labelmap_metrics.get("bounds_ras", []))
        extent.center_ras = list(labelmap_metrics.get("center_ras", []))
        extent.center_voxel_ijk = list(labelmap_metrics.get("center_voxel_ijk", []))

        if not any([
            extent.bounds_ras,
            extent.extent_ijk,
            extent.volume_mm3,
            extent.surface_area_mm2,
        ]):
            return None
        return extent

    def _events_for_segment(self, segment_id, segment_name=""):
        return [
            event for event in self._modification_events
            if event.segment_id == segment_id
            or event.segment_name == segment_name
            or (segment_name and event.segment_id == segment_name)
        ]

    def _apply_effect_summary(self, lbl):
        if lbl.modification_events:
            return
        summary = (
            self._segment_effect_summary.get(lbl.segment_id)
            or self._segment_effect_summary.get(lbl.name)
        )
        if not summary:
            return
        event = SegmentModificationEvent(
            effect_name=summary.get("effect_name", ""),
            segment_id=lbl.segment_id,
            segment_name=lbl.name,
            slice_context=summary.get("slice_context", {}),
            effect_parameters=summary.get("effect_parameters", {}),
        )
        if summary.get("timestamp"):
            event.timestamp = summary["timestamp"]
        lbl.modification_events = [event]
        lbl.last_effect_name = summary.get("effect_name", "")
        lbl.last_effect_parameters = dict(summary.get("effect_parameters", {}))

    # ─── Public API ──────────────────────────────────────────────────────

    def get_segmentation_data(self):
        """Collect current segmentation metadata into a SegmentationData object."""
        self._flush_pending_segment_changes()
        data = SegmentationData()

        if self._segmentation_node:
            data.segmentation_node_id = self._segmentation_node.GetID()
            segmentation = self._segmentation_node.GetSegmentation()

            for i in range(segmentation.GetNumberOfSegments()):
                segment_id = segmentation.GetNthSegmentID(i)
                segment = segmentation.GetSegment(segment_id)
                color_arr = segment.GetColor()
                lbl = SegmentLabel(
                    name=segment.GetName(),
                    color=rgb_float_to_hex(color_arr[0], color_arr[1], color_arr[2]),
                    segment_id=segment_id,
                )
                data.labels.append(lbl)

        if self._volume_node:
            data.source_volume_node_id = self._volume_node.GetID()
            data.source_volume_name = self._volume_node.GetName()

        data.label_to_segment_map = dict(self._label_to_segment_map)

        if hasattr(self, "_last_export_filepath"):
            data.export_filepath = self._last_export_filepath
            data.export_format = self._last_export_format

        segment_stats, full_stats = self._compute_stats(data)

        config_by_name = {label_def.name: label_def for label_def in self._seg_labels}
        for lbl in data.labels:
            labelmap_metrics = self._compute_labelmap_metrics(lbl.segment_id)
            lbl.voxel_count = int(labelmap_metrics.get("voxel_count", 0))
            if lbl.voxel_count == 0:
                lbl.voxel_count = int(data.per_label_voxel_counts.get(lbl.name, 0))
            if lbl.voxel_count == 0 and lbl.segment_id in segment_stats:
                lbl.voxel_count = int(segment_stats[lbl.segment_id].get("voxel_count", 0) or 0)

            label_def = config_by_name.get(lbl.name)
            if label_def:
                lbl.label_config_id = label_def.id
                lbl.description = label_def.description

            self._apply_effect_summary(lbl)
            seg_events = self._events_for_segment(lbl.segment_id, lbl.name)
            lbl.modification_events = seg_events
            if seg_events:
                last_event = seg_events[-1]
                lbl.last_effect_name = last_event.effect_name
                lbl.last_effect_parameters = dict(last_event.effect_parameters)
            else:
                lbl.last_effect_name = ""
                lbl.last_effect_parameters = {}

            lbl.spatial_extent = self._build_segment_spatial_extent(
                lbl.segment_id, full_stats, lbl.name, labelmap_metrics
            )
        return data

    def _compute_stats(self, data):
        """Compute voxel counts and rich statistics per segment."""
        if self._segmentation_node is None or self._volume_node is None:
            return {}, {}

        per_segment = {}
        full_stats = {}
        try:
            import SegmentStatistics
            logic = SegmentStatistics.SegmentStatisticsLogic()
            param_node = logic.getParameterNode()
            param_node.SetParameter("Segmentation", self._segmentation_node.GetID())
            param_node.SetParameter("ScalarVolume", self._volume_node.GetID())
            for metric in (
                "voxel_count",
                "volume_mm3",
                "surface_area_mm2",
                "obb_origin_ras",
                "obb_diameter_mm",
            ):
                param_node.SetParameter(
                    f"LabelmapSegmentStatisticsPlugin.{metric}.enabled", "True"
                )
            logic.computeStatistics()
            stats = logic.getStatistics()
            full_stats = dict(stats)

            total = 0
            segmentation = self._segmentation_node.GetSegmentation()
            prefix = "LabelmapSegmentStatisticsPlugin"
            for i in range(segmentation.GetNumberOfSegments()):
                seg_id = segmentation.GetNthSegmentID(i)
                segment = segmentation.GetSegment(seg_id)
                seg_name = segment.GetName() if segment else seg_id
                seg_stats = {"segment_name": seg_name}
                for metric in (
                    "voxel_count",
                    "volume_mm3",
                    "surface_area_mm2",
                    "obb_origin_ras",
                    "obb_diameter_mm",
                ):
                    key = f"{seg_id}.{prefix}.{metric}"
                    if key in stats:
                        seg_stats[metric] = stats[key]

                count = int(seg_stats.get("voxel_count", 0) or 0)
                if count == 0:
                    count = self._compute_labelmap_metrics(seg_id).get("voxel_count", 0)
                seg_stats["voxel_count"] = count
                data.per_label_voxel_counts[seg_name] = count
                per_segment[seg_id] = seg_stats
                total += count

            if total == 0:
                for lbl in data.labels:
                    count = self._compute_labelmap_metrics(lbl.segment_id).get("voxel_count", 0)
                    if count:
                        data.per_label_voxel_counts[lbl.name] = count
                        total += count

            data.total_voxel_count = total
        except Exception as e:
            logger.warning(f"Could not compute segment statistics: {e}")
            total = 0
            for lbl in data.labels:
                count = self._compute_labelmap_metrics(lbl.segment_id).get("voxel_count", 0)
                if count:
                    data.per_label_voxel_counts[lbl.name] = count
                    per_segment[lbl.segment_id] = {"voxel_count": count}
                    total += count
            data.total_voxel_count = total
        return per_segment, full_stats

    def load_segmentation(self, seg_data):
        """Load a SegmentationData object: import mask file or create from labels."""
        self._last_import_error = ""
        if seg_data is None:
            return True

        volume_node = self._volume_node

        if seg_data.export_filepath:
            if os.path.exists(seg_data.export_filepath):
                try:
                    if self._segmentation_node:
                        try:
                            slicer.mrmlScene.RemoveNode(self._segmentation_node)
                        except Exception:
                            pass
                        self._segmentation_node = None

                    if seg_data.export_filepath.lower().endswith(".seg.nrrd"):
                        self._load_segmentation_from_seg_nrrd(
                            seg_data.export_filepath, volume_node
                        )
                    else:
                        labelmap_node = slicer.util.loadLabelVolume(seg_data.export_filepath)
                        self._segmentation_node = slicer.mrmlScene.AddNewNodeByClass(
                            "vtkMRMLSegmentationNode"
                        )
                        self._segmentation_node.CreateDefaultDisplayNodes()
                        self._segmentation_node.SetName("AnnotationSegmentation")

                        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                            labelmap_node, self._segmentation_node
                        )
                        slicer.mrmlScene.RemoveNode(labelmap_node)

                        if volume_node:
                            self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
                                volume_node
                            )
                        self._install_segmentation_observer()
                        display_node = self._segmentation_node.GetDisplayNode()
                        if display_node:
                            display_node.SetVisibility(True)
                            display_node.SetAllSegmentsVisibility(True)
                            display_node.SetOpacity(self._opacity_slider.value / 100.0)
                        self._link_editor_to_nodes(volume_node)
                except Exception as e:
                    self._last_import_error = str(e)
                    logger.error(f"Failed to load segmentation mask: {e}")
                    return False
            else:
                self._last_import_error = (
                    f"Segmentation file not found: {seg_data.export_filepath}"
                )
                return False

        if self._segmentation_node is None:
            self._ensure_segmentation_node(volume_node)

        if self._segmentation_node and seg_data.labels:
            segmentation = self._segmentation_node.GetSegmentation()
            for lbl in seg_data.labels:
                if not segmentation.GetSegment(lbl.segment_id):
                    r, g, b = hex_to_rgb_float(lbl.color)
                    segmentation.AddEmptySegment(lbl.name, lbl.name, [r, g, b])

        if self._segmentation_node and seg_data.labels:
            segmentation = self._segmentation_node.GetSegmentation()
            for lbl in seg_data.labels:
                segment = segmentation.GetSegment(lbl.segment_id)
                if segment:
                    segment.SetName(lbl.name)
                    r, g, b = hex_to_rgb_float(lbl.color)
                    segment.SetColor(r, g, b)

        if self._segmentation_node:
            self._link_editor_to_nodes(volume_node)
        self._start_context_timer()

        self._modification_events = list(seg_data.modification_events or [])
        self._segment_effect_summary = {}
        for event in self._modification_events:
            self._segment_effect_summary[event.segment_id] = {
                "effect_name": event.effect_name,
                "effect_parameters": dict(event.effect_parameters),
                "slice_context": dict(event.slice_context),
                "timestamp": event.timestamp,
            }

        self._select_first_segment()
        self._reset_modification_snapshots()

        return True

    def deactivate_effect(self):
        """Stop the active painting effect."""
        try:
            self._segment_editor_widget.setActiveEffectByName("None")
        except Exception:
            pass

    def cleanup(self):
        """Remove temporary parameter nodes. Called on module unload."""
        self.deactivate_effect()
        self._stop_context_timer()
        self._remove_segmentation_observer()
        self._remove_segment_editor_observer()
        self._remove_editor_slice_tracking()
        if self._segment_editor_node:
            try:
                slicer.mrmlScene.RemoveNode(self._segment_editor_node)
            except Exception:
                pass
            self._segment_editor_node = None
