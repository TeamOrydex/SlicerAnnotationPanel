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
        self._sample_roi_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; }"
        )
        self._sample_roi_btn.setToolTip(
            "Programmatically create sample markup nodes to test the ROI tab"
        )
        self._sample_roi_btn.clicked.connect(self._on_add_sample_rois)
        self.layout.addWidget(self._sample_roi_btn)

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
            ROIAnnotation(
                roi_type="ellipse",
                label="Tumor",
                color="#0000ff",
                slice_view="Red",
                slice_index=0,
                control_points=[
                    {"x": -30.0, "y": 30.0, "z": 0.0},
                ],
                radii=[15.0, 10.0],
            ),
        ]

        roi_tab = self._panel._roi_tab
        roi_tab.load_rois(sample_rois)

        slicer.util.infoDisplay(
            f"Added {len(sample_rois)} sample ROIs (line, polygon, ellipse).",
            "Test Harness",
        )

    def cleanup(self):
        if hasattr(self, "_panel"):
            self._panel.cleanup()
