"""Tests for neutral ROI workspace initialization (no auto tool activation)."""
import os
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AnnotationPanel"))

from AnnotationModel import LabelDefinition


class _FakeComboBox:
    def __init__(self):
        self._items = []
        self._index = -1
        self.currentIndexChanged = MagicMock()

    def blockSignals(self, blocked):
        pass

    def clear(self):
        self._items = []
        self._index = -1

    def addItem(self, text):
        self._items.append(text)

    def setCurrentIndex(self, index):
        self._index = index

    @property
    def count(self):
        return len(self._items)

    @property
    def currentText(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return ""


class _FakeToolButton:
    def __init__(self):
        self._checked = False
        self._enabled = True
        self._tooltip = ""
        self.toggled = MagicMock()

    def setChecked(self, checked):
        self._checked = checked

    def isChecked(self):
        return self._checked

    def setEnabled(self, enabled):
        self._enabled = enabled

    def blockSignals(self, _blocked):
        pass

    def setToolTip(self, tip):
        self._tooltip = tip


def _install_module_mocks():
    qt = types.ModuleType("qt")

    class _QWidget:
        def __init__(self, parent=None):
            pass

    qt.QWidget = _QWidget
    qt.QVBoxLayout = MagicMock
    qt.QHBoxLayout = MagicMock
    qt.QFrame = MagicMock()
    qt.QFrame.StyledPanel = 0
    qt.QFrame.NoFrame = 0
    qt.QLabel = MagicMock
    qt.QComboBox = _FakeComboBox
    qt.QPushButton = MagicMock
    qt.QToolButton = _FakeToolButton
    qt.QButtonGroup = MagicMock
    qt.QTableWidget = MagicMock
    qt.QHeaderView = MagicMock()
    qt.QHeaderView.Stretch = 0
    qt.QCheckBox = MagicMock
    qt.QTimer = MagicMock
    qt.Qt = MagicMock()
    qt.Qt.UserRole = 0
    sys.modules["qt"] = qt

    slicer = types.ModuleType("slicer")
    slicer.mrmlScene = MagicMock()
    slicer.app = MagicMock()
    slicer.vtkMRMLMarkupsNode = MagicMock()
    slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent = 1
    sys.modules["slicer"] = slicer


@contextmanager
def _roi_tab_test_context():
    saved_modules = {
        name: sys.modules.get(name)
        for name in ("qt", "slicer", "ROITab")
    }
    _install_module_mocks()
    sys.modules.pop("ROITab", None)
    try:
        from ROITab import ROITab

        yield ROITab
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class TestROIWorkspaceInitialization(unittest.TestCase):
    def _make_tab(self, ROITab):
        tab = ROITab.__new__(ROITab)
        tab._record = None
        tab._roi_labels = []
        tab._roi_annotations = []
        tab._volume_node = None
        tab._current_color = "#ff0000"
        tab._active_tool = None
        tab._observers = []
        tab._node_observers = {}
        tab._available_tools = {
            "rectangle_2d": True,
            "rectangle_3d": True,
            "polygon": True,
            "freehand_curve": True,
            "line": True,
        }
        tab._placement_node = None
        tab._rectangle_finalize_scheduled = set()
        tab._extend_roi = None
        tab._extend_mode_active = False
        tab._global_roi_hidden = False
        tab._label_combo = _FakeComboBox()
        tab._drawing_tool_label = MagicMock()
        tab._color_swatch = MagicMock()
        tab._tool_buttons = {
            tool_id: _FakeToolButton() for tool_id in tab._available_tools
        }
        tab._tool_group = MagicMock()
        tab._extend_hint_label = MagicMock()
        tab._roi_table = MagicMock()
        return tab

    def test_set_labels_does_not_activate_tool(self):
        with _roi_tab_test_context() as ROITab:
            tab = self._make_tab(ROITab)
            labels = [
                LabelDefinition(name="Tumor", color="#ff0000", drawing_tool="rectangle_3d"),
                LabelDefinition(name="Organ", color="#00ff00", drawing_tool="polygon"),
            ]

            with patch.object(tab, "_deactivate_tool") as deactivate, patch.object(
                tab, "_activate_tool"
            ) as activate, patch.object(tab, "_sync_label_drawing_tool") as sync_tool:
                tab.set_labels(labels)

            deactivate.assert_called_once()
            activate.assert_not_called()
            sync_tool.assert_called_once_with(activate=False)
            self.assertEqual(tab._label_combo._index, -1)

    def test_set_labels_clears_empty_selection_state(self):
        with _roi_tab_test_context() as ROITab:
            tab = self._make_tab(ROITab)
            with patch.object(tab, "_deactivate_tool"), patch.object(
                tab, "_sync_label_drawing_tool"
            ):
                tab.set_labels([])

            self.assertEqual(tab._label_combo.count, 0)
            self.assertEqual(tab._label_combo._index, -1)

    def test_label_selection_still_activates_tool(self):
        with _roi_tab_test_context() as ROITab:
            tab = self._make_tab(ROITab)
            tab._roi_labels = [
                LabelDefinition(name="Tumor", color="#ff0000", drawing_tool="rectangle_3d"),
            ]

            with patch.object(tab, "_sync_label_drawing_tool") as sync_tool:
                tab._on_label_selection_changed(0)

            sync_tool.assert_called_once_with(activate=True)

    def test_apply_label_config_does_not_auto_activate(self):
        with _roi_tab_test_context() as ROITab:
            tab = self._make_tab(ROITab)
            tab._roi_labels = [LabelDefinition(name="Tumor", color="#ff0000")]
            tab._roi_annotations = []

            with patch.object(tab, "_update_table"), patch.object(
                tab, "_sync_to_record"
            ), patch.object(tab, "_sync_label_drawing_tool") as sync_tool:
                tab.apply_label_config(tab._roi_labels, tab._roi_labels)

            sync_tool.assert_called_once_with(activate=False)


if __name__ == "__main__":
    unittest.main()
