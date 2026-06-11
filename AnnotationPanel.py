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

# Fail fast with a clear import error if extension files are incomplete.
try:
    import LabelColors  # noqa: F401
    import PresetStorage  # noqa: F401
except ImportError:
    raise ImportError(
        "Annotation Panel extension is incomplete. Copy the full module folder into "
        "Slicer, including LabelColors.py and PresetStorage.py."
    ) from None


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

        import qt
        import traceback

        try:
            from PanelWidget import AnnotationPanelRootWidget

            self.panel = AnnotationPanelRootWidget()
            self.layout.addWidget(self.panel)
            self.layout.addStretch(1)
        except Exception as exc:
            error_box = qt.QTextEdit()
            error_box.setReadOnly(True)
            error_box.setPlainText(
                "Annotation Panel failed to load.\n\n"
                f"{exc}\n\n"
                f"{traceback.format_exc()}"
            )
            error_box.setStyleSheet("color: #c62828; padding: 8px;")
            self.layout.addWidget(error_box)
            import logging
            logging.getLogger(__name__).exception("Annotation Panel setup failed")

    def cleanup(self):
        if hasattr(self, "panel"):
            self.panel.cleanup()


class AnnotationPanelLogic(ScriptedLoadableModuleLogic):
    """Business logic for the Annotation Panel module."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    def load_annotation_file(self, filepath):
        """Load an annotation JSON file and return an AnnotationRecord."""
        from AnnotationModel import (
            build_record_from_import,
            resolve_import_paths,
        )

        resolution = resolve_import_paths(filepath)
        record, errors = build_record_from_import(resolution)
        if errors or record is None:
            raise ValueError("\n".join(errors or resolution.errors or ["Import failed."]))
        return record

    def import_annotations(self, panel_widget, path):
        """Import annotations through the panel UI."""
        return panel_widget.import_annotations(path)

    def save_annotation_file(self, record, filepath):
        """Save an AnnotationRecord to a JSON file."""
        with open(filepath, "w") as f:
            f.write(record.to_json())
