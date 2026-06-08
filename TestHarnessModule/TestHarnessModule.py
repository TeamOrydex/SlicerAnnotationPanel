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

    def cleanup(self):
        pass
