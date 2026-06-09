"""
Segmentation tab: pixel-level painting using Slicer's Segment Editor.
Embeds qMRMLSegmentEditorWidget and wraps it with label management,
export controls, and opacity adjustment. The source volume is set
externally by the panel (shared volume binding). Segment labels are
provided by the configuration screen — no add/delete here.
"""
import qt
import slicer
import logging

from AnnotationModel import SegmentationData, SegmentLabel

logger = logging.getLogger(__name__)


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
        self._setup_ui()

    # ─── UI Setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)

        self._build_label_manager(layout)
        self._build_segment_editor(layout)
        self._build_export_section(layout)

    def _build_label_manager(self, parent_layout):
        frame = qt.QFrame()
        frame.setFrameShape(qt.QFrame.StyledPanel)
        fl = qt.QVBoxLayout(frame)

        heading = qt.QLabel("Segment Labels")
        heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        fl.addWidget(heading)

        self._segment_table = qt.QTableWidget()
        self._segment_table.setColumnCount(3)
        self._segment_table.setHorizontalHeaderLabels(["Color", "Name", "Visible"])
        self._segment_table.horizontalHeader().setStretchLastSection(True)
        self._segment_table.setSelectionBehavior(qt.QTableWidget.SelectRows)
        self._segment_table.setEditTriggers(qt.QTableWidget.NoEditTriggers)
        fl.addWidget(self._segment_table)

        active_row = qt.QHBoxLayout()
        active_row.addWidget(qt.QLabel("Active segment:"))
        self._active_segment_combo = qt.QComboBox()
        self._active_segment_combo.currentIndexChanged.connect(self._on_active_segment_changed)
        active_row.addWidget(self._active_segment_combo)
        active_row.addStretch()
        fl.addLayout(active_row)

        parent_layout.addWidget(frame)

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

        self._stats_label = qt.QLabel("Total labeled voxels: 0")
        fl.addWidget(self._stats_label)

        btn_row = qt.QHBoxLayout()
        self._export_nrrd_btn = qt.QPushButton("Export Mask as NRRD")
        self._export_nrrd_btn.clicked.connect(lambda: self._on_export("nrrd"))
        btn_row.addWidget(self._export_nrrd_btn)

        self._export_nifti_btn = qt.QPushButton("Export Mask as NIfTI")
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
        self._segment_table.setRowCount(0)
        self._active_segment_combo.clear()
        self._stats_label.setText("Total labeled voxels: 0")

    # ─── Label Config (called by panel) ──────────────────────────────────

    def set_labels(self, labels):
        """Receive segmentation class labels from config. Creates segments if volume exists."""
        self._seg_labels = list(labels)
        if self._segmentation_node:
            self._create_segments_from_config()

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

        self._refresh_segment_table()
        self._refresh_active_combo()

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

        try:
            self._segment_editor_widget.setSourceVolumeNode(volume_node)
        except AttributeError:
            try:
                self._segment_editor_widget.setMasterVolumeNode(volume_node)
            except AttributeError:
                logger.warning("Could not set source volume on segment editor widget")

    # ─── Segment Table (read-only for label management) ───────────────────

    def _on_active_segment_changed(self, index):
        if index < 0 or self._segmentation_node is None:
            return
        segment_id = self._active_segment_combo.itemData(index)
        if segment_id:
            self._segment_editor_widget.setCurrentSegmentID(segment_id)

    def _refresh_segment_table(self):
        """Rebuild the segment table from the segmentation node."""
        if self._segmentation_node is None:
            self._segment_table.setRowCount(0)
            return

        segmentation = self._segmentation_node.GetSegmentation()
        num_segments = segmentation.GetNumberOfSegments()
        self._segment_table.setRowCount(num_segments)

        for row in range(num_segments):
            segment_id = segmentation.GetNthSegmentID(row)
            segment = segmentation.GetSegment(segment_id)
            color_arr = segment.GetColor()
            hex_color = rgb_float_to_hex(color_arr[0], color_arr[1], color_arr[2])

            color_item = qt.QTableWidgetItem("")
            color_item.setBackground(qt.QColor(hex_color))
            self._segment_table.setItem(row, 0, color_item)

            self._segment_table.setItem(row, 1, qt.QTableWidgetItem(segment.GetName()))

            vis_widget = qt.QWidget()
            vis_layout = qt.QHBoxLayout(vis_widget)
            vis_layout.setContentsMargins(4, 0, 4, 0)
            vis_cb = qt.QCheckBox()
            vis_cb.setChecked(True)
            display_node = self._segmentation_node.GetDisplayNode()
            if display_node:
                vis_cb.setChecked(display_node.GetSegmentVisibility(segment_id))
            vis_cb.toggled.connect(
                lambda checked, sid=segment_id: self._on_visibility_toggled(sid, checked)
            )
            vis_layout.addWidget(vis_cb)
            self._segment_table.setCellWidget(row, 2, vis_widget)

    def _refresh_active_combo(self):
        """Rebuild the active segment combo box."""
        self._active_segment_combo.blockSignals(True)
        self._active_segment_combo.clear()

        if self._segmentation_node:
            segmentation = self._segmentation_node.GetSegmentation()
            for i in range(segmentation.GetNumberOfSegments()):
                segment_id = segmentation.GetNthSegmentID(i)
                segment = segmentation.GetSegment(segment_id)
                self._active_segment_combo.addItem(segment.GetName(), segment_id)

        self._active_segment_combo.blockSignals(False)

        if self._active_segment_combo.count > 0:
            self._active_segment_combo.setCurrentIndex(0)
            self._on_active_segment_changed(0)

    def _on_visibility_toggled(self, segment_id, visible):
        if self._segmentation_node:
            display_node = self._segmentation_node.GetDisplayNode()
            if display_node:
                display_node.SetSegmentVisibility(segment_id, visible)

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

    # ─── Public API ──────────────────────────────────────────────────────

    def get_segmentation_data(self):
        """Collect current segmentation metadata into a SegmentationData object."""
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

        if hasattr(self, "_last_export_filepath"):
            data.export_filepath = self._last_export_filepath
            data.export_format = self._last_export_format

        self._compute_stats(data)
        return data

    def _compute_stats(self, data):
        """Compute voxel counts per segment."""
        if self._segmentation_node is None or self._volume_node is None:
            return

        try:
            import SegmentStatistics
            logic = SegmentStatistics.SegmentStatisticsLogic()
            logic.getParameterNode().SetParameter("Segmentation", self._segmentation_node.GetID())
            logic.getParameterNode().SetParameter("ScalarVolume", self._volume_node.GetID())
            logic.computeStatistics()
            stats = logic.getStatistics()

            total = 0
            segmentation = self._segmentation_node.GetSegmentation()
            for i in range(segmentation.GetNumberOfSegments()):
                seg_id = segmentation.GetNthSegmentID(i)
                key = f"{seg_id}.LabelmapSegmentStatisticsPlugin.voxel_count"
                if key in stats:
                    count = int(stats[key])
                    segment = segmentation.GetSegment(seg_id)
                    data.per_label_voxel_counts[segment.GetName()] = count
                    total += count

            data.total_voxel_count = total
            self._stats_label.setText(f"Total labeled voxels: {total:,}")
        except Exception as e:
            logger.warning(f"Could not compute segment statistics: {e}")

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

        self._refresh_segment_table()
        self._refresh_active_combo()

        if seg_data.total_voxel_count > 0:
            self._stats_label.setText(f"Total labeled voxels: {seg_data.total_voxel_count:,}")

    def deactivate_effect(self):
        """Stop the active painting effect."""
        try:
            self._segment_editor_widget.setActiveEffectByName("None")
        except Exception:
            pass

    def cleanup(self):
        """Remove temporary parameter nodes. Called on module unload."""
        self.deactivate_effect()
        if self._segment_editor_node:
            try:
                slicer.mrmlScene.RemoveNode(self._segment_editor_node)
            except Exception:
                pass
            self._segment_editor_node = None
