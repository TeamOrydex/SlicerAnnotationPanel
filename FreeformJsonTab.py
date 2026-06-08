"""Freeform JSON metadata tab. Placeholder for Phase 4."""
import qt


class FreeformJsonTab(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(qt.QLabel("Freeform JSON — coming in Phase 4"))

    def set_read_only(self, enabled):
        pass
