from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import uuid
import json
from datetime import datetime, timezone


@dataclass
class ROIAnnotation:
    """
    A single ROI annotation drawn on the scan.
    Coordinates are stored in RAS (Right-Anterior-Superior) world coordinates,
    which is Slicer's native coordinate system for markups.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    roi_type: str = ""
    # roi_type values: "ellipse", "rectangle", "polygon", "freehand_curve", "line"

    label: str = ""
    color: str = "#ff0000"

    # Slice context
    slice_view: str = ""        # "Red", "Green", "Yellow"
    slice_index: int = 0

    # Geometry: ordered list of control points (3D RAS)
    # Each point is {"x": float, "y": float, "z": float}
    control_points: list = field(default_factory=list)

    # Ellipse/rectangle-specific
    radii: list = field(default_factory=list)        # [rx, ry] for ellipse, [w, h] for rect
    orientation: list = field(default_factory=list)   # 3x3 rotation matrix as flat 9-element list

    # Metadata
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Runtime-only reference to Slicer MRML node (excluded from serialization)
    mrml_node_id: str = ""

    def to_dict(self) -> dict:
        """Serialize to a plain dict. Excludes mrml_node_id (runtime only)."""
        return {
            "id": self.id,
            "roi_type": self.roi_type,
            "label": self.label,
            "color": self.color,
            "slice_view": self.slice_view,
            "slice_index": self.slice_index,
            "control_points": list(self.control_points),
            "radii": list(self.radii),
            "orientation": list(self.orientation),
            "description": self.description,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ROIAnnotation":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            roi_type=data.get("roi_type", ""),
            label=data.get("label", ""),
            color=data.get("color", "#ff0000"),
            slice_view=data.get("slice_view", ""),
            slice_index=data.get("slice_index", 0),
            control_points=data.get("control_points", []),
            radii=data.get("radii", []),
            orientation=data.get("orientation", []),
            description=data.get("description", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            mrml_node_id="",
        )


@dataclass
class SegmentLabel:
    """A single segment (label class) within the segmentation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    color: str = "#ff0000"
    segment_id: str = ""        # Slicer's internal segment ID (e.g., "Segment_1")
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "segment_id": self.segment_id,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentLabel":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            color=data.get("color", "#ff0000"),
            segment_id=data.get("segment_id", ""),
            description=data.get("description", ""),
        )


@dataclass
class SegmentationData:
    """
    Segmentation mask data for the annotation.
    The actual voxel data lives in the Slicer scene as a vtkMRMLSegmentationNode.
    This dataclass stores metadata and export references.
    """
    labels: List[SegmentLabel] = field(default_factory=list)

    export_format: str = "nrrd"         # "nrrd" or "nifti"
    export_filepath: str = ""

    source_volume_node_id: str = ""

    # Runtime reference (not serialized)
    segmentation_node_id: str = ""

    # Statistics
    total_voxel_count: int = 0
    per_label_voxel_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict. Excludes segmentation_node_id (runtime only)."""
        return {
            "labels": [lbl.to_dict() for lbl in self.labels],
            "export_format": self.export_format,
            "export_filepath": self.export_filepath,
            "source_volume_node_id": self.source_volume_node_id,
            "total_voxel_count": self.total_voxel_count,
            "per_label_voxel_counts": dict(self.per_label_voxel_counts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentationData":
        labels = [SegmentLabel.from_dict(lbl) for lbl in data.get("labels", [])]
        return cls(
            labels=labels,
            export_format=data.get("export_format", "nrrd"),
            export_filepath=data.get("export_filepath", ""),
            source_volume_node_id=data.get("source_volume_node_id", ""),
            segmentation_node_id="",
            total_voxel_count=data.get("total_voxel_count", 0),
            per_label_voxel_counts=data.get("per_label_voxel_counts", {}),
        )


@dataclass
class AnnotationRecord:
    """
    Top-level annotation record. One per study/series being annotated.
    All four annotation sections are optional -- annotators use whichever modes apply.
    """
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    study_id: str = ""
    series_id: str = ""

    # Workflow
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "draft"  # draft | submitted | approved | rejected
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_comments: Optional[str] = None

    # Mode A -- Class Labels
    class_labels: List[str] = field(default_factory=list)

    # Mode B -- ROIs
    rois: List[ROIAnnotation] = field(default_factory=list)

    # Mode C -- Segmentation
    segmentation: Optional[SegmentationData] = None

    # Mode D -- Freeform JSON
    freeform_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe)."""
        return {
            "id": self.id,
            "study_id": self.study_id,
            "series_id": self.series_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_comments": self.review_comments,
            "class_labels": list(self.class_labels),
            "rois": [roi.to_dict() for roi in self.rois],
            "segmentation": self.segmentation.to_dict() if self.segmentation else None,
            "freeform_data": self.freeform_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnnotationRecord":
        """Deserialize from a plain dict."""
        rois = [ROIAnnotation.from_dict(r) for r in data.get("rois", [])]
        seg_data = data.get("segmentation")
        segmentation = SegmentationData.from_dict(seg_data) if seg_data else None

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            study_id=data.get("study_id", ""),
            series_id=data.get("series_id", ""),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "draft"),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=data.get("reviewed_at"),
            review_comments=data.get("review_comments"),
            class_labels=data.get("class_labels", []),
            rois=rois,
            segmentation=segmentation,
            freeform_data=data.get("freeform_data", {}),
        )

    def to_json(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "AnnotationRecord":
        return cls.from_dict(json.loads(json_str))
