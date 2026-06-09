"""
Segmentation tab: pixel-level painting using Slicer's Segment Editor.
Embeds qMRMLSegmentEditorWidget and wraps it with label management,
export controls, and opacity adjustment. The source volume is set
externally by the panel (shared volume binding).
"""
import qt
import slicer
import logging

from AnnotationModel import SegmentationData, SegmentLabel

logger = logging.getLogger(__name__)

DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
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
        self._color_index = 0
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
        self._segment_table.setColumnCount(4)
        self._segment_table.setHorizontalHeaderLabels(["Color", "Name", "Visible", "Actions"])
        self._segment_table.horizontalHeader().setStretchLastSection(True)
        self._segment_table.setSelectionBehavior(qt.QTableWidget.SelectRows)
        self._segment_table.setEditTriggers(qt.QTableWidget.NoEditTriggers)
        fl.addWidget(self._segment_table)

        btn_row = qt.QHBoxLayout()
        self._add_segment_btn = qt.QPushButton("+ Add Segment")
        self._add_segment_btn.clicked.connect(self._on_add_segment)
        btn_row.addWidget(self._add_segment_btn)
        btn_row.addStretch()
        fl.addLayout(btn_row)

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

    def clear_and_unbind(self):
        """Remove segmentation data and unbind the volume."""
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
        self._color_index = 0
        self._segment_table.setRowCount(0)
        self._active_segment_combo.clear()
        self._stats_label.setText("Total labeled voxels: 0")

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

        # Slicer 5.x uses setSourceVolumeNode; older uses setMasterVolumeNode
        try:
            self._segment_editor_widget.setSourceVolumeNode(volume_node)
        except AttributeError:
            try:
                self._segment_editor_widget.setMasterVolumeNode(volume_node)
            except AttributeError:
                logger.warning("Could not set source volume on segment editor widget")

    # ─── Segment Label Management ────────────────────────────────────────

    def _on_add_segment(self):
        name, ok = qt.QInputDialog.getText(self, "Add Segment", "Segment name:")
        if not ok or not name.strip():
            return
        name = name.strip()

        if self._segmentation_node is None:
            qt.QMessageBox.warning(self, "No Volume", "Please load a scan first.")
            return

        color = DEFAULT_COLORS[self._color_index % len(DEFAULT_COLORS)]
        self._color_index += 1
        r, g, b = hex_to_rgb_float(color)

        segmentation = self._segmentation_node.GetSegmentation()
        segmentation.AddEmptySegment(name, name, [r, g, b])

        self._refresh_segment_table()
        self._refresh_active_combo()

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

            action_widget = qt.QWidget()
            action_layout = qt.QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            edit_btn = qt.QPushButton("\u270e")
            edit_btn.setFixedSize(24, 24)
            edit_btn.clicked.connect(lambda checked, sid=segment_id: self._on_edit_segment(sid))
            action_layout.addWidget(edit_btn)

            del_btn = qt.QPushButton("\u2715")
            del_btn.setFixedSize(24, 24)
            del_btn.clicked.connect(lambda checked, sid=segment_id: self._on_delete_segment(sid))
            action_layout.addWidget(del_btn)

            self._segment_table.setCellWidget(row, 3, action_widget)

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

    def _on_edit_segment(self, segment_id):
        if self._segmentation_node is None:
            return
        segmentation = self._segmentation_node.GetSegmentation()
        segment = segmentation.GetSegment(segment_id)
        if not segment:
            return

        dialog = qt.QDialog(self)
        dialog.setWindowTitle("Edit Segment")
        dlg_layout = qt.QVBoxLayout(dialog)

        dlg_layout.addWidget(qt.QLabel("Name:"))
        name_edit = qt.QLineEdit(segment.GetName())
        dlg_layout.addWidget(name_edit)

        color_arr = segment.GetColor()
        current_color = [rgb_float_to_hex(color_arr[0], color_arr[1], color_arr[2])]

        color_row = qt.QHBoxLayout()
        color_row.addWidget(qt.QLabel("Color:"))
        color_btn = qt.QPushButton("")
        color_btn.setFixedSize(32, 24)
        color_btn.setStyleSheet(f"background-color: {current_color[0]}; border: 1px solid #333;")

        def pick_color():
            c = qt.QColorDialog.getColor(qt.QColor(current_color[0]), dialog, "Segment Color")
            if c.isValid():
                current_color[0] = c.name()
                color_btn.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #333;")

        color_btn.clicked.connect(pick_color)
        color_row.addWidget(color_btn)
        color_row.addStretch()
        dlg_layout.addLayout(color_row)

        btn_box = qt.QDialogButtonBox()
        btn_box.addButton("Save", qt.QDialogButtonBox.AcceptRole)
        btn_box.addButton("Cancel", qt.QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        dlg_layout.addWidget(btn_box)

        if dialog.exec_() == qt.QDialog.Accepted:
            new_name = name_edit.text.strip()
            if new_name:
                segment.SetName(new_name)
            r, g, b = hex_to_rgb_float(current_color[0])
            segment.SetColor(r, g, b)
            self._refresh_segment_table()
            self._refresh_active_combo()

    def _on_delete_segment(self, segment_id):
        result = qt.QMessageBox.question(
            self, "Delete Segment",
            "Are you sure you want to delete this segment?",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
        )
        if result != qt.QMessageBox.Yes:
            return
        if self._segmentation_node:
            self._segmentation_node.GetSegmentation().RemoveSegment(segment_id)
            self._refresh_segment_table()
            self._refresh_active_combo()

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
        """
        Export the segmentation labelmap to a file.
        Returns True if export succeeded, False otherwise.
        """
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
