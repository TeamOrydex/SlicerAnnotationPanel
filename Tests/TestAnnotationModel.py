"""Unit tests for AnnotationModel.py"""
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AnnotationModel import AnnotationRecord, ROIAnnotation, SegmentationData


class TestAnnotationRecordCreation(unittest.TestCase):
    def test_default_creation(self):
        record = AnnotationRecord()
        self.assertTrue(len(record.id) > 0)
        self.assertEqual(record.study_id, "")
        self.assertEqual(record.series_id, "")
        self.assertEqual(record.status, "draft")
        self.assertEqual(record.class_labels, [])
        self.assertEqual(record.rois, [])
        self.assertIsNone(record.segmentation)
        self.assertEqual(record.freeform_data, {})
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
            "status", "reviewed_by", "reviewed_at", "review_comments",
            "class_labels", "rois", "segmentation", "freeform_data",
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
            format="rle",
            labels=[{"name": "tumor", "color": "#ff0000"}],
            slices={0: "encoded_data_here"},
        )
        record = AnnotationRecord(segmentation=seg)
        d = record.to_dict()
        self.assertIsNotNone(d["segmentation"])
        self.assertEqual(d["segmentation"]["format"], "rle")
        self.assertEqual(d["segmentation"]["slices"]["0"], "encoded_data_here")


class TestFromDict(unittest.TestCase):
    def test_round_trip(self):
        record = AnnotationRecord(
            study_id="STUDY-RT",
            series_id="SERIES-RT",
            created_by="user1",
            status="submitted",
            class_labels=["Normal", "Artifact"],
            rois=[ROIAnnotation(roi_type="rectangle", slice_index=10,
                                control_points=[{"x": 1.0, "y": 2.0, "z": 3.0}],
                                radii=[5.0, 3.0])],
            segmentation=SegmentationData(labels=[{"name": "bg", "color": "#000"}]),
            freeform_data={"notes": "test note"},
        )
        d = record.to_dict()
        restored = AnnotationRecord.from_dict(d)

        self.assertEqual(restored.id, record.id)
        self.assertEqual(restored.study_id, record.study_id)
        self.assertEqual(restored.series_id, record.series_id)
        self.assertEqual(restored.status, record.status)
        self.assertEqual(restored.class_labels, record.class_labels)
        self.assertEqual(len(restored.rois), 1)
        self.assertEqual(restored.rois[0].roi_type, "rectangle")
        self.assertEqual(restored.rois[0].radii, [5.0, 3.0])
        self.assertIsNotNone(restored.segmentation)
        self.assertEqual(restored.freeform_data["notes"], "test note")

    def test_from_dict_missing_optional_fields(self):
        minimal = {"id": "test-id", "status": "draft"}
        record = AnnotationRecord.from_dict(minimal)
        self.assertEqual(record.id, "test-id")
        self.assertEqual(record.class_labels, [])
        self.assertIsNone(record.segmentation)


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
            freeform_data={"key": [1, 2, 3]},
        )
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)
        self.assertEqual(restored.study_id, "JSON-TEST")
        self.assertEqual(restored.class_labels, ["Pathological", "Motion Blur"])
        self.assertEqual(restored.freeform_data["key"], [1, 2, 3])


class TestClassLabels(unittest.TestCase):
    def test_set_and_get_labels(self):
        record = AnnotationRecord()
        record.class_labels = ["Normal", "Artifact"]
        self.assertEqual(record.class_labels, ["Normal", "Artifact"])

    def test_labels_persist_through_serialization(self):
        record = AnnotationRecord(class_labels=["A", "B", "C"])
        restored = AnnotationRecord.from_dict(record.to_dict())
        self.assertEqual(restored.class_labels, ["A", "B", "C"])


class TestStatusTransitions(unittest.TestCase):
    def test_draft_to_submitted(self):
        record = AnnotationRecord()
        self.assertEqual(record.status, "draft")
        record.status = "submitted"
        self.assertEqual(record.status, "submitted")

    def test_submitted_to_approved(self):
        record = AnnotationRecord(status="submitted")
        record.status = "approved"
        record.reviewed_by = "reviewer1"
        record.reviewed_at = "2024-01-01T00:00:00"
        self.assertEqual(record.status, "approved")
        self.assertEqual(record.reviewed_by, "reviewer1")

    def test_submitted_to_rejected(self):
        record = AnnotationRecord(status="submitted")
        record.status = "rejected"
        record.reviewed_by = "reviewer2"
        record.reviewed_at = "2024-01-02T00:00:00"
        record.review_comments = "Incomplete labels"
        self.assertEqual(record.status, "rejected")
        self.assertEqual(record.review_comments, "Incomplete labels")


class TestROIAnnotation(unittest.TestCase):
    def test_default_creation(self):
        roi = ROIAnnotation()
        self.assertTrue(len(roi.id) > 0)
        self.assertEqual(roi.roi_type, "")
        self.assertEqual(roi.label, "")
        self.assertEqual(roi.color, "#ff0000")
        self.assertEqual(roi.control_points, [])
        self.assertEqual(roi.radii, [])
        self.assertEqual(roi.orientation, [])
        self.assertEqual(roi.mrml_node_id, "")

    def test_creation_with_values(self):
        roi = ROIAnnotation(
            roi_type="polygon",
            label="Tumor",
            color="#00ff00",
            slice_view="Red",
            slice_index=42,
            control_points=[
                {"x": 0.0, "y": 0.0, "z": 0.0},
                {"x": 10.0, "y": 10.0, "z": 0.0},
                {"x": 20.0, "y": 0.0, "z": 0.0},
            ],
            description="Sample polygon ROI",
        )
        self.assertEqual(roi.roi_type, "polygon")
        self.assertEqual(roi.label, "Tumor")
        self.assertEqual(roi.slice_view, "Red")
        self.assertEqual(len(roi.control_points), 3)

    def test_to_dict_excludes_mrml_node_id(self):
        roi = ROIAnnotation(mrml_node_id="vtkMRMLMarkupsLineNode1")
        d = roi.to_dict()
        self.assertNotIn("mrml_node_id", d)

    def test_to_dict_includes_all_fields(self):
        roi = ROIAnnotation(
            roi_type="ellipse",
            label="Test",
            color="#abcdef",
            slice_view="Green",
            slice_index=10,
            control_points=[{"x": 1.0, "y": 2.0, "z": 3.0}],
            radii=[5.0, 3.0],
            orientation=[1, 0, 0, 0, 1, 0, 0, 0, 1],
            description="An ellipse",
        )
        d = roi.to_dict()
        self.assertEqual(d["roi_type"], "ellipse")
        self.assertEqual(d["label"], "Test")
        self.assertEqual(d["color"], "#abcdef")
        self.assertEqual(d["slice_view"], "Green")
        self.assertEqual(d["slice_index"], 10)
        self.assertEqual(d["control_points"], [{"x": 1.0, "y": 2.0, "z": 3.0}])
        self.assertEqual(d["radii"], [5.0, 3.0])
        self.assertEqual(d["orientation"], [1, 0, 0, 0, 1, 0, 0, 0, 1])
        self.assertEqual(d["description"], "An ellipse")
        self.assertIn("id", d)
        self.assertIn("created_at", d)

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
            radii=[],
            orientation=[],
            description="A freehand curve",
        )
        d = roi.to_dict()
        restored = ROIAnnotation.from_dict(d)
        self.assertEqual(restored.id, roi.id)
        self.assertEqual(restored.roi_type, "freehand_curve")
        self.assertEqual(restored.label, "Region B")
        self.assertEqual(restored.color, "#123456")
        self.assertEqual(restored.slice_view, "Yellow")
        self.assertEqual(restored.slice_index, 99)
        self.assertEqual(len(restored.control_points), 3)
        self.assertEqual(restored.control_points[2]["z"], 5.0)
        self.assertEqual(restored.description, "A freehand curve")
        self.assertEqual(restored.mrml_node_id, "")

    def test_from_dict_with_radii_and_orientation(self):
        data = {
            "id": "roi-orient-test",
            "roi_type": "ellipse",
            "label": "Oriented",
            "color": "#ff00ff",
            "slice_view": "Red",
            "slice_index": 5,
            "control_points": [{"x": 10.0, "y": 20.0, "z": 0.0}],
            "radii": [8.0, 4.0],
            "orientation": [0.707, 0.707, 0, -0.707, 0.707, 0, 0, 0, 1],
            "description": "",
            "created_at": "2024-06-01T00:00:00",
        }
        roi = ROIAnnotation.from_dict(data)
        self.assertEqual(roi.id, "roi-orient-test")
        self.assertEqual(roi.radii, [8.0, 4.0])
        self.assertEqual(len(roi.orientation), 9)
        self.assertAlmostEqual(roi.orientation[0], 0.707)

    def test_empty_roi_serialization(self):
        roi = ROIAnnotation()
        d = roi.to_dict()
        self.assertEqual(d["roi_type"], "")
        self.assertEqual(d["control_points"], [])
        self.assertEqual(d["radii"], [])
        self.assertEqual(d["orientation"], [])


class TestAnnotationRecordWithROIs(unittest.TestCase):
    def test_record_with_populated_rois(self):
        rois = [
            ROIAnnotation(roi_type="line", label="L1",
                          control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 10, "z": 0}]),
            ROIAnnotation(roi_type="polygon", label="L2",
                          control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 5, "z": 0},
                                          {"x": 10, "y": 0, "z": 0}]),
        ]
        record = AnnotationRecord(rois=rois)
        d = record.to_dict()
        self.assertEqual(len(d["rois"]), 2)
        self.assertEqual(d["rois"][0]["roi_type"], "line")
        self.assertEqual(d["rois"][1]["roi_type"], "polygon")

        restored = AnnotationRecord.from_dict(d)
        self.assertEqual(len(restored.rois), 2)
        self.assertEqual(restored.rois[0].label, "L1")
        self.assertEqual(restored.rois[1].label, "L2")
        self.assertEqual(len(restored.rois[0].control_points), 2)
        self.assertEqual(len(restored.rois[1].control_points), 3)

    def test_empty_rois_list_round_trips_as_empty_list(self):
        record = AnnotationRecord(rois=[])
        d = record.to_dict()
        self.assertEqual(d["rois"], [])
        self.assertIsInstance(d["rois"], list)

        restored = AnnotationRecord.from_dict(d)
        self.assertEqual(restored.rois, [])
        self.assertIsInstance(restored.rois, list)

    def test_json_round_trip_with_rois(self):
        roi = ROIAnnotation(
            roi_type="ellipse",
            label="Tumor",
            radii=[12.5, 8.3],
            control_points=[{"x": -5.0, "y": 3.2, "z": 1.0}],
        )
        record = AnnotationRecord(
            study_id="ROI-JSON-TEST",
            rois=[roi],
        )
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)
        self.assertEqual(restored.study_id, "ROI-JSON-TEST")
        self.assertEqual(len(restored.rois), 1)
        self.assertEqual(restored.rois[0].roi_type, "ellipse")
        self.assertEqual(restored.rois[0].radii, [12.5, 8.3])


class TestSegmentationData(unittest.TestCase):
    def test_empty_segmentation_serialization(self):
        seg = SegmentationData()
        d = seg.to_dict()
        self.assertEqual(d["format"], "rle")
        self.assertEqual(d["labels"], [])
        self.assertEqual(d["slices"], {})

    def test_segmentation_round_trip(self):
        seg = SegmentationData(
            format="rle",
            labels=[{"name": "tumor", "color": "#ff0000"}],
            slices={5: "rle_data_5", 10: "rle_data_10"},
        )
        d = seg.to_dict()
        restored = SegmentationData.from_dict(d)
        self.assertEqual(restored.format, "rle")
        self.assertEqual(len(restored.labels), 1)
        self.assertEqual(restored.slices[5], "rle_data_5")
        self.assertEqual(restored.slices[10], "rle_data_10")


if __name__ == "__main__":
    unittest.main()
