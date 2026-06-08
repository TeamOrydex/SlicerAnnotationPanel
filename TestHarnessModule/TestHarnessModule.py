"""
Standalone Slicer module for testing the Annotation Panel.
Loads a sample volume and mounts the panel for interactive testing.
"""
import os
import sys

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
    """Widget that provides a load button and the annotation panel."""

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        import qt
        from PanelWidget import AnnotationPanelRootWidget

        self._load_btn = qt.QPushButton("Load Sample Volume (MRHead)")
        self._load_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-weight: bold; }"
        )
        self._load_btn.clicked.connect(self._on_load_sample)
        self.layout.addWidget(self._load_btn)

        self._sample_roi_btn = qt.QPushButton("Add Sample ROIs")
        self._sample_roi_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._sample_roi_btn.setToolTip(
            "Programmatically create sample markup nodes to test the ROI tab"
        )
        self._sample_roi_btn.clicked.connect(self._on_add_sample_rois)
        self.layout.addWidget(self._sample_roi_btn)

        self._sample_seg_btn = qt.QPushButton("Add Sample Segmentation")
        self._sample_seg_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._sample_seg_btn.setToolTip(
            "Create a sample segmentation with sphere segments"
        )
        self._sample_seg_btn.clicked.connect(self._on_add_sample_segmentation)
        self.layout.addWidget(self._sample_seg_btn)

        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        self.layout.addWidget(separator)

        self._panel = AnnotationPanelRootWidget()
        self._panel.set_study_info("STUDY-TEST-001", "SERIES-MRHead-001")
        self.layout.addWidget(self._panel)

        self.layout.addStretch(1)

    def _on_load_sample(self):
        import SampleData
        SampleData.SampleDataLogic().downloadMRHead()
        slicer.util.infoDisplay(
            "MRHead sample volume loaded successfully.",
            "Test Harness",
        )

    def _on_add_sample_rois(self):
        """Create sample ROI annotations to test the load_rois path."""
        from AnnotationModel import ROIAnnotation

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

        roi_tab = self._panel._roi_tab
        roi_tab.load_rois(sample_rois)
        slicer.util.infoDisplay(
            f"Added {len(sample_rois)} sample ROIs.",
            "Test Harness",
        )

    def _on_add_sample_segmentation(self):
        """Create a sample segmentation with sphere segments for testing."""
        import vtk

        # Get the first volume node in the scene
        volume_node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
        if volume_node is None:
            slicer.util.warningDisplay(
                "Please load a volume first (e.g., MRHead).",
                "Test Harness",
            )
            return

        seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        seg_node.CreateDefaultDisplayNodes()
        seg_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        seg_node.SetName("TestSegmentation")

        # Add sphere segment: Tumor
        sphere1 = vtk.vtkSphereSource()
        sphere1.SetCenter(0, 0, 0)
        sphere1.SetRadius(15)
        sphere1.SetThetaResolution(20)
        sphere1.SetPhiResolution(20)
        sphere1.Update()
        seg_node.AddSegmentFromClosedSurfaceRepresentation(
            sphere1.GetOutput(), "Tumor", [1.0, 0.0, 0.0]
        )

        # Add sphere segment: Edema
        sphere2 = vtk.vtkSphereSource()
        sphere2.SetCenter(30, 20, 0)
        sphere2.SetRadius(10)
        sphere2.SetThetaResolution(20)
        sphere2.SetPhiResolution(20)
        sphere2.Update()
        seg_node.AddSegmentFromClosedSurfaceRepresentation(
            sphere2.GetOutput(), "Edema", [1.0, 1.0, 0.0]
        )

        # Link to the segmentation tab
        seg_tab = self._panel._segmentation_tab
        seg_tab._segmentation_node = seg_node
        seg_tab._volume_selector.setCurrentNode(volume_node)
        seg_tab._link_editor_to_nodes(volume_node)
        seg_tab._refresh_segment_table()
        seg_tab._refresh_active_combo()

        display_node = seg_node.GetDisplayNode()
        if display_node:
            display_node.SetOpacity(0.5)

        slicer.util.infoDisplay(
            "Added sample segmentation (Tumor + Edema spheres).",
            "Test Harness",
        )

    def cleanup(self):
        if hasattr(self, "_panel"):
            self._panel.cleanup()
