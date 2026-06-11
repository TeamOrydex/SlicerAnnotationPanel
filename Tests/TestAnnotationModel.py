"""Unit tests for AnnotationModel.py"""
import unittest
import json
import sys
import os
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AnnotationModel import (
    AnnotationRecord, ROIAnnotation, SegmentationData, SegmentLabel, ScanMetadata,
    LabelDefinition, LabelConfig, ClassLabelAnnotation, PlaneSliceContext,
    SegmentSpatialExtent, SegmentModificationEvent,
    should_record_segment_modification, VOLUME_SCOPED_EFFECTS,
    derive_export_folder_name, resolve_unique_export_subdirectory,
    resolve_import_paths, build_record_from_import,
    reconcile_imported_record, derive_import_preset_name,
    label_configs_differ,
    segment_label_def_for_label_value,
    EXPORT_ANNOTATIONS_FILENAME, EXPORT_SEGMENTATION_FILENAME,
)
from RadiologyTerms import slice_view_to_plane, roi_geometry_type_export
from SliceInfo import anatomical_slice_index_from_ijk


class TestAnatomicalSliceIndex(unittest.TestCase):
    def test_anatomical_slice_index_from_ijk(self):
        self.assertEqual(anatomical_slice_index_from_ijk("Axial", [255, 255, 45]), 45)
        self.assertEqual(anatomical_slice_index_from_ijk("Coronal", [128, 200, 50]), 200)
        self.assertEqual(anatomical_slice_index_from_ijk("Sagittal", [88, 128, 30]), 88)


class TestSliceViewMapping(unittest.TestCase):
    def test_slice_view_to_plane(self):
        self.assertEqual(slice_view_to_plane("Red"), "Axial")
        self.assertEqual(slice_view_to_plane("Green"), "Coronal")
        self.assertEqual(slice_view_to_plane("Yellow"), "Sagittal")
        self.assertEqual(slice_view_to_plane("Axial Plane"), "Axial")
        self.assertEqual(slice_view_to_plane("Axial"), "Axial")
        self.assertEqual(slice_view_to_plane(""), "")


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
        self.assertEqual(record.class_labels[0].label, "Normal")
        self.assertEqual(record.class_labels[1].label, "Artifact")


class TestToDict(unittest.TestCase):
    def test_to_dict_has_all_keys(self):
        record = AnnotationRecord()
        d = record.to_dict()
        expected_keys = {
            "schema_version", "exported_at", "slicer_version",
            "id", "study_id", "series_id", "created_by", "created_at",
            "label_configuration", "series_metadata", "classification_labels",
            "regions_of_interest", "segmentation",
            "label_config", "scan", "class_labels", "rois",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_values(self):
        record = AnnotationRecord(
            study_id="S1",
            class_labels=["Normal"],
        )
        d = record.to_dict()
        self.assertEqual(d["study_id"], "S1")
        self.assertEqual(d["classification_labels"][0]["category"], "Normal")
        self.assertEqual(d["regions_of_interest"], [])
        self.assertIsNone(d["segmentation"])
        self.assertIsNone(d["series_metadata"])

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
        self.assertEqual(len(d["regions_of_interest"]), 1)
        self.assertEqual(d["regions_of_interest"][0]["geometry_type"], "Ellipse")

    def test_to_dict_with_segmentation(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="Tumor", color="#ff0000", segment_id="Segment_1")],
            total_voxel_count=5000,
            per_label_voxel_counts={"Tumor": 5000},
        )
        record = AnnotationRecord(segmentation=seg)
        d = record.to_dict()
        self.assertIsNotNone(d["segmentation"])
        self.assertEqual(d["segmentation"]["segments"][0]["name"], "Tumor")

    def test_to_export_dict_omits_segmentation(self):
        seg = SegmentationData(
            labels=[SegmentLabel(name="Tumor", color="#ff0000", segment_id="Segment_1")],
            total_voxel_count=5000,
        )
        record = AnnotationRecord(
            class_labels=["Normal"],
            rois=[ROIAnnotation(roi_type="line", control_points=[{"x": 0, "y": 0, "z": 0}])],
            segmentation=seg,
        )
        export_payload = record.to_export_dict()
        self.assertNotIn("segmentation", export_payload)
        self.assertEqual(len(export_payload["classification_labels"]), 1)
        self.assertEqual(len(export_payload["regions_of_interest"]), 1)
        self.assertIn("segmentation", record.to_dict())

    def test_to_export_json_round_trip_without_segmentation(self):
        record = AnnotationRecord(
            study_id="EXPORT-1",
            class_labels=["Normal"],
            rois=[ROIAnnotation(roi_type="line", control_points=[{"x": 1, "y": 2, "z": 3}])],
            segmentation=SegmentationData(
                labels=[SegmentLabel(name="Tumor", color="#ff0000")],
            ),
        )
        restored = AnnotationRecord.from_dict(json.loads(record.to_export_json()))
        self.assertIsNone(restored.segmentation)
        self.assertEqual(restored.study_id, "EXPORT-1")
        self.assertEqual(restored.class_labels[0].label, "Normal")
        self.assertEqual(len(restored.rois), 1)

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
        self.assertIsNotNone(d["series_metadata"])
        self.assertEqual(d["series_metadata"]["filename"], "brain.nrrd")
        self.assertEqual(d["series_metadata"]["dimensions"], [256, 256, 130])


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
        self.assertEqual(restored.class_labels[0].label, record.class_labels[0].label)
        self.assertEqual(restored.class_labels[1].label, record.class_labels[1].label)
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
        self.assertEqual(record.class_labels[0].label, "Normal")

    def test_from_dict_without_scan_key(self):
        """Old format without scan field loads fine."""
        data = {
            "id": "no-scan",
            "class_labels": ["A"],
            "rois": [],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertIsNone(record.scan)
        self.assertEqual(record.class_labels[0].label, "A")


class TestJsonSerialization(unittest.TestCase):
    def test_to_json_produces_valid_json(self):
        record = AnnotationRecord(class_labels=["Normal"])
        json_str = record.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["classification_labels"][0]["category"], "Normal")

    def test_json_round_trip(self):
        record = AnnotationRecord(
            study_id="JSON-TEST",
            class_labels=[
                ClassLabelAnnotation(label="Pathological"),
                ClassLabelAnnotation(label="Motion Blur"),
            ],
        )
        json_str = record.to_json()
        restored = AnnotationRecord.from_json(json_str)
        self.assertEqual(restored.study_id, "JSON-TEST")
        self.assertEqual(restored.class_labels[0].label, "Pathological")
        self.assertEqual(restored.class_labels[1].label, "Motion Blur")


class TestClassLabels(unittest.TestCase):
    def test_set_and_get_labels(self):
        record = AnnotationRecord()
        record.class_labels = [
            ClassLabelAnnotation(label="Normal"),
            ClassLabelAnnotation(label="Artifact"),
        ]
        self.assertEqual(record.class_labels[0].label, "Normal")
        self.assertEqual(record.class_labels[1].label, "Artifact")

    def test_labels_persist_through_serialization(self):
        record = AnnotationRecord(
            class_labels=[
                ClassLabelAnnotation(label="A", slice_view="Red", slice_index=42),
                ClassLabelAnnotation(label="B"),
                ClassLabelAnnotation(label="C"),
            ]
        )
        restored = AnnotationRecord.from_dict(record.to_dict())
        self.assertEqual(restored.class_labels[0].label, "A")
        self.assertEqual(restored.class_labels[0].slice_view, "Axial")
        exported = record.to_dict()["classification_labels"][0]
        self.assertNotIn("plane", exported)
        self.assertEqual(exported["plane_slices"][0]["plane"], "Axial")
        self.assertEqual(restored.class_labels[0].slice_index, 42)
        self.assertEqual(restored.class_labels[1].label, "B")
        self.assertEqual(restored.class_labels[2].label, "C")

    def test_class_label_all_planes_round_trip(self):
        annotation = ClassLabelAnnotation(
            label="Abnormal",
            category_id="cat-1",
            category_color="#f44336",
            plane_slices=[
                PlaneSliceContext(
                    slice_view="Axial Plane",
                    slice_index=41,
                    slice_offset_mm=205.0,
                    slice_position_ras=[-203.1, -203.1, 205.0],
                    volume_slice_ijk=[255, 255, 41],
                    slicer_slice_view="Red",
                ),
                PlaneSliceContext(
                    slice_view="Coronal Plane",
                    slice_index=200,
                    slice_offset_mm=120.0,
                    slice_position_ras=[-100.0, 120.0, 50.0],
                    volume_slice_ijk=[128, 200, 50],
                    slicer_slice_view="Green",
                ),
                PlaneSliceContext(
                    slice_view="Sagittal Plane",
                    slice_index=88,
                    slice_offset_mm=88.0,
                    slice_position_ras=[88.0, -50.0, 30.0],
                    volume_slice_ijk=[88, 128, 30],
                    slicer_slice_view="Yellow",
                ),
            ],
        )
        restored = ClassLabelAnnotation.from_dict(annotation.to_dict())
        self.assertEqual(restored.label, "Abnormal")
        self.assertEqual(len(restored.plane_slices), 3)
        self.assertEqual(restored.get_plane_slice("Axial").slice_index, 41)
        self.assertEqual(restored.get_plane_slice("Coronal").slice_index, 200)
        self.assertEqual(restored.get_plane_slice("Sagittal").slice_index, 88)
        exported = restored.to_dict()
        self.assertEqual(len(exported["plane_slices"]), 3)
        self.assertEqual(exported["plane_slices"][0]["slice_view"], "Axial Plane")
        self.assertEqual(exported["plane_slices"][0]["slice_index"], 41)
        self.assertEqual(exported["plane_slices"][0]["slice_offset_mm"], 205.0)
        self.assertEqual(exported["plane_slices"][0]["voxel_index_ijk"], [255, 255, 41])
        self.assertNotIn("slice_position_ras", exported["plane_slices"][0])
        self.assertNotIn("volume_slice_ijk", exported["plane_slices"][0])
        for key in (
            "plane", "slicer_slice_view", "slice_number", "slice_index",
            "slice_offset_mm", "slice_view", "position_ras", "voxel_index_ijk",
            "slice_to_ras_matrix", "field_of_view", "slice_spacing",
            "slice_normal_ras", "volume_node_id", "volume_name",
        ):
            self.assertNotIn(key, exported, f"root-level {key} should not be exported")

    def test_legacy_physical_slice_index_resolves_to_anatomical(self):
        legacy = {
            "plane": "Axial",
            "slice_view": "Axial Plane",
            "slice_number": 225,
            "slice_index": 225,
            "position_ras": [-203.1, -203.1, 225.0],
            "voxel_index_ijk": [255, 255, 45],
            "slicer_slice_view": "Red",
        }
        restored = PlaneSliceContext.from_dict(legacy)
        self.assertEqual(restored.slice_index, 45)
        self.assertEqual(restored.volume_slice_ijk, [255, 255, 45])

    def test_legacy_string_class_labels_load(self):
        record = AnnotationRecord.from_dict({"class_labels": ["Normal", "Artifact"]})
        self.assertEqual(record.class_labels[0].label, "Normal")
        self.assertEqual(record.class_labels[1].label, "Artifact")
        self.assertEqual(record.class_labels[0].slice_view, "")


class TestROIAnnotation(unittest.TestCase):
    def test_default_creation(self):
        roi = ROIAnnotation()
        self.assertTrue(len(roi.id) > 0)
        self.assertEqual(roi.roi_type, "")
        self.assertEqual(roi.control_points, [])
        self.assertEqual(roi.mrml_node_id, "")

    def test_to_dict_includes_mrml_node_id(self):
        roi = ROIAnnotation(mrml_node_id="vtkMRMLMarkupsLineNode1")
        d = roi.to_dict()
        self.assertEqual(d["mrml_node_id"], "vtkMRMLMarkupsLineNode1")

    def test_rectangle_2d_geometry_type_export(self):
        self.assertEqual(roi_geometry_type_export("rectangle_2d"), "Bounding Box 2D")

    def test_rectangle_2d_round_trip(self):
        roi = ROIAnnotation(
            roi_type="rectangle_2d",
            label="Lesion",
            color="#e6194b",
            slice_view="Red",
            slice_index=42,
            control_points=[
                {"x": 0.0, "y": 0.0, "z": 5.0},
                {"x": 10.0, "y": 0.0, "z": 5.0},
                {"x": 10.0, "y": 8.0, "z": 5.0},
                {"x": 0.0, "y": 8.0, "z": 5.0},
            ],
            bounding_box_dimensions=[10.0, 8.0, 0.0],
            radii=[5.0, 4.0, 0.0],
        )
        restored = ROIAnnotation.from_dict(roi.to_dict())
        self.assertEqual(restored.roi_type, "rectangle_2d")
        self.assertEqual(restored.geometry_type if hasattr(restored, "geometry_type") else roi_geometry_type_export(restored.roi_type), "Bounding Box 2D")
        self.assertEqual(len(restored.control_points), 4)
        self.assertEqual(restored.bounding_box_dimensions, [10.0, 8.0, 0.0])

    def test_roi_export_uses_anatomical_slice_and_physical_offset(self):
        roi = ROIAnnotation(
            roi_type="ellipse",
            label="Lesion",
            slice_view="Axial",
            slice_index=45,
            slice_offset_mm=225.0,
            slice_position_ras=[-203.1, -203.1, 225.0],
            volume_slice_ijk=[255, 255, 45],
        )
        exported = roi.to_dict()
        self.assertEqual(exported["slice_index"], 45)
        self.assertEqual(exported["slice_offset_mm"], 225.0)
        for key in ("slice_number", "roi_type", "label", "slice_view", "control_points"):
            self.assertNotIn(key, exported, f"redundant legacy key {key} should not be exported")
        self.assertNotIn("voxel_index_ijk", exported)
        self.assertNotIn("volume_slice_ijk", exported)

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
        self.assertEqual(d["plane"], "Sagittal")
        self.assertEqual(d["geometry_type"], "Freehand Contour")
        restored = ROIAnnotation.from_dict(d)
        self.assertEqual(restored.id, roi.id)
        self.assertEqual(restored.roi_type, "freehand_curve")
        self.assertEqual(len(restored.control_points), 3)
        self.assertEqual(restored.mrml_node_id, "")

    def test_rectangle_3d_exports_box_geometry_without_control_points(self):
        roi = ROIAnnotation(
            roi_type="rectangle_3d",
            label="Lesion",
            slice_view="Axial",
            slice_index=12,
            control_points=[],
            radii=[25.0, 15.0, 10.0],
            bounding_box_dimensions=[50.0, 30.0, 20.0],
            center_ras=[10.0, 20.0, 30.0],
            center_voxel_ijk=[100, 110, 12],
            orientation=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        )
        exported = roi.to_dict()
        self.assertEqual(exported["control_points_ras"], [])
        self.assertEqual(exported["radii"], [25.0, 15.0, 10.0])
        self.assertEqual(exported["bounding_box_dimensions"], [50.0, 30.0, 20.0])
        self.assertEqual(exported["center_ras"], [10.0, 20.0, 30.0])
        self.assertEqual(len(exported["orientation"]), 9)

        restored = ROIAnnotation.from_dict(exported)
        self.assertEqual(restored.radii, [25.0, 15.0, 10.0])
        self.assertEqual(restored.center_ras, [10.0, 20.0, 30.0])

    def test_all_roi_tool_types_export_geometry(self):
        cases = [
            (
                "rectangle_2d",
                ROIAnnotation(
                    roi_type="rectangle_2d",
                    control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 0, "z": 0},
                                    {"x": 1, "y": 1, "z": 0}, {"x": 0, "y": 1, "z": 0}],
                    bounding_box_dimensions=[1.0, 1.0, 0.0],
                ),
                lambda d: len(d["control_points_ras"]) >= 4 or bool(d["bounding_box_dimensions"]),
            ),
            (
                "rectangle_3d",
                ROIAnnotation(
                    roi_type="rectangle_3d",
                    radii=[5.0, 4.0, 3.0],
                    center_ras=[1.0, 2.0, 3.0],
                ),
                lambda d: bool(d["radii"]) and len(d["center_ras"]) == 3,
            ),
            (
                "polygon",
                ROIAnnotation(
                    roi_type="polygon",
                    control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0},
                                    {"x": 2, "y": 0, "z": 0}],
                ),
                lambda d: len(d["control_points_ras"]) >= 3,
            ),
            (
                "freehand_curve",
                ROIAnnotation(
                    roi_type="freehand_curve",
                    control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0}],
                ),
                lambda d: len(d["control_points_ras"]) >= 2,
            ),
            (
                "line",
                ROIAnnotation(
                    roi_type="line",
                    control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 5, "z": 0}],
                ),
                lambda d: len(d["control_points_ras"]) >= 2,
            ),
        ]
        for tool_id, roi, check in cases:
            exported = roi.to_dict()
            self.assertTrue(check(exported), f"{tool_id} export missing geometry: {exported}")

    def test_normalize_geometry_fields_derives_radii_and_dimensions(self):
        roi = ROIAnnotation(
            roi_type="rectangle_3d",
            radii=[10.0, 5.0, 2.0],
            control_points=[],
        )
        roi.normalize_geometry_fields()
        self.assertEqual(roi.bounding_box_dimensions, [20.0, 10.0, 4.0])
        self.assertEqual(roi.number_of_control_points, 0)

        roi2 = ROIAnnotation(
            roi_type="rectangle_2d",
            bounding_box_dimensions=[8.0, 6.0, 0.0],
        )
        roi2.normalize_geometry_fields()
        self.assertEqual(roi2.radii, [4.0, 3.0, 0.0])

    def test_missing_reconstruction_fields_by_type(self):
        self.assertIn(
            "control_points_ras",
            ROIAnnotation(roi_type="line", control_points=[]).missing_reconstruction_fields(),
        )
        self.assertEqual(
            ROIAnnotation(
                roi_type="line",
                control_points=[{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0}],
            ).missing_reconstruction_fields(),
            [],
        )
        self.assertEqual(
            ROIAnnotation(
                roi_type="rectangle_3d",
                center_ras=[1.0, 2.0, 3.0],
                radii=[5.0, 4.0, 3.0],
            ).missing_reconstruction_fields(),
            [],
        )
        self.assertTrue(
            ROIAnnotation(
                roi_type="rectangle_2d",
                control_points=[
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 1, "y": 0, "z": 0},
                    {"x": 1, "y": 1, "z": 0},
                    {"x": 0, "y": 1, "z": 0},
                ],
            ).has_reconstruction_geometry()
        )

    def test_transform_handles_enabled_round_trip(self):
        roi = ROIAnnotation(roi_type="polygon", transform_handles_enabled=True)
        restored = ROIAnnotation.from_dict(roi.to_dict())
        self.assertTrue(restored.transform_handles_enabled)


class TestSegmentSpatialMetadata(unittest.TestCase):
    def test_segment_spatial_extent_round_trip(self):
        extent = SegmentSpatialExtent(
            bounds_ras=[0.0, 10.0, 0.0, 20.0, 0.0, 30.0],
            extent_ijk=[10, 50, 20, 60, 30, 70],
            center_ras=[5.0, 10.0, 15.0],
            center_voxel_ijk=[30, 40, 50],
            volume_mm3=123.4,
            surface_area_mm2=56.7,
        )
        restored = SegmentSpatialExtent.from_dict(extent.to_dict())
        self.assertEqual(restored.extent_ijk, [10, 50, 20, 60, 30, 70])
        self.assertEqual(restored.volume_mm3, 123.4)

    def test_segment_modification_event_round_trip(self):
        event = SegmentModificationEvent(
            effect_name="Threshold",
            segment_id="Lesion",
            segment_name="Lesion",
            effect_parameters={"MinimumThreshold": -100, "MaximumThreshold": 200},
            slice_context={
                "plane": "Axial",
                "slice_number": 42,
                "position_ras": [1.0, 2.0, 3.0],
                "voxel_index_ijk": [10, 20, 42],
                "slicer_slice_view": "Red",
            },
        )
        exported = event.to_dict()
        self.assertEqual(exported["effect_name"], "Threshold")
        self.assertEqual(exported["effect_parameters"]["MaximumThreshold"], 200)
        self.assertEqual(exported["slice_context"]["plane"], "Axial")
        self.assertEqual(exported["slice_context"]["slice_number"], 42)

        restored = SegmentModificationEvent.from_dict(exported)
        self.assertEqual(restored.effect_name, "Threshold")
        self.assertEqual(restored.effect_parameters["MaximumThreshold"], 200)

    def test_segment_label_includes_spatial_and_events(self):
        lbl = SegmentLabel(
            name="Spleen",
            segment_id="Spleen",
            spatial_extent=SegmentSpatialExtent(extent_ijk=[1, 2, 3, 4, 5, 6]),
            modification_events=[
                SegmentModificationEvent(effect_name="Paint", segment_id="Spleen")
            ],
            last_effect_name="Paint",
            last_effect_parameters={"BrushSize": 5},
        )
        exported = lbl.to_dict()
        self.assertIn("spatial_extent", exported)
        self.assertEqual(len(exported["modification_events"]), 1)
        self.assertEqual(exported["last_effect_name"], "Paint")


class TestSegmentModificationRecording(unittest.TestCase):
    def test_plane_local_effect_only_records_selected_segment_with_voxel_change(self):
        self.assertTrue(
            should_record_segment_modification(
                "Paint", "Infarct", "Infarct", 10, 0, 100, 50
            )
        )
        self.assertFalse(
            should_record_segment_modification(
                "Paint", "Spleen", "Infarct", 0, 0, 200, 100
            )
        )
        self.assertFalse(
            should_record_segment_modification(
                "Level tracing", "Infarct", "Infarct", 5, 5, 200, 100
            )
        )

    def test_volume_scoped_effect_ignores_empty_spurious_mtime(self):
        self.assertFalse(
            should_record_segment_modification(
                "Smoothing", "Spleen", "Infarct", 0, 0, 200, 100
            )
        )
        self.assertTrue(
            should_record_segment_modification(
                "Smoothing", "Infarct", "Infarct", 100, 120, 200, 100
            )
        )


    def test_segmentation_export_is_compact(self):
        seg = SegmentationData(
            labels=[
                SegmentLabel(
                    name="Infarct",
                    segment_id="Infarct",
                    modification_events=[
                        SegmentModificationEvent(
                            effect_name="Paint",
                            segment_id="Infarct",
                            slice_context={"plane": "Sagittal", "slice_number": 88, "slicer_slice_view": "Yellow"},
                        )
                    ],
                )
            ],
            total_voxel_count=10,
            per_label_voxel_counts={"Infarct": 10},
        )
        exported = seg.to_dict()
        self.assertIn("segments", exported)
        self.assertNotIn("labels", exported)
        self.assertNotIn("modification_events", exported)
        self.assertNotIn("total_voxel_count", exported)
        event = exported["segments"][0]["modification_events"][0]
        self.assertNotIn("plane", event)
        self.assertEqual(event["slice_context"]["plane"], "Sagittal")
        self.assertNotIn("slice_view", event["slice_context"])


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

    def test_to_dict_includes_segmentation_node_id(self):
        seg = SegmentationData(segmentation_node_id="vtkMRMLSegmentationNode1")
        d = seg.to_dict()
        self.assertEqual(d["segmentation_node_id"], "vtkMRMLSegmentationNode1")

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

    def test_to_dict_includes_volume_node_id(self):
        scan = ScanMetadata(volume_node_id="vtkMRMLScalarVolumeNode1")
        d = scan.to_dict()
        self.assertEqual(d["volume_node_id"], "vtkMRMLScalarVolumeNode1")

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
        self.assertEqual(d["pixel_spacing"], [0.5, 0.5, 1.0])
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
        self.assertIsNone(d["series_metadata"])
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
        self.assertEqual(restored.class_labels[0].label, "Normal")
        self.assertEqual(restored.class_labels[1].label, "Artifact")
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
        self.assertEqual(lbl.drawing_tool, "")
        self.assertTrue(len(lbl.id) > 0)

    def test_drawing_tool_round_trip(self):
        lbl = LabelDefinition(
            name="Lesion",
            color="#e6194b",
            drawing_tool="rectangle_3d",
        )
        restored = LabelDefinition.from_dict(lbl.to_dict())
        self.assertEqual(restored.drawing_tool, "rectangle_3d")

    def test_to_dict_omits_empty_drawing_tool(self):
        lbl = LabelDefinition(name="Normal")
        self.assertNotIn("drawing_tool", lbl.to_dict())

    def test_resolved_drawing_tool_default(self):
        lbl = LabelDefinition(name="Legacy")
        self.assertEqual(lbl.resolved_drawing_tool(), "rectangle_3d")

    def test_from_dict_accepts_display_name(self):
        lbl = LabelDefinition.from_dict(
            {"name": "Spleen", "drawing_tool": "Polygon Contour"}
        )
        self.assertEqual(lbl.drawing_tool, "polygon")

    def test_drawing_tool_changed_from(self):
        old = LabelDefinition(name="Spleen", drawing_tool="polygon")
        new = LabelDefinition(id=old.id, name="Spleen", drawing_tool="rectangle_3d")
        self.assertTrue(new.drawing_tool_changed_from(old))
        same = LabelDefinition(id=old.id, name="Spleen", drawing_tool="polygon")
        self.assertFalse(same.drawing_tool_changed_from(old))


class TestRoiLabelMatching(unittest.TestCase):
    def test_roi_matches_label_definition_by_name(self):
        from AnnotationModel import ROIAnnotation, roi_matches_label_definition

        label = LabelDefinition(name="Spleen", drawing_tool="polygon")
        roi = ROIAnnotation(label="Spleen", roi_type="polygon")
        self.assertTrue(roi_matches_label_definition(roi, label))

    def test_roi_matches_label_definition_by_category_id(self):
        from AnnotationModel import ROIAnnotation, roi_matches_label_definition

        label = LabelDefinition(name="Spleen", drawing_tool="polygon")
        roi = ROIAnnotation(label="Renamed", category_id=label.id, roi_type="polygon")
        self.assertTrue(roi_matches_label_definition(roi, label, "Old Spleen"))


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
        self.assertEqual(len(d["classification_labels"]), 1)
        self.assertEqual(d["classification_labels"][0]["name"], "Normal")
        self.assertEqual(len(d["roi_categories"]), 1)
        self.assertEqual(d["roi_categories"][0]["name"], "Tumor")
        self.assertEqual(len(d["segment_labels"]), 1)
        self.assertEqual(d["segment_labels"][0]["name"], "Edema")

    def test_roi_drawing_tool_in_config_round_trip(self):
        config = LabelConfig(
            roi_labels=[
                LabelDefinition(name="Spleen", color="#8b4513", drawing_tool="polygon"),
                LabelDefinition(name="Lesion", color="#e6194b", drawing_tool="rectangle_3d"),
            ],
        )
        restored = LabelConfig.from_dict(config.to_dict())
        self.assertEqual(restored.roi_labels[0].drawing_tool, "polygon")
        self.assertEqual(restored.roi_labels[1].drawing_tool, "rectangle_3d")

    def test_legacy_roi_labels_without_drawing_tool(self):
        data = {
            "roi_categories": [
                {"name": "Tumor", "color": "#e6194b", "description": "Tumor region"},
            ],
        }
        config = LabelConfig.from_dict(data)
        self.assertEqual(config.roi_labels[0].drawing_tool, "")
        self.assertEqual(config.roi_labels[0].resolved_drawing_tool(), "rectangle_3d")

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


class TestLabelConfigsDiffer(unittest.TestCase):
    def _config(self, **kwargs):
        defaults = {
            "class_labels": [LabelDefinition(id="c1", name="Normal", color="#4CAF50")],
            "roi_labels": [LabelDefinition(id="r1", name="Tumor", color="#e6194b", drawing_tool="rectangle_3d")],
            "segmentation_classes": [LabelDefinition(id="s1", name="Edema", color="#3cb44b")],
        }
        defaults.update(kwargs)
        return LabelConfig(**defaults)

    def test_identical_configs_do_not_differ(self):
        config = self._config()
        self.assertFalse(label_configs_differ(config, self._config()))

    def test_added_label_id_differs(self):
        left = self._config()
        right = self._config(
            class_labels=[
                LabelDefinition(id="c1", name="Normal", color="#4CAF50"),
                LabelDefinition(id="c2", name="Artifact", color="#ff0000"),
            ]
        )
        self.assertTrue(label_configs_differ(left, right))

    def test_renamed_label_differs(self):
        left = self._config()
        right = self._config(
            class_labels=[LabelDefinition(id="c1", name="Abnormal", color="#4CAF50")]
        )
        self.assertTrue(label_configs_differ(left, right))

    def test_color_change_differs(self):
        left = self._config()
        right = self._config(
            roi_labels=[LabelDefinition(id="r1", name="Tumor", color="#000000", drawing_tool="rectangle_3d")]
        )
        self.assertTrue(label_configs_differ(left, right))

    def test_roi_drawing_tool_change_differs(self):
        left = self._config()
        right = self._config(
            roi_labels=[LabelDefinition(id="r1", name="Tumor", color="#e6194b", drawing_tool="rectangle_2d")]
        )
        self.assertTrue(label_configs_differ(left, right))

    def test_none_config_handling(self):
        config = self._config()
        self.assertTrue(label_configs_differ(None, config))
        self.assertFalse(label_configs_differ(None, None))


class TestAnnotationRecordWithLabelConfig(unittest.TestCase):
    def test_record_with_label_config_round_trip(self):
        config = LabelConfig(
            class_labels=[LabelDefinition(name="Normal", color="#4CAF50")],
            roi_labels=[LabelDefinition(name="Tumor", color="#e6194b")],
            segmentation_classes=[LabelDefinition(name="Edema", color="#3cb44b")],
        )
        record = AnnotationRecord(label_config=config, class_labels=["Normal"])
        d = record.to_dict()
        self.assertIsNotNone(d["label_configuration"])
        self.assertEqual(d["label_configuration"]["classification_labels"][0]["name"], "Normal")

        restored = AnnotationRecord.from_dict(d)
        self.assertIsNotNone(restored.label_config)
        self.assertEqual(len(restored.label_config.class_labels), 1)
        self.assertEqual(restored.label_config.class_labels[0].name, "Normal")
        self.assertEqual(len(restored.label_config.roi_labels), 1)

    def test_record_with_none_label_config(self):
        record = AnnotationRecord(label_config=None)
        d = record.to_dict()
        self.assertIsNone(d["label_configuration"])
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
        self.assertEqual(record.class_labels[0].label, "Normal")

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


class TestPresetStorage(unittest.TestCase):
    def setUp(self):
        import PresetStorage as storage

        self.storage = storage
        self._original_module_dir = storage.MODULE_DIR
        self._temp_dir = tempfile.mkdtemp(prefix="annotation_panel_presets_")
        storage.MODULE_DIR = self._temp_dir

    def tearDown(self):
        self.storage.MODULE_DIR = self._original_module_dir
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_list_preset_names_empty_when_folder_missing(self):
        self.assertEqual(self.storage.list_preset_names(), [])

    def test_save_and_load_preset(self):
        payload = {
            "classification_labels": [{"name": "Normal", "color": "#4CAF50"}],
            "roi_categories": [],
            "segment_labels": [],
        }
        path = self.storage.save_preset("Brain Tumor", payload)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(self.storage.list_preset_names(), ["Brain Tumor"])
        loaded = self.storage.load_preset("Brain Tumor")
        self.assertEqual(loaded["classification_labels"][0]["name"], "Normal")
        self.assertEqual(loaded["preset_name"], "Brain Tumor")

    def test_get_presets_dir_prefers_writable_location(self):
        read_only_root = os.path.join(self._temp_dir, "readonly_module")
        writable_root = os.path.join(self._temp_dir, "writable_home", ".AnnotationPanel", "presets")
        self.storage.MODULE_DIR = read_only_root
        self.storage._RESOLVED_PRESETS_DIR = None

        original_candidates = self.storage._candidate_preset_dirs
        original_is_writable = self.storage._is_dir_writable

        def candidates():
            return [os.path.join(read_only_root, "presets"), writable_root]

        def is_writable(path):
            return os.path.normpath(path) == os.path.normpath(writable_root)

        self.storage._candidate_preset_dirs = candidates
        self.storage._is_dir_writable = is_writable
        try:
            os.makedirs(writable_root, exist_ok=True)
            chosen = self.storage.get_presets_dir()
            self.assertEqual(chosen, writable_root)
            payload = {"classification_labels": [], "roi_categories": [], "segment_labels": []}
            path = self.storage.save_preset("Writable Test", payload)
            self.assertTrue(path.startswith(writable_root))
        finally:
            self.storage._candidate_preset_dirs = original_candidates
            self.storage._is_dir_writable = original_is_writable
            self.storage._RESOLVED_PRESETS_DIR = None

    def test_preset_name_must_be_unique(self):
        payload = {"classification_labels": [], "roi_categories": [], "segment_labels": []}
        self.storage.save_preset("Chest CT", payload)
        with self.assertRaises(ValueError):
            self.storage.save_preset("chest ct", payload)

    def test_preset_name_required(self):
        with self.assertRaises(ValueError):
            self.storage.save_preset("   ", {})


class TestLabelColors(unittest.TestCase):
    def test_normalize_hex_color(self):
        from LabelColors import normalize_hex_color

        self.assertEqual(normalize_hex_color("#FF0000"), "#ff0000")
        self.assertEqual(normalize_hex_color("#8B4513"), "#8b4513")
        self.assertEqual(normalize_hex_color("8B4513"), "#8b4513")
        self.assertEqual(normalize_hex_color("#f00"), "#ff0000")

    def test_next_available_color_skips_used(self):
        from LabelColors import LABEL_COLOR_PALETTE, next_available_color

        used = [LABEL_COLOR_PALETTE[0], LABEL_COLOR_PALETTE[1], LABEL_COLOR_PALETTE[2]]
        picked = next_available_color(used)
        self.assertNotIn(picked, {c.lower() for c in used})
        self.assertEqual(picked, LABEL_COLOR_PALETTE[3].lower())

    def test_next_available_color_case_insensitive(self):
        from LabelColors import LABEL_COLOR_PALETTE, next_available_color

        used = ["#4CAF50"]
        picked = next_available_color(used)
        self.assertNotEqual(picked, "#4caf50")
        self.assertEqual(picked, LABEL_COLOR_PALETTE[1].lower())

    def test_next_available_color_when_palette_exhausted(self):
        from LabelColors import LABEL_COLOR_PALETTE, next_available_color, normalize_hex_color

        used = list(LABEL_COLOR_PALETTE)
        picked = normalize_hex_color(next_available_color(used))
        normalized_used = {normalize_hex_color(color) for color in used}
        self.assertNotIn(picked, normalized_used)

    def test_category_palettes_use_distinct_ordering(self):
        from LabelColors import get_category_palette, next_available_color

        class_palette = get_category_palette("classification")
        roi_palette = get_category_palette("roi")
        seg_palette = get_category_palette("segmentation")

        self.assertGreaterEqual(len(class_palette), 50)
        self.assertEqual(len(class_palette), len(set(class_palette)))

        class_first = next_available_color([], palette=class_palette)
        roi_first = next_available_color([], palette=roi_palette)
        seg_first = next_available_color([], palette=seg_palette)

        self.assertNotEqual(class_first, roi_first)
        self.assertNotEqual(class_first, seg_first)
        self.assertNotEqual(roi_first, seg_first)


class TestExportFolderNaming(unittest.TestCase):
    def test_prefers_scan_filename_stem(self):
        record = AnnotationRecord(
            scan=ScanMetadata(filename="Patient_123_Scan.nrrd", volume_name="Volume A"),
            study_id="STUDY-001",
        )
        self.assertEqual(derive_export_folder_name(record), "Patient_123_Scan")

    def test_falls_back_to_volume_name(self):
        record = AnnotationRecord(
            scan=ScanMetadata(volume_name="MRHead"),
            study_id="STUDY-001",
        )
        self.assertEqual(derive_export_folder_name(record), "MRHead")

    def test_falls_back_to_study_id(self):
        record = AnnotationRecord(study_id="Scan_001", series_id="SERIES-1")
        self.assertEqual(derive_export_folder_name(record), "Scan_001")

    def test_falls_back_to_series_id(self):
        record = AnnotationRecord(series_id="SERIES-ONLY")
        self.assertEqual(derive_export_folder_name(record), "SERIES-ONLY")

    def test_generated_fallback_when_no_metadata(self):
        record = AnnotationRecord(id="abcdef12-3456-7890-abcd-ef1234567890")
        name = derive_export_folder_name(record)
        self.assertRegex(name, r"^AnnotationSession_\d{4}_\d{2}_\d{2}$")

    def test_sanitizes_invalid_characters(self):
        record = AnnotationRecord(scan=ScanMetadata(filename="bad/name?.nrrd"))
        self.assertEqual(derive_export_folder_name(record), "bad_name_")

    def test_resolve_unique_subdirectory(self):
        with tempfile.TemporaryDirectory() as parent:
            first = resolve_unique_export_subdirectory(parent, "Scan_001")
            os.makedirs(first)
            second = resolve_unique_export_subdirectory(parent, "Scan_001")
            self.assertEqual(os.path.basename(first), "Scan_001")
            self.assertEqual(os.path.basename(second), "Scan_001_2")

    def test_export_filenames(self):
        self.assertEqual(EXPORT_ANNOTATIONS_FILENAME, "annotations.json")
        self.assertEqual(EXPORT_SEGMENTATION_FILENAME, "segmentation.nii.gz")

    def test_segmentation_volume_path_for_annotation_file(self):
        path = AnnotationRecord.segmentation_volume_path_for_annotation_file(
            "/tmp/export/Scan_001/annotations.json"
        )
        self.assertEqual(path, "/tmp/export/Scan_001/segmentation.nii.gz")


class TestImportResolution(unittest.TestCase):
    def test_resolve_import_paths_from_folder(self):
        with tempfile.TemporaryDirectory() as export_dir:
            json_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
            nifti_path = os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME)
            with open(json_path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            with open(nifti_path, "wb") as handle:
                handle.write(b"\x00")

            resolution = resolve_import_paths(export_dir)
            self.assertEqual(resolution.annotations_path, json_path)
            self.assertEqual(resolution.segmentation_path, nifti_path)
            self.assertTrue(resolution.is_importable())
            self.assertEqual(resolution.warnings, [])

    def test_resolve_import_paths_from_json_file(self):
        with tempfile.TemporaryDirectory() as export_dir:
            json_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
            with open(json_path, "w", encoding="utf-8") as handle:
                handle.write("{}")

            resolution = resolve_import_paths(json_path)
            self.assertEqual(resolution.annotations_path, json_path)
            self.assertEqual(
                resolution.segmentation_path,
                os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME),
            )
            self.assertIn("segmentation.nii.gz was not found", resolution.warnings[0])

    def test_resolve_import_paths_missing_both_files(self):
        with tempfile.TemporaryDirectory() as export_dir:
            resolution = resolve_import_paths(export_dir)
            self.assertFalse(resolution.is_importable())
            self.assertTrue(resolution.errors)

    def test_resolve_import_paths_segmentation_only(self):
        with tempfile.TemporaryDirectory() as export_dir:
            nifti_path = os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME)
            with open(nifti_path, "wb") as handle:
                handle.write(b"\x00")

            resolution = resolve_import_paths(export_dir)
            self.assertTrue(resolution.has_segmentation_file)
            self.assertFalse(resolution.has_annotations_file)
            self.assertIn("annotations.json was not found", resolution.warnings[0])

    def test_build_record_from_export_folder(self):
        label_config = LabelConfig(
            class_labels=[LabelDefinition(id="c1", name="Normal", color="#ff0000")],
            roi_labels=[LabelDefinition(id="r1", name="Lesion", color="#00ff00")],
            segmentation_classes=[LabelDefinition(id="s1", name="Tumor", color="#0000ff")],
        )
        record = AnnotationRecord(
            label_config=label_config,
            class_labels=[ClassLabelAnnotation(label="Normal")],
            rois=[ROIAnnotation(roi_type="line", control_points=[{"x": 0, "y": 0, "z": 0}])],
            segmentation=SegmentationData(
                labels=[SegmentLabel(name="Tumor", color="#0000ff", segment_id="Segment_1")],
            ),
        )

        with tempfile.TemporaryDirectory() as export_dir:
            json_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
            nifti_path = os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME)
            with open(json_path, "w", encoding="utf-8") as handle:
                handle.write(record.to_export_json())
            with open(nifti_path, "wb") as handle:
                handle.write(b"\x00")

            resolution = resolve_import_paths(export_dir)
            imported, errors = build_record_from_import(resolution)
            self.assertEqual(errors, [])
            self.assertIsNotNone(imported)
            self.assertEqual(imported.class_labels[0].label, "Normal")
            self.assertEqual(len(imported.rois), 1)
            self.assertIsNotNone(imported.segmentation)
            self.assertEqual(imported.segmentation.export_filepath, nifti_path)
            self.assertEqual(imported.segmentation.export_format, "nifti")

    def test_build_record_segmentation_only_uses_fallback_config(self):
        with tempfile.TemporaryDirectory() as export_dir:
            nifti_path = os.path.join(export_dir, EXPORT_SEGMENTATION_FILENAME)
            with open(nifti_path, "wb") as handle:
                handle.write(b"\x00")

            fallback = LabelConfig(
                segmentation_classes=[LabelDefinition(id="s1", name="Tumor", color="#0000ff")],
            )
            resolution = resolve_import_paths(export_dir)
            imported, errors = build_record_from_import(
                resolution,
                fallback_label_config=fallback,
            )
            self.assertEqual(errors, [])
            self.assertIsNotNone(imported)
            self.assertEqual(imported.label_config, fallback)
            self.assertEqual(imported.segmentation.export_filepath, nifti_path)

    def test_build_record_requires_label_configuration(self):
        with tempfile.TemporaryDirectory() as export_dir:
            json_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
            with open(json_path, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "class_labels": ["Normal"],
                            "rois": [],
                        }
                    )
                )

            resolution = resolve_import_paths(json_path)
            imported, errors = build_record_from_import(resolution)
            self.assertIsNone(imported)
            self.assertTrue(errors)

    def test_reconcile_imported_record_syncs_annotation_mappings(self):
        label_config = LabelConfig(
            class_labels=[
                LabelDefinition(
                    id="8c982bf2-5457-4188-b633-50752dcb44f2",
                    name="Normal",
                    color="#4caf50",
                    description="Normal spleen size and appearance",
                ),
            ],
            roi_labels=[
                LabelDefinition(
                    id="1219711e-5aa4-4f2d-9076-8a9931389480",
                    name="Spleen",
                    color="#8b4513",
                    description="Spleen boundary region",
                ),
            ],
            segmentation_classes=[
                LabelDefinition(
                    id="f95fa81a-296e-42b8-ad57-1445465aeea1",
                    name="Spleen",
                    color="#8b4513",
                    description="Spleen parenchyma",
                ),
            ],
        )
        record = AnnotationRecord(
            label_config=label_config,
            class_labels=[
                ClassLabelAnnotation(
                    label="Stale Name",
                    category_id="8c982bf2-5457-4188-b633-50752dcb44f2",
                    category_color="#000000",
                )
            ],
            rois=[
                ROIAnnotation(
                    roi_type="line",
                    label="Old ROI Label",
                    category_id="1219711e-5aa4-4f2d-9076-8a9931389480",
                    color="#000000",
                    control_points=[{"x": 0, "y": 0, "z": 0}],
                )
            ],
            segmentation=SegmentationData(
                labels=[
                    SegmentLabel(
                        name="Old Segment",
                        color="#000000",
                        segment_id="Segment_1",
                        label_config_id="f95fa81a-296e-42b8-ad57-1445465aeea1",
                    )
                ],
            ),
        )

        reconcile_imported_record(record)

        self.assertEqual(record.class_labels[0].label, "Normal")
        self.assertEqual(record.class_labels[0].category_color, "#4caf50")
        self.assertEqual(record.rois[0].label, "Spleen")
        self.assertEqual(record.rois[0].color, "#8b4513")
        self.assertEqual(record.segmentation.labels[0].name, "Spleen")
        self.assertEqual(record.segmentation.labels[0].color, "#8b4513")
        self.assertEqual(
            record.segmentation.label_to_segment_map["f95fa81a-296e-42b8-ad57-1445465aeea1"],
            "Segment_1",
        )

    def test_build_record_reads_label_configuration_export_keys(self):
        payload = {
            "label_configuration": {
                "classification_labels": [
                    {
                        "id": "8c982bf2-5457-4188-b633-50752dcb44f2",
                        "name": "Normal",
                        "color": "#4caf50",
                        "description": "Normal spleen size and appearance",
                    }
                ],
                "roi_categories": [
                    {
                        "id": "1219711e-5aa4-4f2d-9076-8a9931389480",
                        "name": "Spleen",
                        "color": "#8b4513",
                        "description": "Spleen boundary region",
                    }
                ],
                "segment_labels": [
                    {
                        "id": "f95fa81a-296e-42b8-ad57-1445465aeea1",
                        "name": "Spleen",
                        "color": "#8b4513",
                        "description": "Spleen parenchyma",
                    }
                ],
            },
            "classification_labels": [
                {
                    "category": "Normal",
                    "category_id": "8c982bf2-5457-4188-b633-50752dcb44f2",
                    "category_color": "#4caf50",
                    "plane_slices": [],
                }
            ],
            "regions_of_interest": [
                {
                    "geometry_type_id": "line",
                    "category": "Spleen",
                    "category_id": "1219711e-5aa4-4f2d-9076-8a9931389480",
                    "color": "#8b4513",
                    "control_points_ras": [{"x": 1, "y": 2, "z": 3}],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as export_dir:
            json_path = os.path.join(export_dir, EXPORT_ANNOTATIONS_FILENAME)
            with open(json_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload))

            resolution = resolve_import_paths(json_path)
            imported, errors = build_record_from_import(resolution)
            self.assertEqual(errors, [])
            self.assertEqual(len(imported.label_config.class_labels), 1)
            self.assertEqual(len(imported.label_config.roi_labels), 1)
            self.assertEqual(len(imported.label_config.segmentation_classes), 1)
            self.assertEqual(imported.class_labels[0].label, "Normal")
            self.assertEqual(imported.rois[0].label, "Spleen")
            self.assertEqual(imported.class_labels[0].category_id, "8c982bf2-5457-4188-b633-50752dcb44f2")

    def test_derive_import_preset_name_from_scan_metadata(self):
        record = AnnotationRecord(
            scan=ScanMetadata(filename="Patient_123.nii.gz"),
            study_id="STUDY-1",
        )
        self.assertEqual(derive_import_preset_name(record), "Import-Patient_123")

    def test_segment_label_def_for_label_value_maps_export_order(self):
        seg_labels = [
            LabelDefinition(id="a", name="Spleen", color="#8b4513"),
            LabelDefinition(id="b", name="Lesion", color="#e6194b"),
            LabelDefinition(id="c", name="Infarct", color="#911eb4"),
        ]
        self.assertEqual(segment_label_def_for_label_value(1, seg_labels).name, "Spleen")
        self.assertEqual(segment_label_def_for_label_value(2, seg_labels).name, "Lesion")
        self.assertEqual(segment_label_def_for_label_value(3, seg_labels).name, "Infarct")
        self.assertIsNone(segment_label_def_for_label_value(0, seg_labels))
        self.assertIsNone(segment_label_def_for_label_value(4, seg_labels))


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
        self.assertEqual(record.class_labels[0].label, "Normal")
        self.assertIsNone(record.scan)

    def test_unknown_keys_do_not_crash(self):
        data = {
            "id": "future-test",
            "unknown_field": "anything",
            "class_labels": ["A"],
        }
        record = AnnotationRecord.from_dict(data)
        self.assertEqual(record.id, "future-test")
        self.assertEqual(record.class_labels[0].label, "A")

    def test_export_json_without_segmentation_key(self):
        export_data = {
            "id": "export-only",
            "classification_labels": [{"category": "Normal", "plane_slices": []}],
            "regions_of_interest": [],
        }
        record = AnnotationRecord.from_dict(export_data)
        self.assertIsNone(record.segmentation)
        self.assertEqual(record.class_labels[0].label, "Normal")


if __name__ == "__main__":
    unittest.main()
