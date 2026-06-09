"""
Segmentation tab: pixel-level painting using Slicer's Segment Editor.
Embeds qMRMLSegmentEditorWidget with export controls and opacity adjustment.
The source volume and segment classes are set externally by the panel.
"""
import time
import qt
import slicer
import logging

from AnnotationModel import (
    SegmentationData,
    SegmentLabel,
    SegmentSpatialExtent,
    SegmentModificationEvent,
)
from SliceInfo import capture_slice_info

logger = logging.getLogger(__name__)

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
    "Scissors": [
        "Operation",
        "Shape",
    ],
    "Islands": [
        "Operation",
        "MinimumSize",
    ],
}


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
        self._last_event_key = None
        self._last_event_time = 0.0
        self._cached_effect_name = ""
        self._cached_effect_params = {}
        self._cached_segment_id = ""
        self._segment_effect_summary = {}
        self._segment_voxel_snapshots = {}
        self._effect_params_by_name = {}
        self._context_timer = None
        self._segment_editor_observer = None
        self._setup_ui()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)
        self._build_segment_editor(layout)
        self._build_export_section(layout)

    def _build_segment_editor(self, parent_layout):
        frame = qt.QFrame()
        frame.setFrameShape(qt.QFrame.StyledPanel)
        fl = qt.QVBoxLayout(frame)

        self._segment_editor_widget = slicer.qMRMLSegmentEditorWidget()
        self._segment_editor_widget.setMRMLScene(slicer.mrmlScene)
        self._segment_editor_widget.setEffectNameOrder([
            "Paint", "Erase", "Threshold", "Islands", "Scissors"
        ])
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

        opacity_row = qt.QHBoxLayout()
        opacity_row.addWidget(qt.QLabel("Overlay opacity:"))
        self._opacity_slider = qt.QSlider(qt.Qt.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self._opacity_slider)
        fl.addLayout(opacity_row)

        parent_layout.addWidget(frame)

    def _build_export_section(self, parent_layout):
        frame = qt.QFrame()
        frame.setFrameShape(qt.QFrame.StyledPanel)
        fl = qt.QVBoxLayout(frame)

        self._stats_label = qt.QLabel("Total segmented voxels: 0")
        fl.addWidget(self._stats_label)

        btn_row = qt.QHBoxLayout()
        self._export_nrrd_btn = qt.QPushButton("Export Segmentation (NRRD)")
        self._export_nrrd_btn.clicked.connect(lambda: self._on_export("nrrd"))
        btn_row.addWidget(self._export_nrrd_btn)

        self._export_nifti_btn = qt.QPushButton("Export Segmentation (NIfTI)")
        self._export_nifti_btn.clicked.connect(lambda: self._on_export("nifti"))
        btn_row.addWidget(self._export_nifti_btn)

        btn_row.addStretch()
        fl.addLayout(btn_row)

        parent_layout.addWidget(frame)

    # ─── Volume Binding (called by panel) ────────────────────────────────

    def set_volume(self, volume_node):
        """Bind a shared volume as the source for segmentation."""
        self._volume_node = volume_node
        self._ensure_segmentation_node(volume_node)
        self._link_editor_to_nodes(volume_node)
        if self._seg_labels:
            self._create_segments_from_config()
        self._start_context_timer()

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
        self._effect_params_by_name = {}
        self._stop_context_timer()
        self._remove_segmentation_observer()
        self._remove_segment_editor_observer()
        self._stats_label.setText("Total segmented voxels: 0")

    # ─── Label Config (called by panel) ──────────────────────────────────

    def set_labels(self, labels):
        """Receive segmentation class labels from config. Creates segments if volume exists."""
        self._seg_labels = list(labels)
        if self._segmentation_node:
            self._create_segments_from_config()

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
        self._refresh_stats()

    def _refresh_stats(self):
        """Recompute and display voxel statistics after segment changes."""
        if self._segmentation_node is None:
            self._stats_label.setText("Total segmented voxels: 0")
            return
        data = SegmentationData()
        self._compute_stats(data)

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
        self._reset_voxel_snapshots()

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

        self._segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        self._install_segmentation_observer()

        display_node = self._segmentation_node.GetDisplayNode()
        if display_node:
            display_node.SetVisibility(True)
            display_node.SetAllSegmentsVisibility(True)
            display_node.SetOpacity(self._opacity_slider.value / 100.0)

    def _link_editor_to_nodes(self, volume_node):
        """Connect the segment editor widget to the segmentation and volume."""
        if self._segment_editor_node is None:
            self._segment_editor_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentEditorNode"
            )

        self._segment_editor_widget.setMRMLSegmentEditorNode(self._segment_editor_node)
        self._segment_editor_widget.setSegmentationNode(self._segmentation_node)
        self._install_segment_editor_observer()

        try:
            self._segment_editor_widget.setSourceVolumeNode(volume_node)
        except AttributeError:
            try:
                self._segment_editor_widget.setMasterVolumeNode(volume_node)
            except AttributeError:
                logger.warning("Could not set source volume on segment editor widget")

    # ─── Opacity ─────────────────────────────────────────────────────────

    def _on_opacity_changed(self, value):
        if self._segmentation_node:
            display_node = self._segmentation_node.GetDisplayNode()
            if display_node:
                display_node.SetOpacity(value / 100.0)

    # ─── Export ──────────────────────────────────────────────────────────

    def _on_export(self, fmt):
        if self._segmentation_node is None:
            qt.QMessageBox.warning(self, "No Segmentation", "No segmentation to export.")
            return
        if self._volume_node is None:
            qt.QMessageBox.warning(self, "No Volume", "No source volume loaded.")
            return

        if fmt == "nrrd":
            ext_filter = "NRRD (*.nrrd)"
        else:
            ext_filter = "NIfTI (*.nii.gz)"

        filepath = qt.QFileDialog.getSaveFileName(self, "Export Segmentation", "", ext_filter)
        if not filepath:
            return

        success = self.export_mask_to_file(filepath, fmt)
        if success:
            self._last_export_filepath = filepath
            self._last_export_format = fmt

    def export_mask_to_file(self, filepath, fmt="nrrd"):
        """Export the segmentation labelmap to a file. Returns True on success."""
        if self._segmentation_node is None or self._volume_node is None:
            return False

        labelmap_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        try:
            slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                self._segmentation_node, labelmap_node, self._volume_node
            )
            slicer.util.saveNode(labelmap_node, filepath)
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
        finally:
            slicer.mrmlScene.RemoveNode(labelmap_node)

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

    def _cache_editor_context(self):
        segment_id = self._resolve_current_segment_id()
        if segment_id:
            self._cached_segment_id = segment_id

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
        self._check_segment_voxel_change(segment_id)

    def _reset_voxel_snapshots(self):
        self._segment_voxel_snapshots = {}
        if self._segmentation_node is None:
            return
        segmentation = self._segmentation_node.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            segment_id = segmentation.GetNthSegmentID(i)
            count = self._compute_labelmap_metrics(segment_id).get("voxel_count", 0)
            self._segment_voxel_snapshots[segment_id] = int(count)

    def _check_all_segments_for_changes(self):
        if self._segmentation_node is None:
            return
        self._cache_editor_context()
        segmentation = self._segmentation_node.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            self._check_segment_voxel_change(segmentation.GetNthSegmentID(i))

    def _check_segment_voxel_change(self, segment_id):
        if not segment_id:
            return
        count = int(self._compute_labelmap_metrics(segment_id).get("voxel_count", 0))
        previous = self._segment_voxel_snapshots.get(segment_id)
        if previous is None:
            self._segment_voxel_snapshots[segment_id] = count
            return
        if count == previous:
            return

        effect_name = self._cached_effect_name or self._resolve_active_effect_name()
        if not effect_name or effect_name == "None":
            effect_name = "SegmentEditor"
        params = dict(self._cached_effect_params)
        if not params:
            params = dict(self._effect_params_by_name.get(effect_name, {}))
        if not params:
            params = self._collect_effect_parameters_for_name(effect_name)

        self._append_modification_event(
            segment_id,
            effect_name,
            params,
            capture_slice_info(self._volume_node),
        )
        self._segment_voxel_snapshots[segment_id] = count

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

        now = time.time()
        debounce_key = (segment_id, effect_name)
        if debounce_key == self._last_event_key and (now - self._last_event_time) < 2.0:
            return
        self._last_event_key = debounce_key
        self._last_event_time = now

        event = SegmentModificationEvent(
            effect_name=effect_name,
            segment_id=segment_id,
            segment_name=self._segment_display_name(segment_id),
            slice_context=dict(slice_context or {}),
            effect_parameters=dict(params or {}),
        )
        self._modification_events.append(event)
        self._segment_effect_summary[segment_id] = {
            "effect_name": effect_name,
            "effect_parameters": dict(params or {}),
            "slice_context": dict(slice_context or {}),
            "timestamp": event.timestamp,
        }

    def _on_segment_modified(self):
        self._check_all_segments_for_changes()

    def _record_modification_event(self):
        self._cache_editor_context()
        self._on_segment_modified()

    def _collect_editor_state(self):
        self._cache_editor_context()
        effect = self._get_active_effect()
        state = {
            "active_effect": self._effect_name(effect) or self._cached_effect_name,
            "current_segment_id": self._resolve_current_segment_id(),
            "slice_context": capture_slice_info(self._volume_node),
        }
        if effect:
            state["effect_parameters"] = self._collect_effect_parameters(effect)
        elif self._cached_effect_params:
            state["effect_parameters"] = dict(self._cached_effect_params)
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
        self._check_all_segments_for_changes()
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
        data.modification_events = list(self._modification_events)
        data.editor_state_at_export = self._collect_editor_state()

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
            self._stats_label.setText(f"Total segmented voxels: {total:,}")
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
            if total:
                self._stats_label.setText(f"Total segmented voxels: {total:,}")
        return per_segment, full_stats

    def load_segmentation(self, seg_data):
        """Load a SegmentationData object: import mask file or create from labels."""
        if seg_data is None:
            return

        volume_node = self._volume_node

        if seg_data.export_filepath:
            import os
            if os.path.exists(seg_data.export_filepath):
                try:
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
                except Exception as e:
                    logger.error(f"Failed to load segmentation mask: {e}")

        if self._segmentation_node is None and volume_node:
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

        if volume_node:
            self._link_editor_to_nodes(volume_node)
        self._start_context_timer()

        self._select_first_segment()

        if seg_data.total_voxel_count > 0:
            self._stats_label.setText(f"Total segmented voxels: {seg_data.total_voxel_count:,}")

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
        if self._segment_editor_node:
            try:
                slicer.mrmlScene.RemoveNode(self._segment_editor_node)
            except Exception:
                pass
            self._segment_editor_node = None
