"""Unit tests for AnnotationModel.py"""
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AnnotationModel import (
    AnnotationRecord, ROIAnnotation, SegmentationData, SegmentLabel, ScanMetadata,
    LabelDefinition, LabelConfig
)


class TestAnnotationRecordCreation(unittest.TestCase):
    def test_default_creation(self):
        record = AnnotationRecord()
        self.assertTrue(len(record.id) > 0)
        self.assertEqual(record.study_id, "")
        self.assertEqual(record.series_id, "")
        self.assertEqual(record.class_labels, [])
        self.assertEqual(record.rois, [])
        self.assertIsNone(record.segmentation)
        self.assertIsNone(record.scan)
        self.assertIsNotNone(record.created_at)

    def test_creation_with_values(self):
        record = AnnotationRecord(
            study_id="STUDY-001",
            series_id="SERIES-001",
            created_by="annotator1",
            class_labels=["Normal", "Artifact"],
        )
        self.assertEqual(record.study_id, "STUDY-001")
        self.assertEqual(record.series_id, "SERIES-001")
        self.assertEqual(record.created_by, "annotator1")
        self.assertEqual(record.class_labels, ["Normal", "Artifact"])


class TestToDict(unittest.TestCase):
    def test_to_dict_has_all_keys(self):
        record = AnnotationRecord()
        d = record.to_dict()
        expected_keys = {
            "id", "study_id", "series_id", "created_by", "created_at",
            "label_config", "scan", "class_labels", "rois", "segmentation",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_values(self):
        record = AnnotationRecord(
            study_id="S1",
            class_labels=["Normal"],
        )
        d = record.to_dict()
        self.assertEqual(d["study_id"], "S1")
        self.assertEqual(d["class_labels"], ["Normal"])
        self.assertEqual(d["rois"], [])
        self.assertIsNone(d["segmentation"])
        self.assertIsNone(d["scan"])

    def test_to_dict_with_rois(self):
        roi = ROIAnnotation(
            roi_type="ellipse",
            slice_index=5,
            control_points=[{"x": 100.0, "y": 200.0, "z": 0.0}],
            radii=[30.0, 20.0],
            label="Lesion",
            color="#00ff00",
        )
        record = AnnotationRecord(rois=[roi])
        d = record.to_dict()
        self.assertEqual(len(d["rois"]), 1)
        self.assertEqual(d["rois"][0]["roi_type"], "ellipse")

    def test_to_dict_with_segmentation(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="Tumor", color="#ff0000", segment_id="Segment_1")],
            total_voxel_count=5000,
            per_label_voxel_counts={"Tumor": 5000},
        )
        record = AnnotationRecord(segmentation=seg)
        d = record.to_dict()
        self.assertIsNotNone(d["segmentation"])
        self.assertEqual(d["segmentation"]["labels"][0]["name"], "Tumor")

    def test_to_dict_with_scan(self):
        scan = ScanMetadata(
            filename="brain.nrrd",
            filepath="/data/brain.nrrd",
            file_format="nrrd",
            dimensions=[256, 256, 130],
            spacing=[1.0, 1.0, 1.3],
            origin=[0.0, 0.0, 0.0],
        )
        record = AnnotationRecord(scan=scan)
        d = record.to_dict()
        self.assertIsNotNone(d["scan"])
        self.assertEqual(d["scan"]["filename"], "brain.nrrd")
        self.assertEqual(d["scan"]["dimensions"], [256, 256, 130])


class TestFromDict(unittest.TestCase):
    def test_round_trip(self):
        record = AnnotationRecord(
            study_id="STUDY-RT",
            series_id="SERIES-RT",
            created_by="user1",
            class_labels=["Normal", "Artifact"],
            rois=[ROIAnnotation(roi_type="rectangle", slice_index=10,
                                control_points=[{"x": 1.0, "y": 2.0, "z": 3.0}],
                                radii=[5.0, 3.0])],
            segmentation=SegmentationData(
                labels=[SegmentLabel(name="bg", color="#000000", segment_id="S1")],
            ),
            scan=ScanMetadata(filename="test.nrrd", dimensions=[128, 128, 64]),
        )
        d = record.to_dict()
        restored = AnnotationRecord.from_dict(d)

        self.assertEqual(restored.id, record.id)
        self.assertEqual(restored.study_id, record.study_id)
        self.assertEqual(restored.class_labels, record.class_labels)
        self.assertEqual(len(restored.rois), 1)
        self.assertIsNotNone(restored.segmentation)
        self.assertIsNotNone(restored.scan)
        self.assertEqual(restored.scan.filename, "test.nrrd")

    def test_from_dict_missing_optional_fields(self):
        minimal = {"id": "test-id"}
        record = AnnotationRecord.from_dict(minimal)
        self.assertEqual(record.id, "test-id")
        self.assertEqual(record.class_labels, [])
        self.assertIsNone(record.segmentation)
        self.assertIsNone(record.scan)

    def test_from_dict_ignores_old_fields(self):
        """Loading an old JSON with removed fields should not crash."""
        old_data = {
            "id": "old-record",
            "study_id": "S-OLD",
            "status": "approved",
            "reviewed_by": "reviewer1",
            "freeform_data": {"key": "value"},
            "class_labels": ["Normal"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(old_data)
        self.assertEqual(record.id, "old-record")
        self.assertEqual(record.class_labels, ["Normal"])

    def test_from_dict_without_scan_key(self):
        """Old format without scan field loads fine."""
        data = {
            "id": "no-scan",
            "class_labels": ["A"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertIsNone(record.scan)
        self.assertEqual(record.class_labels, ["A"])


class TestJsonSerialization(unittest.TestCase):
    def test_to_json_produces_valid_json(self):
        record = AnnotationRecord(class_labels=["Normal"])
        json_str = record.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["class_labels"], ["Normal"])

    def test_json_round_trip(self):
        record = AnnotationRecord(
            study_id="JSON-TEST",
            class_labels=["Pathological", "Motion Blur"],
        )
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)
        self.assertEqual(restored.study_id, "JSON-TEST")
        self.assertEqual(restored.class_labels, ["Pathological", "Motion Blur"])


class TestClassLabels(unittest.TestCase):
    def test_set_and_get_labels(self):
        record = AnnotationRecord()
        record.class_labels = ["Normal", "Artifact"]
        self.assertEqual(record.class_labels, ["Normal", "Artifact"])

    def test_labels_persist_through_serialization(self):
        record = AnnotationRecord(class_labels=["A", "B", "C"])
        restored = AnnotationRecord.from_dict(record.to_dict())
        self.assertEqual(restored.class_labels, ["A", "B", "C"])


class TestROIAnnotation(unittest.TestCase):
    def test_default_creation(self):
        roi = ROIAnnotation()
        self.assertTrue(len(roi.id) > 0)
        self.assertEqual(roi.roi_type, "")
        self.assertEqual(roi.control_points, [])
        self.assertEqual(roi.mrml_node_id, "")

    def test_to_dict_excludes_mrml_node_id(self):
        roi = ROIAnnotation(mrml_node_id="vtkMRMLMarkupsLineNode1")
        d = roi.to_dict()
        self.assertNotIn("mrml_node_id", d)

    def test_from_dict_round_trip(self):
        roi = ROIAnnotation(
            roi_type="freehand_curve",
            label="Region B",
            color="#123456",
            slice_view="Yellow",
            slice_index=99,
            control_points=[
                {"x": 0.0, "y": 0.0, "z": 5.0},
                {"x": 1.0, "y": 2.0, "z": 5.0},
                {"x": 3.0, "y": 4.0, "z": 5.0},
            ],
            description="A freehand curve",
        )
        d = roi.to_dict()
        restored = ROIAnnotation.from_dict(d)
        self.assertEqual(restored.id, roi.id)
        self.assertEqual(restored.roi_type, "freehand_curve")
        self.assertEqual(len(restored.control_points), 3)
        self.assertEqual(restored.mrml_node_id, "")


class TestSegmentLabel(unittest.TestCase):
    def test_default_creation(self):
        lbl = SegmentLabel()
        self.assertTrue(len(lbl.id) > 0)
        self.assertEqual(lbl.name, "")
        self.assertEqual(lbl.color, "#ff0000")

    def test_from_dict_round_trip(self):
        lbl = SegmentLabel(name="Necrosis", color="#800080", segment_id="Segment_3")
        d = lbl.to_dict()
        restored = SegmentLabel.from_dict(d)
        self.assertEqual(restored.name, "Necrosis")
        self.assertEqual(restored.color, "#800080")


class TestSegmentationData(unittest.TestCase):
    def test_default_creation(self):
        seg = SegmentationData()
        self.assertEqual(seg.labels, [])
        self.assertEqual(seg.export_format, "nrrd")
        self.assertEqual(seg.segmentation_node_id, "")

    def test_to_dict_excludes_segmentation_node_id(self):
        seg = SegmentationData(segmentation_node_id="vtkMRMLSegmentationNode1")
        d = seg.to_dict()
        self.assertNotIn("segmentation_node_id", d)

    def test_from_dict_round_trip(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="WM", color="#ffffff", segment_id="Seg_WM")],
            export_format="nrrd",
            export_filepath="/data/mask.nrrd",
            total_voxel_count=50000,
            per_label_voxel_counts={"WM": 50000},
        )
        d = seg.to_dict()
        restored = SegmentationData.from_dict(d)
        self.assertEqual(restored.labels[0].name, "WM")
        self.assertEqual(restored.total_voxel_count, 50000)
        self.assertEqual(restored.segmentation_node_id, "")


class TestScanMetadata(unittest.TestCase):
    def test_default_creation(self):
        scan = ScanMetadata()
        self.assertEqual(scan.filename, "")
        self.assertEqual(scan.filepath, "")
        self.assertEqual(scan.file_format, "")
        self.assertEqual(scan.dimensions, [])
        self.assertEqual(scan.spacing, [])
        self.assertEqual(scan.origin, [])
        self.assertEqual(scan.modality, "")
        self.assertEqual(scan.volume_node_id, "")

    def test_creation_with_values(self):
        scan = ScanMetadata(
            filename="brain_mri.nrrd",
            filepath="/data/scans/brain_mri.nrrd",
            file_format="nrrd",
            dimensions=[256, 256, 130],
            spacing=[1.0, 1.0, 1.3],
            origin=[-127.5, -127.5, -84.5],
            modality="MR",
            patient_id="PAT001",
            study_description="Brain MRI",
        )
        self.assertEqual(scan.filename, "brain_mri.nrrd")
        self.assertEqual(scan.dimensions, [256, 256, 130])
        self.assertEqual(scan.modality, "MR")

    def test_to_dict_excludes_volume_node_id(self):
        scan = ScanMetadata(volume_node_id="vtkMRMLScalarVolumeNode1")
        d = scan.to_dict()
        self.assertNotIn("volume_node_id", d)

    def test_to_dict_values(self):
        scan = ScanMetadata(
            filename="test.nii.gz",
            filepath="/tmp/test.nii.gz",
            file_format="nifti",
            dimensions=[512, 512, 300],
            spacing=[0.5, 0.5, 1.0],
            origin=[0.0, 0.0, 0.0],
            modality="CT",
        )
        d = scan.to_dict()
        self.assertEqual(d["filename"], "test.nii.gz")
        self.assertEqual(d["file_format"], "nifti")
        self.assertEqual(d["dimensions"], [512, 512, 300])
        self.assertEqual(d["spacing"], [0.5, 0.5, 1.0])
        self.assertEqual(d["modality"], "CT")

    def test_from_dict_round_trip(self):
        scan = ScanMetadata(
            filename="scan.mha",
            filepath="/data/scan.mha",
            file_format="metaimage",
            dimensions=[128, 128, 64],
            spacing=[2.0, 2.0, 3.0],
            origin=[10.0, 20.0, 30.0],
            modality="PET",
            patient_id="P123",
            study_description="PET Scan",
        )
        d = scan.to_dict()
        restored = ScanMetadata.from_dict(d)
        self.assertEqual(restored.filename, "scan.mha")
        self.assertEqual(restored.filepath, "/data/scan.mha")
        self.assertEqual(restored.file_format, "metaimage")
        self.assertEqual(restored.dimensions, [128, 128, 64])
        self.assertEqual(restored.spacing, [2.0, 2.0, 3.0])
        self.assertEqual(restored.origin, [10.0, 20.0, 30.0])
        self.assertEqual(restored.modality, "PET")
        self.assertEqual(restored.patient_id, "P123")
        self.assertEqual(restored.study_description, "PET Scan")
        self.assertEqual(restored.volume_node_id, "")

    def test_from_dict_missing_fields(self):
        data = {"filename": "minimal.nrrd"}
        scan = ScanMetadata.from_dict(data)
        self.assertEqual(scan.filename, "minimal.nrrd")
        self.assertEqual(scan.dimensions, [])
        self.assertEqual(scan.modality, "")


class TestAnnotationRecordWithScan(unittest.TestCase):
    def test_record_with_scan_round_trip(self):
        scan = ScanMetadata(
            filename="brain.nrrd",
            dimensions=[256, 256, 130],
            spacing=[1.0, 1.0, 1.3],
        )
        record = AnnotationRecord(study_id="SCAN-TEST", scan=scan)
        d = record.to_dict()
        restored = AnnotationRecord.from_dict(d)
        self.assertIsNotNone(restored.scan)
        self.assertEqual(restored.scan.filename, "brain.nrrd")
        self.assertEqual(restored.scan.dimensions, [256, 256, 130])

    def test_record_with_none_scan(self):
        record = AnnotationRecord(scan=None)
        d = record.to_dict()
        self.assertIsNone(d["scan"])
        restored = AnnotationRecord.from_dict(d)
        self.assertIsNone(restored.scan)

    def test_full_record_round_trip(self):
        """All fields populated: scan + labels + ROIs + segmentation."""
        record = AnnotationRecord(
            study_id="FULL",
            series_id="S1",
            created_by="tester",
            scan=ScanMetadata(
                filename="full.nrrd",
                filepath="/data/full.nrrd",
                file_format="nrrd",
                dimensions=[256, 256, 128],
                spacing=[1.0, 1.0, 2.0],
                origin=[0.0, 0.0, 0.0],
            ),
            class_labels=["Normal", "Artifact"],
            rois=[
                ROIAnnotation(roi_type="line", control_points=[
                    {"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 10, "z": 0}
                ]),
            ],
            segmentation=SegmentationData(
                labels=[SegmentLabel(name="Tumor", color="#ff0000")],
                total_voxel_count=1234,
            ),
        )
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)

        self.assertEqual(restored.study_id, "FULL")
        self.assertEqual(restored.scan.filename, "full.nrrd")
        self.assertEqual(restored.scan.dimensions, [256, 256, 128])
        self.assertEqual(restored.class_labels, ["Normal", "Artifact"])
        self.assertEqual(len(restored.rois), 1)
        self.assertEqual(restored.segmentation.labels[0].name, "Tumor")
        self.assertEqual(restored.segmentation.total_voxel_count, 1234)


class TestLabelDefinition(unittest.TestCase):
    def test_default_creation(self):
        lbl = LabelDefinition()
        self.assertTrue(len(lbl.id) > 0)
        self.assertEqual(lbl.name, "")
        self.assertEqual(lbl.color, "#ff0000")
        self.assertEqual(lbl.description, "")

    def test_creation_with_values(self):
        lbl = LabelDefinition(name="Tumor", color="#e6194b", description="Tumor region")
        self.assertEqual(lbl.name, "Tumor")
        self.assertEqual(lbl.color, "#e6194b")
        self.assertEqual(lbl.description, "Tumor region")

    def test_to_dict(self):
        lbl = LabelDefinition(id="test-id", name="Edema", color="#3cb44b", description="Swelling")
        d = lbl.to_dict()
        self.assertEqual(d["id"], "test-id")
        self.assertEqual(d["name"], "Edema")
        self.assertEqual(d["color"], "#3cb44b")
        self.assertEqual(d["description"], "Swelling")

    def test_from_dict_round_trip(self):
        lbl = LabelDefinition(name="Necrosis", color="#911eb4", description="Dead tissue")
        d = lbl.to_dict()
        restored = LabelDefinition.from_dict(d)
        self.assertEqual(restored.id, lbl.id)
        self.assertEqual(restored.name, "Necrosis")
        self.assertEqual(restored.color, "#911eb4")
        self.assertEqual(restored.description, "Dead tissue")

    def test_id_stability_across_rename(self):
        lbl = LabelDefinition(name="OldName", color="#000000")
        original_id = lbl.id
        lbl.name = "NewName"
        self.assertEqual(lbl.id, original_id)

    def test_from_dict_missing_fields(self):
        data = {"name": "Minimal"}
        lbl = LabelDefinition.from_dict(data)
        self.assertEqual(lbl.name, "Minimal")
        self.assertEqual(lbl.color, "#ff0000")
        self.assertEqual(lbl.description, "")
        self.assertTrue(len(lbl.id) > 0)


class TestLabelConfig(unittest.TestCase):
    def test_default_creation(self):
        config = LabelConfig()
        self.assertEqual(config.class_labels, [])
        self.assertEqual(config.roi_labels, [])
        self.assertEqual(config.segmentation_classes, [])

    def test_creation_with_labels(self):
        config = LabelConfig(
            class_labels=[LabelDefinition(name="Normal"), LabelDefinition(name="Abnormal")],
            roi_labels=[LabelDefinition(name="Tumor")],
            segmentation_classes=[LabelDefinition(name="Tumor Core")],
        )
        self.assertEqual(len(config.class_labels), 2)
        self.assertEqual(len(config.roi_labels), 1)
        self.assertEqual(len(config.segmentation_classes), 1)

    def test_to_dict(self):
        config = LabelConfig(
            class_labels=[LabelDefinition(name="Normal", color="#4CAF50")],
            roi_labels=[LabelDefinition(name="Tumor", color="#e6194b")],
            segmentation_classes=[LabelDefinition(name="Edema", color="#3cb44b")],
        )
        d = config.to_dict()
        self.assertEqual(len(d["class_labels"]), 1)
        self.assertEqual(d["class_labels"][0]["name"], "Normal")
        self.assertEqual(len(d["roi_labels"]), 1)
        self.assertEqual(d["roi_labels"][0]["name"], "Tumor")
        self.assertEqual(len(d["segmentation_classes"]), 1)
        self.assertEqual(d["segmentation_classes"][0]["name"], "Edema")

    def test_from_dict_round_trip(self):
        config = LabelConfig(
            class_labels=[
                LabelDefinition(name="Normal", color="#4CAF50", description="No findings"),
                LabelDefinition(name="Pathological", color="#f44336", description="Has findings"),
            ],
            roi_labels=[
                LabelDefinition(name="Tumor", color="#e6194b"),
                LabelDefinition(name="Lesion", color="#f58231"),
            ],
            segmentation_classes=[
                LabelDefinition(name="Tumor Core", color="#e6194b"),
                LabelDefinition(name="Edema", color="#3cb44b"),
            ],
        )
        d = config.to_dict()
        restored = LabelConfig.from_dict(d)
        self.assertEqual(len(restored.class_labels), 2)
        self.assertEqual(restored.class_labels[0].name, "Normal")
        self.assertEqual(restored.class_labels[1].name, "Pathological")
        self.assertEqual(len(restored.roi_labels), 2)
        self.assertEqual(len(restored.segmentation_classes), 2)

    def test_empty_categories_round_trip(self):
        config = LabelConfig(
            class_labels=[LabelDefinition(name="Normal")],
            roi_labels=[],
            segmentation_classes=[],
        )
        d = config.to_dict()
        restored = LabelConfig.from_dict(d)
        self.assertEqual(len(restored.class_labels), 1)
        self.assertEqual(restored.roi_labels, [])
        self.assertEqual(restored.segmentation_classes, [])

    def test_from_dict_empty_data(self):
        config = LabelConfig.from_dict({})
        self.assertEqual(config.class_labels, [])
        self.assertEqual(config.roi_labels, [])
        self.assertEqual(config.segmentation_classes, [])


class TestAnnotationRecordWithLabelConfig(unittest.TestCase):
    def test_record_with_label_config_round_trip(self):
        config = LabelConfig(
            class_labels=[LabelDefinition(name="Normal", color="#4CAF50")],
            roi_labels=[LabelDefinition(name="Tumor", color="#e6194b")],
            segmentation_classes=[LabelDefinition(name="Edema", color="#3cb44b")],
        )
        record = AnnotationRecord(label_config=config, class_labels=["Normal"])
        d = record.to_dict()
        self.assertIsNotNone(d["label_config"])
        self.assertEqual(d["label_config"]["class_labels"][0]["name"], "Normal")

        restored = AnnotationRecord.from_dict(d)
        self.assertIsNotNone(restored.label_config)
        self.assertEqual(len(restored.label_config.class_labels), 1)
        self.assertEqual(restored.label_config.class_labels[0].name, "Normal")
        self.assertEqual(len(restored.label_config.roi_labels), 1)

    def test_record_with_none_label_config(self):
        record = AnnotationRecord(label_config=None)
        d = record.to_dict()
        self.assertIsNone(d["label_config"])
        restored = AnnotationRecord.from_dict(d)
        self.assertIsNone(restored.label_config)

    def test_from_dict_without_label_config_key(self):
        """Old format without label_config field loads fine."""
        data = {
            "id": "no-config",
            "class_labels": ["Normal"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertIsNone(record.label_config)
        self.assertEqual(record.class_labels, ["Normal"])

    def test_preset_json_format(self):
        """Verify preset dict can be converted to LabelConfig."""
        preset = {
            "class_labels": [
                {"name": "Normal", "color": "#4CAF50", "description": "No findings"},
            ],
            "roi_labels": [
                {"name": "Tumor", "color": "#e6194b", "description": "Tumor region"},
            ],
            "segmentation_classes": [
                {"name": "Edema", "color": "#3cb44b", "description": "Swelling"},
            ],
        }
        config = LabelConfig(
            class_labels=[LabelDefinition(name=d["name"], color=d["color"], description=d["description"])
                          for d in preset["class_labels"]],
            roi_labels=[LabelDefinition(name=d["name"], color=d["color"], description=d["description"])
                        for d in preset["roi_labels"]],
            segmentation_classes=[LabelDefinition(name=d["name"], color=d["color"], description=d["description"])
                                  for d in preset["segmentation_classes"]],
        )
        d = config.to_dict()
        restored = LabelConfig.from_dict(d)
        self.assertEqual(restored.class_labels[0].name, "Normal")
        self.assertEqual(restored.roi_labels[0].description, "Tumor region")


class TestBackwardCompatibility(unittest.TestCase):
    """Test loading old format JSON files with removed/missing fields."""

    def test_old_format_with_removed_fields(self):
        old_data = {
            "id": "compat-test",
            "study_id": "STUDY-OLD",
            "status": "approved",
            "reviewed_by": "reviewer1",
            "freeform_data": {"notes": "some data"},
            "class_labels": ["Normal"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(old_data)
        self.assertEqual(record.id, "compat-test")
        self.assertEqual(record.class_labels, ["Normal"])
        self.assertIsNone(record.scan)

    def test_unknown_keys_do_not_crash(self):
        data = {
            "id": "future-test",
            "unknown_field": "anything",
            "class_labels": ["A"],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertEqual(record.id, "future-test")
        self.assertEqual(record.class_labels, ["A"])


if __name__ == "__main__":
    unittest.main()
