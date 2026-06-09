"""Unit tests for AnnotationModel.py"""
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AnnotationModel import (
    AnnotationRecord, ROIAnnotation, SegmentationData, SegmentLabel
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

    def test_no_status_or_reviewer_fields(self):
        record = AnnotationRecord()
        self.assertFalse(hasattr(record, "status"))
        self.assertFalse(hasattr(record, "reviewed_by"))
        self.assertFalse(hasattr(record, "reviewed_at"))
        self.assertFalse(hasattr(record, "review_comments"))
        self.assertFalse(hasattr(record, "freeform_data"))


class TestToDict(unittest.TestCase):
    def test_to_dict_has_all_keys(self):
        record = AnnotationRecord()
        d = record.to_dict()
        expected_keys = {
            "id", "study_id", "series_id", "created_by", "created_at",
            "class_labels", "rois", "segmentation",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_does_not_contain_removed_fields(self):
        record = AnnotationRecord()
        d = record.to_dict()
        self.assertNotIn("status", d)
        self.assertNotIn("reviewed_by", d)
        self.assertNotIn("reviewed_at", d)
        self.assertNotIn("review_comments", d)
        self.assertNotIn("freeform_data", d)

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
        self.assertEqual(d["rois"][0]["control_points"][0]["x"], 100.0)
        self.assertEqual(d["rois"][0]["radii"], [30.0, 20.0])

    def test_to_dict_with_segmentation(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="Tumor", color="#ff0000", segment_id="Segment_1")],
            total_voxel_count=5000,
            per_label_voxel_counts={"Tumor": 5000},
        )
        record = AnnotationRecord(segmentation=seg)
        d = record.to_dict()
        self.assertIsNotNone(d["segmentation"])
        self.assertEqual(len(d["segmentation"]["labels"]), 1)
        self.assertEqual(d["segmentation"]["labels"][0]["name"], "Tumor")
        self.assertEqual(d["segmentation"]["total_voxel_count"], 5000)


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
        )
        d = record.to_dict()
        restored = AnnotationRecord.from_dict(d)

        self.assertEqual(restored.id, record.id)
        self.assertEqual(restored.study_id, record.study_id)
        self.assertEqual(restored.series_id, record.series_id)
        self.assertEqual(restored.class_labels, record.class_labels)
        self.assertEqual(len(restored.rois), 1)
        self.assertEqual(restored.rois[0].roi_type, "rectangle")
        self.assertEqual(restored.rois[0].radii, [5.0, 3.0])
        self.assertIsNotNone(restored.segmentation)
        self.assertEqual(restored.segmentation.labels[0].name, "bg")

    def test_from_dict_missing_optional_fields(self):
        minimal = {"id": "test-id"}
        record = AnnotationRecord.from_dict(minimal)
        self.assertEqual(record.id, "test-id")
        self.assertEqual(record.class_labels, [])
        self.assertIsNone(record.segmentation)

    def test_from_dict_ignores_old_fields(self):
        """Loading an old JSON with removed fields should not crash."""
        old_data = {
            "id": "old-record",
            "study_id": "S-OLD",
            "status": "approved",
            "reviewed_by": "reviewer1",
            "reviewed_at": "2024-01-01T00:00:00",
            "review_comments": "Looks good",
            "freeform_data": {"key": "value", "nested": {"a": 1}},
            "class_labels": ["Normal"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(old_data)
        self.assertEqual(record.id, "old-record")
        self.assertEqual(record.study_id, "S-OLD")
        self.assertEqual(record.class_labels, ["Normal"])
        self.assertFalse(hasattr(record, "status"))
        self.assertFalse(hasattr(record, "reviewed_by"))
        self.assertFalse(hasattr(record, "freeform_data"))


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
        self.assertEqual(restored.label, "Region B")
        self.assertEqual(len(restored.control_points), 3)
        self.assertEqual(restored.mrml_node_id, "")

    def test_empty_rois_list_round_trips_as_empty_list(self):
        record = AnnotationRecord(rois=[])
        d = record.to_dict()
        self.assertEqual(d["rois"], [])
        restored = AnnotationRecord.from_dict(d)
        self.assertEqual(restored.rois, [])
        self.assertIsInstance(restored.rois, list)


class TestSegmentLabel(unittest.TestCase):
    def test_default_creation(self):
        lbl = SegmentLabel()
        self.assertTrue(len(lbl.id) > 0)
        self.assertEqual(lbl.name, "")
        self.assertEqual(lbl.color, "#ff0000")
        self.assertEqual(lbl.segment_id, "")

    def test_creation_with_values(self):
        lbl = SegmentLabel(
            name="Tumor",
            color="#00ff00",
            segment_id="Segment_1",
            description="Primary tumor region",
        )
        self.assertEqual(lbl.name, "Tumor")
        self.assertEqual(lbl.color, "#00ff00")
        self.assertEqual(lbl.segment_id, "Segment_1")
        self.assertEqual(lbl.description, "Primary tumor region")

    def test_to_dict(self):
        lbl = SegmentLabel(name="Edema", color="#ffff00", segment_id="S2")
        d = lbl.to_dict()
        self.assertEqual(d["name"], "Edema")
        self.assertEqual(d["color"], "#ffff00")
        self.assertEqual(d["segment_id"], "S2")
        self.assertIn("id", d)

    def test_from_dict_round_trip(self):
        lbl = SegmentLabel(
            name="Necrosis",
            color="#800080",
            segment_id="Segment_3",
            description="Necrotic core",
        )
        d = lbl.to_dict()
        restored = SegmentLabel.from_dict(d)
        self.assertEqual(restored.id, lbl.id)
        self.assertEqual(restored.name, "Necrosis")
        self.assertEqual(restored.color, "#800080")
        self.assertEqual(restored.segment_id, "Segment_3")
        self.assertEqual(restored.description, "Necrotic core")


class TestSegmentationData(unittest.TestCase):
    def test_default_creation(self):
        seg = SegmentationData()
        self.assertEqual(seg.labels, [])
        self.assertEqual(seg.export_format, "nrrd")
        self.assertEqual(seg.export_filepath, "")
        self.assertEqual(seg.segmentation_node_id, "")
        self.assertEqual(seg.total_voxel_count, 0)
        self.assertEqual(seg.per_label_voxel_counts, {})

    def test_to_dict_excludes_segmentation_node_id(self):
        seg = SegmentationData(segmentation_node_id="vtkMRMLSegmentationNode1")
        d = seg.to_dict()
        self.assertNotIn("segmentation_node_id", d)

    def test_to_dict_with_labels(self):
        seg = SegmentationData(
            labels=[
                SegmentLabel(name="Tumor", color="#ff0000", segment_id="S1"),
                SegmentLabel(name="Edema", color="#ffff00", segment_id="S2"),
            ],
            export_format="nifti",
            export_filepath="/tmp/seg.nii.gz",
            total_voxel_count=12000,
            per_label_voxel_counts={"Tumor": 8000, "Edema": 4000},
        )
        d = seg.to_dict()
        self.assertEqual(len(d["labels"]), 2)
        self.assertEqual(d["labels"][0]["name"], "Tumor")
        self.assertEqual(d["export_format"], "nifti")
        self.assertEqual(d["export_filepath"], "/tmp/seg.nii.gz")
        self.assertEqual(d["total_voxel_count"], 12000)
        self.assertEqual(d["per_label_voxel_counts"]["Tumor"], 8000)

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
        self.assertEqual(len(restored.labels), 1)
        self.assertEqual(restored.labels[0].name, "WM")
        self.assertEqual(restored.labels[0].color, "#ffffff")
        self.assertEqual(restored.export_format, "nrrd")
        self.assertEqual(restored.export_filepath, "/data/mask.nrrd")
        self.assertEqual(restored.total_voxel_count, 50000)
        self.assertEqual(restored.per_label_voxel_counts["WM"], 50000)
        self.assertEqual(restored.segmentation_node_id, "")

    def test_per_label_voxel_counts_serializes_with_string_keys(self):
        seg = SegmentationData(
            per_label_voxel_counts={"Label A": 100, "Label B": 200},
        )
        d = seg.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["per_label_voxel_counts"]["Label A"], 100)
        self.assertEqual(parsed["per_label_voxel_counts"]["Label B"], 200)


class TestAnnotationRecordWithSegmentation(unittest.TestCase):
    def test_record_with_segmentation_round_trip(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="T", color="#ff0000")],
            total_voxel_count=999,
        )
        record = AnnotationRecord(study_id="SEG-TEST", segmentation=seg)
        d = record.to_dict()
        restored = AnnotationRecord.from_dict(d)
        self.assertIsNotNone(restored.segmentation)
        self.assertEqual(restored.segmentation.labels[0].name, "T")
        self.assertEqual(restored.segmentation.total_voxel_count, 999)

    def test_record_with_none_segmentation(self):
        record = AnnotationRecord(segmentation=None)
        d = record.to_dict()
        self.assertIsNone(d["segmentation"])
        restored = AnnotationRecord.from_dict(d)
        self.assertIsNone(restored.segmentation)

    def test_json_round_trip_with_segmentation(self):
        seg = SegmentationData(
            labels=[
                SegmentLabel(name="A", color="#aaaaaa"),
                SegmentLabel(name="B", color="#bbbbbb"),
            ],
            export_format="nifti",
            per_label_voxel_counts={"A": 1000, "B": 2000},
            total_voxel_count=3000,
        )
        record = AnnotationRecord(segmentation=seg)
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)
        self.assertEqual(len(restored.segmentation.labels), 2)
        self.assertEqual(restored.segmentation.total_voxel_count, 3000)


class TestBackwardCompatibility(unittest.TestCase):
    """Test loading old format JSON files with removed fields."""

    def test_old_format_with_all_removed_fields(self):
        old_data = {
            "id": "compat-test",
            "study_id": "STUDY-OLD",
            "series_id": "SERIES-OLD",
            "created_by": "old_user",
            "created_at": "2024-01-01T00:00:00",
            "status": "approved",
            "reviewed_by": "reviewer_person",
            "reviewed_at": "2024-01-02T00:00:00",
            "review_comments": "All good",
            "freeform_data": {"notes": "some data", "nested": {"key": 42}},
            "class_labels": ["Normal", "Pathological"],
            "rois": [
                {
                    "id": "roi-1",
                    "roi_type": "line",
                    "label": "Measurement",
                    "color": "#00ff00",
                    "control_points": [{"x": 0, "y": 0, "z": 0}],
                }
            ],
            "segmentation": None,
        }
        record = AnnotationRecord.from_dict(old_data)
        self.assertEqual(record.id, "compat-test")
        self.assertEqual(record.study_id, "STUDY-OLD")
        self.assertEqual(record.class_labels, ["Normal", "Pathological"])
        self.assertEqual(len(record.rois), 1)
        self.assertEqual(record.rois[0].roi_type, "line")
        self.assertIsNone(record.segmentation)

    def test_old_format_with_unknown_keys_does_not_crash(self):
        data = {
            "id": "future-test",
            "unknown_field_1": "anything",
            "unknown_field_2": [1, 2, 3],
            "class_labels": ["A"],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertEqual(record.id, "future-test")
        self.assertEqual(record.class_labels, ["A"])


if __name__ == "__main__":
    unittest.main()
