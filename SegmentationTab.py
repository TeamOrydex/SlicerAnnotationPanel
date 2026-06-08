"""Segmentation mask annotation tab. Placeholder for Phase 3."""
import qt


class SegmentationTab(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(qt.QLabel("Segmentation masks — coming in Phase 3"))

    def set_read_only(self, enabled):
        pass
