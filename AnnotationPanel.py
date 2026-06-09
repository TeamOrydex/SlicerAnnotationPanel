import os
import sys

import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)


class AnnotationPanel(ScriptedLoadableModule):
    """3D Slicer scripted loadable module: Annotation Panel."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Annotation Panel"
        self.parent.categories = ["Annotation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Annotation Panel Contributors"]
        self.parent.helpText = (
            "A custom annotation panel supporting classification labels, "
            "regions of interest (ROI), and segmentations for medical imaging."
        )
        self.parent.acknowledgementText = ""


class AnnotationPanelWidget(ScriptedLoadableModuleWidget):
    """Module widget that hosts the AnnotationPanelRootWidget."""

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        from PanelWidget import AnnotationPanelRootWidget

        self.panel = AnnotationPanelRootWidget()
        self.layout.addWidget(self.panel)
        self.layout.addStretch(1)

    def cleanup(self):
        if hasattr(self, "panel"):
            self.panel.cleanup()


class AnnotationPanelLogic(ScriptedLoadableModuleLogic):
    """Business logic for the Annotation Panel module."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    def load_annotation_file(self, filepath):
        """Load an annotation JSON file and return an AnnotationRecord."""
        from AnnotationModel import AnnotationRecord
        import json

        with open(filepath, "r") as f:
            data = json.load(f)
        return AnnotationRecord.from_dict(data)

    def save_annotation_file(self, record, filepath):
        """Save an AnnotationRecord to a JSON file."""
        with open(filepath, "w") as f:
            f.write(record.to_json())
