from dataclasses import dataclass, field
from typing import List, Optional, Dict
import uuid
import json
from datetime import datetime, timezone

from RadiologyTerms import (
    DEFAULT_ROI_DRAWING_TOOL,
    normalize_drawing_tool,
    roi_geometry_type_export,
    roi_geometry_type_from_export,
    slice_view_to_plane,
)
from SliceInfo import anatomical_slice_index_from_ijk


def _resolve_slice_index(plane, data: dict) -> int:
    """Resolve anatomical slice index, including legacy exports that stored physical offset."""
    ijk = list(data.get("voxel_index_ijk", data.get("volume_slice_ijk", [])))
    slice_offset_mm = float(data.get("slice_offset_mm", 0) or 0)
    slice_index = int(data.get("slice_number", data.get("slice_index", 0)) or 0)
    if ijk and len(ijk) >= 3:
        anatomical = anatomical_slice_index_from_ijk(plane, ijk)
        if slice_offset_mm == 0 and slice_index != anatomical:
            return anatomical
        return slice_index or anatomical
    return slice_index

ANNOTATION_SCHEMA_VERSION = "1.1.0"


def _get_slicer_version():
    try:
        from SliceInfo import _get_slicer_version as _version
        return _version()
    except Exception:
        return ""


@dataclass
class LabelDefinition:
    """A single label definition used in configuration."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    color: str = "#ff0000"
    description: str = ""
    drawing_tool: str = ""

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "description": self.description,
        }
        if self.drawing_tool:
            payload["drawing_tool"] = self.drawing_tool
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "LabelDefinition":
        raw_tool = data.get("drawing_tool")
        drawing_tool = normalize_drawing_tool(raw_tool) if raw_tool else ""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            color=data.get("color", "#ff0000"),
            description=data.get("description", ""),
            drawing_tool=drawing_tool,
        )

    def resolved_drawing_tool(self) -> str:
        """Return the configured ROI drawing tool, or the default when unset."""
        return normalize_drawing_tool(self.drawing_tool) or DEFAULT_ROI_DRAWING_TOOL

    def drawing_tool_changed_from(self, other: "LabelDefinition") -> bool:
        """True when the configured ROI drawing tool differs from another definition."""
        return self.resolved_drawing_tool() != other.resolved_drawing_tool()


def roi_matches_label_definition(roi, label_def: LabelDefinition, alternate_name: str = "") -> bool:
    """True when an ROI annotation belongs to the given label definition."""
    names = {label_def.name}
    if alternate_name:
        names.add(alternate_name)
    category_id = getattr(roi, "category_id", "")
    return roi.label in names or (label_def.id and category_id == label_def.id)


@dataclass
class LabelConfig:
    """Centralized label configuration. Defined once before annotation begins."""
    class_labels: List[LabelDefinition] = field(default_factory=list)
    roi_labels: List[LabelDefinition] = field(default_factory=list)
    segmentation_classes: List[LabelDefinition] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "classification_labels": [lbl.to_dict() for lbl in self.class_labels],
            "roi_categories": [lbl.to_dict() for lbl in self.roi_labels],
            "segment_labels": [lbl.to_dict() for lbl in self.segmentation_classes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LabelConfig":
        return cls(
            class_labels=[
                LabelDefinition.from_dict(d)
                for d in data.get("classification_labels", data.get("class_labels", []))
            ],
            roi_labels=[
                LabelDefinition.from_dict(d)
                for d in data.get("roi_categories", data.get("roi_labels", []))
            ],
            segmentation_classes=[
                LabelDefinition.from_dict(d)
                for d in data.get("segment_labels", data.get("segmentation_classes", []))
            ],
        )


def _plane_display_name(plane: str) -> str:
    """Return a human-readable plane label such as 'Axial Plane'."""
    normalized = slice_view_to_plane(plane)
    if not normalized:
        return plane
    if normalized.endswith(" Plane"):
        return normalized
    return f"{normalized} Plane"


@dataclass
class PlaneSliceContext:
    """Slice position and geometry for one anatomical plane."""
    slice_view: str = ""
    slice_index: int = 0
    slice_offset_mm: float = 0.0
    slice_position_ras: list = field(default_factory=list)
    volume_slice_ijk: list = field(default_factory=list)
    slicer_slice_view: str = ""
    slice_to_ras_matrix: list = field(default_factory=list)
    field_of_view: list = field(default_factory=list)
    slice_spacing: float = 0.0
    slice_normal_ras: list = field(default_factory=list)
    volume_node_id: str = ""
    volume_name: str = ""

    @classmethod
    def from_slice_info(cls, slice_info: dict) -> "PlaneSliceContext":
        plane = slice_info.get("plane", slice_info.get("slice_view", ""))
        return cls(
            slice_view=_plane_display_name(plane),
            slice_index=_resolve_slice_index(plane, slice_info),
            slice_offset_mm=float(slice_info.get("slice_offset_mm", 0) or 0),
            slice_position_ras=list(slice_info.get("position_ras", slice_info.get("slice_position_ras", []))),
            volume_slice_ijk=list(slice_info.get("voxel_index_ijk", slice_info.get("volume_slice_ijk", []))),
            slicer_slice_view=slice_info.get("slicer_slice_view", ""),
            slice_to_ras_matrix=list(slice_info.get("slice_to_ras_matrix", [])),
            field_of_view=list(slice_info.get("field_of_view", [])),
            slice_spacing=float(slice_info.get("slice_spacing", 0.0) or 0.0),
            slice_normal_ras=list(slice_info.get("slice_normal_ras", [])),
            volume_node_id=slice_info.get("volume_node_id", ""),
            volume_name=slice_info.get("volume_name", ""),
        )

    def to_export_dict(self) -> dict:
        """Compact slice context for JSON export (no duplicate legacy keys)."""
        plane = slice_view_to_plane(self.slice_view)
        payload = {
            "plane": plane,
            "slice_number": self.slice_index,
            "slicer_slice_view": self.slicer_slice_view,
            "position_ras": list(self.slice_position_ras),
            "voxel_index_ijk": list(self.volume_slice_ijk),
        }
        if self.slice_spacing:
            payload["slice_spacing"] = self.slice_spacing
        if self.slice_normal_ras:
            payload["slice_normal_ras"] = list(self.slice_normal_ras)
        return payload

    def to_dict(self) -> dict:
        plane = slice_view_to_plane(self.slice_view)
        payload = {
            "plane": plane,
            "slice_view": self.slice_view or _plane_display_name(plane),
            "slice_number": self.slice_index,
            "slice_index": self.slice_index,
            "slice_offset_mm": self.slice_offset_mm,
            "position_ras": list(self.slice_position_ras),
            "voxel_index_ijk": list(self.volume_slice_ijk),
            "slicer_slice_view": self.slicer_slice_view,
            "slice_to_ras_matrix": list(self.slice_to_ras_matrix),
            "field_of_view": list(self.field_of_view),
            "slice_spacing": self.slice_spacing,
            "slice_normal_ras": list(self.slice_normal_ras),
            "volume_node_id": self.volume_node_id,
            "volume_name": self.volume_name,
        }
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "PlaneSliceContext":
        plane = data.get("plane", data.get("slice_view", ""))
        return cls(
            slice_view=data.get("slice_view", _plane_display_name(plane)),
            slice_index=_resolve_slice_index(plane, data),
            slice_offset_mm=float(data.get("slice_offset_mm", 0) or 0),
            slice_position_ras=data.get("position_ras", data.get("slice_position_ras", [])),
            volume_slice_ijk=data.get("voxel_index_ijk", data.get("volume_slice_ijk", [])),
            slicer_slice_view=data.get("slicer_slice_view", ""),
            slice_to_ras_matrix=data.get("slice_to_ras_matrix", []),
            field_of_view=data.get("field_of_view", []),
            slice_spacing=float(data.get("slice_spacing", 0.0) or 0.0),
            slice_normal_ras=data.get("slice_normal_ras", []),
            volume_node_id=data.get("volume_node_id", ""),
            volume_name=data.get("volume_name", ""),
        )


@dataclass
class ClassLabelAnnotation:
    """A classification label applied with slice context from all three planes."""
    label: str = ""
    plane_slices: List[PlaneSliceContext] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category_id: str = ""
    category_color: str = ""
    category_description: str = ""
    # Legacy single-plane fields kept for backward compatibility.
    slice_view: str = ""
    slice_index: int = 0
    slice_offset_mm: float = 0.0
    slice_position_ras: list = field(default_factory=list)
    volume_slice_ijk: list = field(default_factory=list)
    slicer_slice_view: str = ""
    slice_to_ras_matrix: list = field(default_factory=list)
    field_of_view: list = field(default_factory=list)
    slice_spacing: float = 0.0
    slice_normal_ras: list = field(default_factory=list)
    volume_node_id: str = ""
    volume_name: str = ""

    def __post_init__(self):
        if not self.plane_slices and (self.slice_view or self.slice_index):
            self.plane_slices = [PlaneSliceContext(
                slice_view=_plane_display_name(self.slice_view),
                slice_index=self.slice_index,
                slice_offset_mm=self.slice_offset_mm,
                slice_position_ras=list(self.slice_position_ras),
                volume_slice_ijk=list(self.volume_slice_ijk),
                slicer_slice_view=self.slicer_slice_view,
                slice_to_ras_matrix=list(self.slice_to_ras_matrix),
                field_of_view=list(self.field_of_view),
                slice_spacing=self.slice_spacing,
                slice_normal_ras=list(self.slice_normal_ras),
                volume_node_id=self.volume_node_id,
                volume_name=self.volume_name,
            )]

    def _sync_legacy_fields(self):
        """Populate legacy single-plane fields from the primary axial slice."""
        primary = self.get_plane_slice("Axial") or (self.plane_slices[0] if self.plane_slices else None)
        if not primary:
            return
        self.slice_view = slice_view_to_plane(primary.slice_view) or primary.slice_view
        self.slice_index = primary.slice_index
        self.slice_offset_mm = primary.slice_offset_mm
        self.slice_position_ras = list(primary.slice_position_ras)
        self.volume_slice_ijk = list(primary.volume_slice_ijk)
        self.slicer_slice_view = primary.slicer_slice_view
        self.slice_to_ras_matrix = list(primary.slice_to_ras_matrix)
        self.field_of_view = list(primary.field_of_view)
        self.slice_spacing = primary.slice_spacing
        self.slice_normal_ras = list(primary.slice_normal_ras)
        self.volume_node_id = primary.volume_node_id
        self.volume_name = primary.volume_name

    def get_plane_slice(self, plane_name: str) -> Optional[PlaneSliceContext]:
        normalized = slice_view_to_plane(plane_name)
        for plane_slice in self.plane_slices:
            if slice_view_to_plane(plane_slice.slice_view) == normalized:
                return plane_slice
        return None

    @classmethod
    def from_slice_context(cls, label_def, slice_info: dict) -> "ClassLabelAnnotation":
        """Build a rich annotation from a label definition and one captured slice context."""
        annotation = cls(
            label=label_def.name,
            category_id=label_def.id,
            category_color=label_def.color,
            category_description=label_def.description,
            plane_slices=[PlaneSliceContext.from_slice_info(slice_info)],
        )
        annotation._sync_legacy_fields()
        return annotation

    @classmethod
    def from_all_planes_context(cls, label_def, plane_slice_infos: list) -> "ClassLabelAnnotation":
        """Build an annotation with slice context from Axial, Coronal, and Sagittal views."""
        annotation = cls(
            label=label_def.name,
            category_id=label_def.id,
            category_color=label_def.color,
            category_description=label_def.description,
            plane_slices=[PlaneSliceContext.from_slice_info(info) for info in plane_slice_infos],
        )
        annotation._sync_legacy_fields()
        return annotation

    def to_dict(self) -> dict:
        return {
            "category": self.label,
            "category_id": self.category_id,
            "category_color": self.category_color,
            "category_description": self.category_description,
            "plane_slices": [plane.to_dict() for plane in self.plane_slices],
            "created_at": self.created_at,
            # Legacy alias for category name only; slice context lives in plane_slices.
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data) -> "ClassLabelAnnotation":
        if isinstance(data, cls):
            return data
        if isinstance(data, str):
            return cls(label=data)

        plane_slices_data = data.get("plane_slices", [])
        if plane_slices_data:
            plane_slices = [PlaneSliceContext.from_dict(item) for item in plane_slices_data]
        else:
            plane = data.get("plane", data.get("slice_view", ""))
            if plane or data.get("slice_number") or data.get("slice_index"):
                plane_slices = [PlaneSliceContext.from_dict(data)]
            else:
                plane_slices = []

        annotation = cls(
            label=data.get("category", data.get("label", "")),
            category_id=data.get("category_id", ""),
            category_color=data.get("category_color", ""),
            category_description=data.get("category_description", ""),
            plane_slices=plane_slices,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
        annotation._sync_legacy_fields()
        return annotation


ROI_BOX_2D_TYPES = frozenset({"rectangle_2d"})
ROI_BOX_3D_TYPES = frozenset({"rectangle_3d", "rectangle"})
ROI_CURVE_TYPES = frozenset({"polygon", "freehand_curve", "ellipse"})
ROI_LINE_TYPES = frozenset({"line"})


def _valid_ras_points(points, minimum=1):
    if not isinstance(points, list) or len(points) < minimum:
        return False
    for pt in points:
        if not isinstance(pt, dict):
            return False
        if not all(axis in pt for axis in ("x", "y", "z")):
            return False
    return True


def _valid_ras_xyz(coords):
    return isinstance(coords, list) and len(coords) == 3


def _non_zero_extent(values, minimum_count=2):
    if not isinstance(values, list) or len(values) < minimum_count:
        return False
    significant = [float(v or 0.0) for v in values[:minimum_count]]
    return sum(1 for v in significant if abs(v) > 1e-6) >= minimum_count


@dataclass
class ROIAnnotation:
    """A single region of interest on an image series (RAS coordinates)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    roi_type: str = ""
    label: str = ""
    color: str = "#ff0000"
    slice_view: str = ""
    slice_index: int = 0
    slice_offset_mm: float = 0.0
    control_points: list = field(default_factory=list)
    radii: list = field(default_factory=list)
    orientation: list = field(default_factory=list)
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mrml_node_id: str = ""
    mrml_node_name: str = ""
    category_id: str = ""
    category_description: str = ""
    slicer_slice_view: str = ""
    slice_position_ras: list = field(default_factory=list)
    volume_slice_ijk: list = field(default_factory=list)
    slice_to_ras_matrix: list = field(default_factory=list)
    field_of_view: list = field(default_factory=list)
    slice_spacing: float = 0.0
    slice_normal_ras: list = field(default_factory=list)
    volume_node_id: str = ""
    volume_name: str = ""
    number_of_control_points: int = 0
    bounding_box_dimensions: list = field(default_factory=list)
    center_ras: list = field(default_factory=list)
    center_voxel_ijk: list = field(default_factory=list)
    transform_handles_enabled: bool = False

    def normalize_geometry_fields(self):
        """Keep derived geometry fields consistent before export."""
        self.number_of_control_points = len(self.control_points or [])
        if self.radii and not self.bounding_box_dimensions:
            self.bounding_box_dimensions = [float(r) * 2.0 for r in self.radii[:3]]
        elif self.bounding_box_dimensions and not self.radii:
            self.radii = [float(d) / 2.0 for d in self.bounding_box_dimensions[:3]]

    def missing_reconstruction_fields(self) -> list:
        """Return export keys still required to rebuild this ROI on import."""
        roi_type = self.roi_type or ""
        missing = []
        if not roi_type:
            missing.append("geometry_type_id")

        if roi_type in ROI_LINE_TYPES:
            if not _valid_ras_points(self.control_points, 2):
                missing.append("control_points_ras")
        elif roi_type in ROI_CURVE_TYPES:
            minimum = 3 if roi_type == "polygon" else 2
            if not _valid_ras_points(self.control_points, minimum):
                missing.append("control_points_ras")
        elif roi_type in ROI_BOX_2D_TYPES:
            has_corners = _valid_ras_points(self.control_points, 4)
            has_centered_box = _valid_ras_xyz(self.center_ras) and (
                _non_zero_extent(self.bounding_box_dimensions, 2)
                or _non_zero_extent(self.radii, 2)
            )
            if not has_corners and not has_centered_box:
                missing.append("control_points_ras")
                missing.append("center_ras with bounding_box_dimensions or radii")
        elif roi_type in ROI_BOX_3D_TYPES:
            has_center = _valid_ras_xyz(self.center_ras) or _valid_ras_points(
                self.control_points, 1
            )
            has_size = _non_zero_extent(self.radii, 2) or _non_zero_extent(
                self.bounding_box_dimensions, 2
            )
            if not has_center:
                missing.append("center_ras")
            if not has_size:
                missing.append("radii")
                missing.append("bounding_box_dimensions")
        return missing

    def has_reconstruction_geometry(self) -> bool:
        return not self.missing_reconstruction_fields()

    def to_dict(self) -> dict:
        self.normalize_geometry_fields()
        return {
            "id": self.id,
            "geometry_type": roi_geometry_type_export(self.roi_type),
            "geometry_type_id": self.roi_type,
            "category": self.label,
            "category_id": self.category_id,
            "category_description": self.category_description,
            "color": self.color,
            "plane": slice_view_to_plane(self.slice_view),
            "slicer_slice_view": self.slicer_slice_view,
            "slice_index": self.slice_index,
            "slice_offset_mm": self.slice_offset_mm,
            "position_ras": list(self.slice_position_ras),
            "slice_to_ras_matrix": list(self.slice_to_ras_matrix),
            "field_of_view": list(self.field_of_view),
            "slice_spacing": self.slice_spacing,
            "slice_normal_ras": list(self.slice_normal_ras),
            "volume_node_id": self.volume_node_id,
            "volume_name": self.volume_name,
            "control_points_ras": list(self.control_points),
            "number_of_control_points": self.number_of_control_points,
            "radii": list(self.radii),
            "bounding_box_dimensions": list(self.bounding_box_dimensions),
            "orientation": list(self.orientation),
            "center_ras": list(self.center_ras),
            "center_voxel_ijk": list(self.center_voxel_ijk),
            "transform_handles_enabled": bool(self.transform_handles_enabled),
            "description": self.description,
            "mrml_node_id": self.mrml_node_id,
            "mrml_node_name": self.mrml_node_name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ROIAnnotation":
        geometry = data.get("geometry_type_id", data.get("geometry_type", data.get("roi_type", "")))
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            roi_type=roi_geometry_type_from_export(geometry),
            label=data.get("category", data.get("label", "")),
            category_id=data.get("category_id", ""),
            category_description=data.get("category_description", ""),
            color=data.get("color", "#ff0000"),
            slice_view=data.get("plane", data.get("slice_view", "")),
            slice_index=_resolve_slice_index(
                data.get("plane", data.get("slice_view", "")), data
            ),
            slice_offset_mm=float(data.get("slice_offset_mm", 0) or 0),
            slicer_slice_view=data.get("slicer_slice_view", ""),
            slice_position_ras=data.get("position_ras", data.get("slice_position_ras", [])),
            volume_slice_ijk=data.get("voxel_index_ijk", data.get("volume_slice_ijk", [])),
            slice_to_ras_matrix=data.get("slice_to_ras_matrix", []),
            field_of_view=data.get("field_of_view", []),
            slice_spacing=float(data.get("slice_spacing", 0.0) or 0.0),
            slice_normal_ras=data.get("slice_normal_ras", []),
            volume_node_id=data.get("volume_node_id", ""),
            volume_name=data.get("volume_name", ""),
            control_points=data.get("control_points_ras", data.get("control_points", [])),
            number_of_control_points=int(data.get("number_of_control_points", 0) or 0),
            radii=data.get("radii", []),
            bounding_box_dimensions=data.get("bounding_box_dimensions", []),
            orientation=data.get("orientation", []),
            center_ras=data.get("center_ras", []),
            center_voxel_ijk=data.get("center_voxel_ijk", []),
            transform_handles_enabled=bool(data.get("transform_handles_enabled", False)),
            description=data.get("description", ""),
            mrml_node_id=data.get("mrml_node_id", ""),
            mrml_node_name=data.get("mrml_node_name", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class SegmentSpatialExtent:
    """Where a segment occupies space in the source volume."""
    bounds_ras: list = field(default_factory=list)
    extent_ijk: list = field(default_factory=list)
    center_ras: list = field(default_factory=list)
    center_voxel_ijk: list = field(default_factory=list)
    volume_mm3: float = 0.0
    surface_area_mm2: float = 0.0
    oriented_bounding_box_origin_ras: list = field(default_factory=list)
    oriented_bounding_box_diameter_mm: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bounds_ras": list(self.bounds_ras),
            "extent_ijk": list(self.extent_ijk),
            "center_ras": list(self.center_ras),
            "center_voxel_ijk": list(self.center_voxel_ijk),
            "volume_mm3": self.volume_mm3,
            "surface_area_mm2": self.surface_area_mm2,
            "oriented_bounding_box_origin_ras": list(self.oriented_bounding_box_origin_ras),
            "oriented_bounding_box_diameter_mm": list(self.oriented_bounding_box_diameter_mm),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentSpatialExtent":
        if not data:
            return cls()
        return cls(
            bounds_ras=data.get("bounds_ras", []),
            extent_ijk=data.get("extent_ijk", []),
            center_ras=data.get("center_ras", []),
            center_voxel_ijk=data.get("center_voxel_ijk", []),
            volume_mm3=float(data.get("volume_mm3", 0.0) or 0.0),
            surface_area_mm2=float(data.get("surface_area_mm2", 0.0) or 0.0),
            oriented_bounding_box_origin_ras=data.get("oriented_bounding_box_origin_ras", []),
            oriented_bounding_box_diameter_mm=data.get("oriented_bounding_box_diameter_mm", []),
        )


# Effects that operate on the whole segment rather than a single slice plane.
VOLUME_SCOPED_EFFECTS = frozenset({
    "Margin",
    "Hollow",
    "Smoothing",
    "Islands",
    "Logical operators",
    "Fill between slices",
    "Grow from seeds",
    "Mask volume",
})


def should_record_segment_modification(
    effect_name,
    segment_id,
    selected_segment_id,
    count,
    previous_count,
    mtime,
    previous_mtime,
    volume_scoped_effects=VOLUME_SCOPED_EFFECTS,
):
    """Return True when a segment edit should produce a modification event."""
    count_changed = count != previous_count
    mtime_changed = mtime != previous_mtime
    if not count_changed and not mtime_changed:
        return False

    if effect_name not in volume_scoped_effects:
        if selected_segment_id and segment_id != selected_segment_id:
            return False
        return count_changed

    if count_changed:
        return True
    return mtime_changed and count > 0


@dataclass
class SegmentModificationEvent:
    """A recorded segment-editor action (paint, threshold, erase, etc.)."""
    effect_name: str = ""
    segment_id: str = ""
    segment_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    slice_context: dict = field(default_factory=dict)
    effect_parameters: dict = field(default_factory=dict)

    def normalized_slice_context(self) -> dict:
        """Return compact slice context for export."""
        if not self.slice_context:
            return {}
        return PlaneSliceContext.from_slice_info(self.slice_context).to_export_dict()

    def to_dict(self) -> dict:
        return {
            "effect_name": self.effect_name,
            "segment_id": self.segment_id,
            "segment_name": self.segment_name,
            "timestamp": self.timestamp,
            "slice_context": self.normalized_slice_context(),
            "effect_parameters": dict(self.effect_parameters),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentModificationEvent":
        return cls(
            effect_name=data.get("effect_name", ""),
            segment_id=data.get("segment_id", ""),
            segment_name=data.get("segment_name", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            slice_context=data.get("slice_context", {}),
            effect_parameters=data.get("effect_parameters", {}),
        )


@dataclass
class SegmentLabel:
    """A single segment within a segmentation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    color: str = "#ff0000"
    segment_id: str = ""
    description: str = ""
    label_config_id: str = ""
    voxel_count: int = 0
    spatial_extent: Optional[SegmentSpatialExtent] = None
    modification_events: List[SegmentModificationEvent] = field(default_factory=list)
    last_effect_name: str = ""
    last_effect_parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "segment_id": self.segment_id,
            "description": self.description,
            "label_config_id": self.label_config_id,
            "voxel_count": self.voxel_count,
            "last_effect_name": self.last_effect_name,
            "last_effect_parameters": dict(self.last_effect_parameters),
            "modification_events": [event.to_dict() for event in self.modification_events],
        }
        if self.spatial_extent:
            payload["spatial_extent"] = self.spatial_extent.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentLabel":
        spatial = data.get("spatial_extent")
        events = data.get("modification_events", [])
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            color=data.get("color", "#ff0000"),
            segment_id=data.get("segment_id", ""),
            description=data.get("description", ""),
            label_config_id=data.get("label_config_id", ""),
            voxel_count=int(data.get("voxel_count", 0) or 0),
            spatial_extent=SegmentSpatialExtent.from_dict(spatial) if spatial else None,
            modification_events=[SegmentModificationEvent.from_dict(e) for e in events],
            last_effect_name=data.get("last_effect_name", ""),
            last_effect_parameters=data.get("last_effect_parameters", {}),
        )


@dataclass
class SegmentationData:
    """Segmentation metadata. Voxel data lives in the Slicer scene or export file."""
    labels: List[SegmentLabel] = field(default_factory=list)
    export_format: str = "nrrd"
    export_filepath: str = ""
    source_volume_node_id: str = ""
    source_volume_name: str = ""
    segmentation_node_id: str = ""
    total_voxel_count: int = 0
    per_label_voxel_counts: Dict[str, int] = field(default_factory=dict)
    label_to_segment_map: Dict[str, str] = field(default_factory=dict)
    modification_events: List[SegmentModificationEvent] = field(default_factory=list)
    editor_state_at_export: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "segments": [lbl.to_dict() for lbl in self.labels],
            "export_format": self.export_format,
            "export_filepath": self.export_filepath,
            "source_volume_node_id": self.source_volume_node_id,
            "source_volume_name": self.source_volume_name,
            "segmentation_node_id": self.segmentation_node_id,
            "total_segmented_voxels": self.total_voxel_count,
            "segment_voxel_counts": dict(self.per_label_voxel_counts),
            "label_to_segment_map": dict(self.label_to_segment_map),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SegmentationData":
        segment_data = data.get("segments", data.get("labels", []))
        labels = [SegmentLabel.from_dict(lbl) for lbl in segment_data]
        events = data.get("modification_events", [])
        if not events:
            for lbl_data in segment_data:
                events.extend(lbl_data.get("modification_events", []))
        return cls(
            labels=labels,
            export_format=data.get("export_format", "nrrd"),
            export_filepath=data.get("export_filepath", ""),
            source_volume_node_id=data.get("source_volume_node_id", ""),
            source_volume_name=data.get("source_volume_name", ""),
            segmentation_node_id=data.get("segmentation_node_id", ""),
            total_voxel_count=data.get("total_segmented_voxels", data.get("total_voxel_count", 0)),
            per_label_voxel_counts=data.get("segment_voxel_counts", data.get("per_label_voxel_counts", {})),
            label_to_segment_map=data.get("label_to_segment_map", {}),
            modification_events=[SegmentModificationEvent.from_dict(e) for e in events],
            editor_state_at_export=data.get("editor_state_at_export", {}),
        )


@dataclass
class ScanMetadata:
    """Metadata about the loaded image series being annotated."""
    filename: str = ""
    filepath: str = ""
    file_format: str = ""
    dimensions: List[int] = field(default_factory=list)
    spacing: List[float] = field(default_factory=list)
    origin: List[float] = field(default_factory=list)
    modality: str = ""
    patient_id: str = ""
    study_description: str = ""
    volume_node_id: str = ""
    volume_name: str = ""
    ijk_to_ras_matrix: List[float] = field(default_factory=list)
    series_description: str = ""
    study_instance_uid: str = ""
    series_instance_uid: str = ""
    series_number: str = ""
    study_date: str = ""
    instance_uids: List[str] = field(default_factory=list)
    window_center: Optional[float] = None
    window_width: Optional[float] = None

    @classmethod
    def from_volume_capture(cls, captured: dict, filepath="", file_format="") -> "ScanMetadata":
        return cls(
            filename=captured.get("volume_name", "") or (filepath.split("/")[-1] if filepath else ""),
            filepath=filepath,
            file_format=file_format or captured.get("file_format", ""),
            dimensions=list(captured.get("dimensions", [])),
            spacing=list(captured.get("pixel_spacing", [])),
            origin=list(captured.get("image_origin", [])),
            modality=captured.get("modality", ""),
            patient_id=captured.get("patient_id", ""),
            study_description=captured.get("study_description", ""),
            volume_node_id=captured.get("volume_node_id", ""),
            volume_name=captured.get("volume_name", ""),
            ijk_to_ras_matrix=list(captured.get("ijk_to_ras_matrix", [])),
            series_description=captured.get("series_description", ""),
            study_instance_uid=captured.get("study_instance_uid", ""),
            series_instance_uid=captured.get("series_instance_uid", ""),
            series_number=captured.get("series_number", ""),
            study_date=captured.get("study_date", ""),
            instance_uids=list(captured.get("instance_uids", [])),
            window_center=captured.get("window_center"),
            window_width=captured.get("window_width"),
        )

    def to_dict(self) -> dict:
        payload = {
            "filename": self.filename,
            "filepath": self.filepath,
            "file_format": self.file_format,
            "dimensions": list(self.dimensions),
            "pixel_spacing": list(self.spacing),
            "image_origin": list(self.origin),
            "modality": self.modality,
            "patient_id": self.patient_id,
            "study_description": self.study_description,
            "series_description": self.series_description,
            "study_instance_uid": self.study_instance_uid,
            "series_instance_uid": self.series_instance_uid,
            "series_number": self.series_number,
            "study_date": self.study_date,
            "instance_uids": list(self.instance_uids),
            "volume_node_id": self.volume_node_id,
            "volume_name": self.volume_name,
            "ijk_to_ras_matrix": list(self.ijk_to_ras_matrix),
            "window_center": self.window_center,
            "window_width": self.window_width,
            # Legacy aliases
            "spacing": list(self.spacing),
            "origin": list(self.origin),
        }
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "ScanMetadata":
        return cls(
            filename=data.get("filename", ""),
            filepath=data.get("filepath", ""),
            file_format=data.get("file_format", ""),
            dimensions=data.get("dimensions", []),
            spacing=data.get("pixel_spacing", data.get("spacing", [])),
            origin=data.get("image_origin", data.get("origin", [])),
            modality=data.get("modality", ""),
            patient_id=data.get("patient_id", ""),
            study_description=data.get("study_description", ""),
            volume_node_id=data.get("volume_node_id", ""),
            volume_name=data.get("volume_name", ""),
            ijk_to_ras_matrix=data.get("ijk_to_ras_matrix", []),
            series_description=data.get("series_description", ""),
            study_instance_uid=data.get("study_instance_uid", ""),
            series_instance_uid=data.get("series_instance_uid", ""),
            series_number=data.get("series_number", ""),
            study_date=data.get("study_date", ""),
            instance_uids=data.get("instance_uids", []),
            window_center=data.get("window_center"),
            window_width=data.get("window_width"),
        )


@dataclass
class AnnotationRecord:
    """Top-level annotation record. One per study/series being annotated."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    study_id: str = ""
    series_id: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    label_config: Optional[LabelConfig] = None
    scan: Optional[ScanMetadata] = None

    class_labels: List[ClassLabelAnnotation] = field(default_factory=list)
    rois: List[ROIAnnotation] = field(default_factory=list)
    segmentation: Optional[SegmentationData] = None

    def __post_init__(self):
        self.class_labels = [
            item if isinstance(item, ClassLabelAnnotation) else ClassLabelAnnotation.from_dict(item)
            for item in self.class_labels
        ]

    def to_dict(self) -> dict:
        return {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "slicer_version": _get_slicer_version(),
            "id": self.id,
            "study_id": self.study_id,
            "series_id": self.series_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "label_configuration": self.label_config.to_dict() if self.label_config else None,
            "series_metadata": self.scan.to_dict() if self.scan else None,
            "classification_labels": [lbl.to_dict() for lbl in self.class_labels],
            "regions_of_interest": [roi.to_dict() for roi in self.rois],
            "segmentation": self.segmentation.to_dict() if self.segmentation else None,
            # Legacy top-level aliases
            "label_config": self.label_config.to_dict() if self.label_config else None,
            "scan": self.scan.to_dict() if self.scan else None,
            "class_labels": [lbl.to_dict() for lbl in self.class_labels],
            "rois": [roi.to_dict() for roi in self.rois],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnnotationRecord":
        rois = [
            ROIAnnotation.from_dict(r)
            for r in data.get("regions_of_interest", data.get("rois", []))
        ]
        seg_data = data.get("segmentation")
        segmentation = SegmentationData.from_dict(seg_data) if seg_data else None
        scan_data = data.get("series_metadata", data.get("scan"))
        scan = ScanMetadata.from_dict(scan_data) if scan_data else None
        lc_data = data.get("label_configuration", data.get("label_config"))
        label_config = LabelConfig.from_dict(lc_data) if lc_data else None
        class_labels = data.get("classification_labels", data.get("class_labels", []))

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            study_id=data.get("study_id", ""),
            series_id=data.get("series_id", ""),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            label_config=label_config,
            scan=scan,
            class_labels=class_labels,
            rois=rois,
            segmentation=segmentation,
        )

    def to_json(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "AnnotationRecord":
        return cls.from_dict(json.loads(json_str))
