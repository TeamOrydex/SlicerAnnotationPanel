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

        self._load_preset_btn = qt.QPushButton("Load Sample Config")
        self._load_preset_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; font-weight: bold; }"
        )
        self._load_preset_btn.setToolTip(
            "Loads a sample label configuration into the config screen and confirms"
        )
        self._load_preset_btn.clicked.connect(self._on_load_sample_config)
        self.layout.addWidget(self._load_preset_btn)

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

        self._test_full_btn = qt.QPushButton("Test Config \u2192 Annotate \u2192 Export")
        self._test_full_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._test_full_btn.setToolTip(
            "Load preset, confirm config, load MRHead, annotate, export, verify"
        )
        self._test_full_btn.clicked.connect(self._on_test_full_workflow)
        self.layout.addWidget(self._test_full_btn)

        self._test_config_edit_btn = qt.QPushButton("Test Config Edit")
        self._test_config_edit_btn.setStyleSheet("QPushButton { padding: 8px 16px; }")
        self._test_config_edit_btn.setToolTip(
            "Load preset, confirm, annotate, re-edit config, verify cleanup"
        )
        self._test_config_edit_btn.clicked.connect(self._on_test_config_edit)
        self.layout.addWidget(self._test_config_edit_btn)

        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        self.layout.addWidget(separator)

        self._panel = AnnotationPanelRootWidget()
        self._panel.set_study_info("STUDY-TEST-001", "SERIES-MRHead-001")
        self.layout.addWidget(self._panel)

        self.layout.addStretch(1)

    def _sample_label_config(self):
        from AnnotationModel import LabelDefinition, LabelConfig

        return LabelConfig(
            class_labels=[
                LabelDefinition(name="Normal", color="#4CAF50", description="No abnormality identified"),
                LabelDefinition(name="Pathological", color="#f44336", description="Abnormality present"),
            ],
            roi_labels=[
                LabelDefinition(name="Tumor", color="#e6194b", description="Tumor"),
                LabelDefinition(name="Lesion", color="#f58231", description="Lesion"),
                LabelDefinition(name="Cyst", color="#42d4f4", description="Cyst"),
                LabelDefinition(name="Artifact", color="#808080", description="Imaging artifact"),
            ],
            segmentation_classes=[
                LabelDefinition(name="Tumor Core", color="#e6194b", description="Solid tumor"),
                LabelDefinition(name="Enhancing Tumor", color="#ffe119", description="Enhancing region"),
                LabelDefinition(name="Edema", color="#3cb44b", description="Peritumoral edema"),
                LabelDefinition(name="Necrosis", color="#911eb4", description="Necrotic core"),
            ],
        )

    def _on_load_sample_config(self):
        """Load a sample label configuration into the config screen and confirm."""
        config = self._sample_label_config()
        self._panel._config_screen.load_config(config)
        self._panel._on_config_confirmed(config)
        slicer.util.infoDisplay(
            "Sample label configuration loaded and confirmed.", "Test Harness"
        )

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
                label="Tumor",
                color="#e6194b",
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
                color="#f58231",
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

    def _on_test_full_workflow(self):
        """Full automated workflow: config -> scan -> annotate -> export -> verify."""
        import json as json_mod
        from AnnotationModel import LabelDefinition, LabelConfig

        # 1. Load sample config and confirm
        config = self._sample_label_config()
        self._panel._on_config_confirmed(config)

        # 2. Load MRHead
        import SampleData
        volume_node = SampleData.SampleDataLogic().downloadMRHead()
        self._panel._on_scan_loaded(volume_node, "SampleData/MRHead.nrrd")

        # 3. Select class labels
        self._panel._class_label_tab.set_selected_labels(["Normal"])

        # 4. Add sample ROIs
        self._on_add_sample_rois()

        # 5. Export
        export_dir = tempfile.mkdtemp(prefix="config_workflow_test_")
        self._panel._collect_all_data()
        record = self._panel._record

        annotation_path = os.path.join(export_dir, "annotation.json")
        with open(annotation_path, "w") as f:
            f.write(record.to_json())

        # 6. Verify
        files = os.listdir(export_dir)
        print(f"Full workflow test export: {export_dir}")
        for fn in files:
            print(f"  - {fn}")

        assert files == ["annotation.json"], f"Expected only annotation.json, got: {files}"

        with open(annotation_path, "r") as f:
            data = json_mod.load(f)
        assert data.get("label_config") is not None, "Expected label_config in export"
        assert len(data["label_config"]["class_labels"]) == 2
        assert len(data["label_config"]["roi_labels"]) == 4
        assert len(data["label_config"]["segmentation_classes"]) == 4
        class_label_names = [
            item["label"] if isinstance(item, dict) else item
            for item in data["class_labels"]
        ]
        assert "Normal" in class_label_names, "Expected 'Normal' in class_labels"
        assert len(data["rois"]) >= 2, "Expected at least 2 ROIs"
        from AnnotationModel import ROIAnnotation

        for roi_entry in data.get("regions_of_interest", data.get("rois", [])):
            roi = ROIAnnotation.from_dict(roi_entry)
            missing = roi.missing_reconstruction_fields()
            assert not missing, (
                f"ROI {roi.roi_type} ({roi.label}) missing reconstruction fields: {missing}"
            )
        assert data["scan"] is not None, "Expected scan metadata"

        slicer.util.infoDisplay(
            f"Full workflow test PASSED.\nExport dir: {export_dir}",
            "Test Harness",
        )

    def _on_test_config_edit(self):
        """Test re-editing configuration after annotation."""
        from AnnotationModel import LabelDefinition, LabelConfig

        # 1. Setup initial config with 2 class labels
        config = LabelConfig(
            class_labels=[
                LabelDefinition(name="Normal", color="#4CAF50", description="No findings"),
                LabelDefinition(name="Pathological", color="#f44336", description="Has findings"),
            ],
            roi_labels=[
                LabelDefinition(name="Tumor", color="#e6194b", description="Tumor region"),
            ],
            segmentation_classes=[],
        )
        self._panel._on_config_confirmed(config)

        # 2. Load scan
        import SampleData
        volume_node = SampleData.SampleDataLogic().downloadMRHead()
        self._panel._on_scan_loaded(volume_node, "SampleData/MRHead.nrrd")

        # 3. Select "Normal" class label
        self._panel._class_label_tab.set_selected_labels(["Normal"])

        # 4. Verify label is selected
        selected = self._panel._class_label_tab.get_selected_labels()
        assert "Normal" in selected, f"Expected 'Normal' in selected labels, got {selected}"

        # 5. Re-configure: remove "Normal", keep "Pathological", add "Inconclusive"
        new_config = LabelConfig(
            class_labels=[
                config.class_labels[1],  # Pathological (same id)
                LabelDefinition(name="Inconclusive", color="#FF9800"),
            ],
            roi_labels=config.roi_labels,
            segmentation_classes=[],
        )
        self._panel._on_config_confirmed(new_config)

        # 6. Verify "Normal" was removed from record
        selected_names = [ann.label for ann in self._panel._record.class_labels]
        assert "Normal" not in selected_names, (
            "Expected 'Normal' to be removed after config edit"
        )

        slicer.util.infoDisplay(
            "Config edit test PASSED.\n"
            "'Normal' was removed from annotations after being removed from config.",
            "Test Harness",
        )

    def cleanup(self):
        if hasattr(self, "_panel"):
            self._panel.cleanup()
