from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import uuid
import json
from datetime import datetime, timezone


@dataclass
class ROIAnnotation:
    """Single ROI annotation. Placeholder -- will be fleshed out in Phase 2."""
    id: str = ""
    roi_type: str = ""          # "ellipse", "rectangle", "polygon"
    slice_index: int = 0
    coords: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    color: str = "#ff0000"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "roi_type": self.roi_type,
            "slice_index": self.slice_index,
            "coords": self.coords,
            "label": self.label,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ROIAnnotation":
        return cls(
            id=data.get("id", ""),
            roi_type=data.get("roi_type", ""),
            slice_index=data.get("slice_index", 0),
            coords=data.get("coords", {}),
            label=data.get("label", ""),
            color=data.get("color", "#ff0000"),
        )


@dataclass
class SegmentationData:
    """Segmentation mask data. Placeholder -- will be fleshed out in Phase 3."""
    format: str = "rle"
    labels: List[Dict[str, str]] = field(default_factory=list)
    slices: Dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "labels": self.labels,
            "slices": {str(k): v for k, v in self.slices.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentationData":
        slices = {int(k): v for k, v in data.get("slices", {}).items()}
        return cls(
            format=data.get("format", "rle"),
            labels=data.get("labels", []),
            slices=slices,
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
