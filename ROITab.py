"""ROI (Region of Interest) annotation tab. Placeholder for Phase 2."""
import qt


class ROITab(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(qt.QLabel("ROI annotations — coming in Phase 2"))

    def set_read_only(self, enabled):
        pass
