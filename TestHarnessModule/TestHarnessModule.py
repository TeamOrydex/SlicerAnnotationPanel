"""
Standalone Slicer module for testing the Annotation Panel.
Loads a sample volume and mounts the panel for interactive testing.
"""
import os
import sys
import tempfile

import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PANEL_DIR = os.path.dirname(MODULE_DIR)
if PANEL_DIR not in sys.path:
    sys.path.insert(0, PANEL_DIR)


class TestHarnessModule(ScriptedLoadableModule):
    """Test harness module for the Annotation Panel."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Annotation Panel Test Harness"
        self.parent.categories = ["Testing"]
        self.parent.dependencies = []
        self.parent.contributors = ["Annotation Panel Contributors"]
        self.parent.helpText = (
            "Test harness that loads a sample volume and displays the "
            "Annotation Panel for interactive testing."
        )
        self.parent.acknowledgementText = ""


class TestHarnessModuleWidget(ScriptedLoadableModuleWidget):
    """Widget that provides test buttons and the annotation panel."""

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        import qt
        from PanelWidget import AnnotationPanelRootWidget

        self._load_via_panel_btn = qt.QPushButton("Load MRHead via Panel")
        self._load_via_panel_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-weight: bold; }"
        )
        self._load_via_panel_btn.setToolTip(
            "Download MRHead and load it through the panel's scan binding"
        )
        self._load_via_panel_btn.clicked.connect(self._on_load_via_panel)
        self.layout.addWidget(self._load_via_panel_btn)

        self._sample_roi_btn = qt.QPushButton("Add Sample ROIs")
        self._sample_roi_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._sample_roi_btn.clicked.connect(self._on_add_sample_rois)
        self.layout.addWidget(self._sample_roi_btn)

        self._sample_seg_btn = qt.QPushButton("Add Sample Segmentation")
        self._sample_seg_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._sample_seg_btn.clicked.connect(self._on_add_sample_segmentation)
        self.layout.addWidget(self._sample_seg_btn)

        self._test_export_btn = qt.QPushButton("Test Export")
        self._test_export_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._test_export_btn.setToolTip("Export annotations to a temp directory")
        self._test_export_btn.clicked.connect(self._on_test_export)
        self.layout.addWidget(self._test_export_btn)

        self._test_full_btn = qt.QPushButton("Test Full Workflow")
        self._test_full_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._test_full_btn.setToolTip(
            "Load MRHead, add annotations, export, and verify"
        )
        self._test_full_btn.clicked.connect(self._on_test_full_workflow)
        self.layout.addWidget(self._test_full_btn)

        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        self.layout.addWidget(separator)

        self._panel = AnnotationPanelRootWidget()
        self._panel.set_study_info("STUDY-TEST-001", "SERIES-MRHead-001")
        self.layout.addWidget(self._panel)

        self.layout.addStretch(1)

    def _on_load_via_panel(self):
        """Load MRHead through the panel's scan binding workflow."""
        import SampleData
        volume_node = SampleData.SampleDataLogic().downloadMRHead()
        if volume_node:
            self._panel._on_scan_loaded(volume_node, "SampleData/MRHead.nrrd")
            slicer.util.infoDisplay(
                "MRHead loaded and bound to panel.", "Test Harness"
            )

    def _on_add_sample_rois(self):
        """Create sample ROI annotations."""
        from AnnotationModel import ROIAnnotation

        if self._panel._active_volume_node is None:
            slicer.util.warningDisplay(
                "Load a scan first.", "Test Harness"
            )
            return

        sample_rois = [
            ROIAnnotation(
                roi_type="line",
                label="Measurement",
                color="#00ff00",
                slice_view="Red",
                slice_index=0,
                control_points=[
                    {"x": -20.0, "y": 10.0, "z": 0.0},
                    {"x": 20.0, "y": -10.0, "z": 0.0},
                ],
            ),
            ROIAnnotation(
                roi_type="polygon",
                label="Lesion",
                color="#ff0000",
                slice_view="Red",
                slice_index=0,
                control_points=[
                    {"x": 0.0, "y": 0.0, "z": 0.0},
                    {"x": 10.0, "y": 10.0, "z": 0.0},
                    {"x": 20.0, "y": 5.0, "z": 0.0},
                    {"x": 15.0, "y": -5.0, "z": 0.0},
                    {"x": 5.0, "y": -5.0, "z": 0.0},
                ],
            ),
        ]

        self._panel._roi_tab.load_rois(sample_rois)
        slicer.util.infoDisplay(
            f"Added {len(sample_rois)} sample ROIs.", "Test Harness"
        )

    def _on_add_sample_segmentation(self):
        """Create a sample segmentation with sphere segments."""
        import vtk

        volume_node = self._panel._active_volume_node
        if volume_node is None:
            slicer.util.warningDisplay(
                "Load a scan first.", "Test Harness"
            )
            return

        seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        seg_node.CreateDefaultDisplayNodes()
        seg_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        seg_node.SetName("TestSegmentation")

        sphere1 = vtk.vtkSphereSource()
        sphere1.SetCenter(0, 0, 0)
        sphere1.SetRadius(15)
        sphere1.SetThetaResolution(20)
        sphere1.SetPhiResolution(20)
        sphere1.Update()
        seg_node.AddSegmentFromClosedSurfaceRepresentation(
            sphere1.GetOutput(), "Tumor", [1.0, 0.0, 0.0]
        )

        sphere2 = vtk.vtkSphereSource()
        sphere2.SetCenter(30, 20, 0)
        sphere2.SetRadius(10)
        sphere2.SetThetaResolution(20)
        sphere2.SetPhiResolution(20)
        sphere2.Update()
        seg_node.AddSegmentFromClosedSurfaceRepresentation(
            sphere2.GetOutput(), "Edema", [1.0, 1.0, 0.0]
        )

        seg_tab = self._panel._segmentation_tab
        seg_tab._segmentation_node = seg_node
        seg_tab._link_editor_to_nodes(volume_node)
        seg_tab._refresh_segment_table()
        seg_tab._refresh_active_combo()

        display_node = seg_node.GetDisplayNode()
        if display_node:
            display_node.SetOpacity(0.5)

        slicer.util.infoDisplay(
            "Added sample segmentation (Tumor + Edema).", "Test Harness"
        )

    def _on_test_export(self):
        """Export annotations to a temp directory."""
        import json as json_mod

        if self._panel._active_volume_node is None:
            slicer.util.warningDisplay("Load a scan first.", "Test Harness")
            return

        self._panel._collect_all_data()
        record = self._panel._record
        export_dir = tempfile.mkdtemp(prefix="annotation_export_")

        annotation_path = os.path.join(export_dir, "annotation.json")
        with open(annotation_path, "w") as f:
            f.write(record.to_json())

        if record.rois:
            rois_path = os.path.join(export_dir, "rois.json")
            with open(rois_path, "w") as f:
                json_mod.dump([roi.to_dict() for roi in record.rois], f, indent=2)

        if record.scan:
            scan_path = os.path.join(export_dir, "scan_metadata.json")
            with open(scan_path, "w") as f:
                json_mod.dump(record.scan.to_dict(), f, indent=2)

        print(f"Test export directory: {export_dir}")
        for fname in os.listdir(export_dir):
            print(f"  - {fname}")

        slicer.util.infoDisplay(
            f"Test export complete.\nFiles in: {export_dir}", "Test Harness"
        )

    def _on_test_full_workflow(self):
        """Run a full automated workflow test."""
        import json as json_mod

        # 1. Load MRHead
        import SampleData
        volume_node = SampleData.SampleDataLogic().downloadMRHead()
        self._panel._on_scan_loaded(volume_node, "SampleData/MRHead.nrrd")

        # 2. Add class labels
        self._panel._class_label_tab._checkboxes["Normal"].setChecked(True)
        self._panel._class_label_tab._checkboxes["Artifact"].setChecked(True)

        # 3. Add sample ROIs
        self._on_add_sample_rois()

        # 4. Add sample segmentation
        self._on_add_sample_segmentation()

        # 5. Export
        export_dir = tempfile.mkdtemp(prefix="full_workflow_test_")
        self._panel._collect_all_data()
        record = self._panel._record

        annotation_path = os.path.join(export_dir, "annotation.json")
        with open(annotation_path, "w") as f:
            f.write(record.to_json())

        if record.rois:
            rois_path = os.path.join(export_dir, "rois.json")
            with open(rois_path, "w") as f:
                json_mod.dump([roi.to_dict() for roi in record.rois], f, indent=2)

        if record.scan:
            scan_path = os.path.join(export_dir, "scan_metadata.json")
            with open(scan_path, "w") as f:
                json_mod.dump(record.scan.to_dict(), f, indent=2)

        # 6. Verify
        files = os.listdir(export_dir)
        print(f"Full workflow test export: {export_dir}")
        for f in files:
            print(f"  - {f}")

        assert "annotation.json" in files, "Missing annotation.json"
        assert "rois.json" in files, "Missing rois.json"
        assert "scan_metadata.json" in files, "Missing scan_metadata.json"

        # Verify annotation.json contents
        with open(annotation_path, "r") as f:
            data = json_mod.load(f)
        assert len(data["class_labels"]) >= 2, "Expected at least 2 class labels"
        assert len(data["rois"]) >= 2, "Expected at least 2 ROIs"
        assert data["scan"] is not None, "Expected scan metadata"

        slicer.util.infoDisplay(
            f"Full workflow test PASSED.\nExport dir: {export_dir}",
            "Test Harness",
        )

    def cleanup(self):
        if hasattr(self, "_panel"):
            self._panel.cleanup()
