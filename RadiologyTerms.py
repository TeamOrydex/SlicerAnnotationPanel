"""
Radiology terminology helpers for UI labels and export serialization.
"""

# Slicer slice view colors → standard anatomical planes (default four-up layout).
SLICE_VIEW_TO_PLANE = {
    "Red": "Axial",
    "Green": "Coronal",
    "Yellow": "Sagittal",
}

PLANE_ALIASES = {
    "Axial Plane": "Axial",
    "Coronal Plane": "Coronal",
    "Sagittal Plane": "Sagittal",
}

ROI_GEOMETRY_TYPES = {
    "rectangle_3d": "Bounding Box",
    "rectangle": "Bounding Box",
    "polygon": "Polygon Contour",
    "freehand_curve": "Freehand Contour",
    "line": "Linear Measurement",
    "ellipse": "Ellipse",
    "rectangle_2d": "Planar Rectangle",
}


def slice_view_to_plane(slice_view):
    """Convert a Slicer slice view name to a standard anatomical plane label."""
    if not slice_view:
        return ""
    if slice_view in PLANE_ALIASES:
        return PLANE_ALIASES[slice_view]
    return SLICE_VIEW_TO_PLANE.get(slice_view, slice_view)


def plane_to_slice_view(plane):
    """Convert an anatomical plane label back to a Slicer slice view name."""
    if not plane:
        return ""
    normalized = PLANE_ALIASES.get(plane, plane)
    for view_name, plane_name in SLICE_VIEW_TO_PLANE.items():
        if plane_name == normalized:
            return view_name
    return plane


def roi_geometry_type_export(roi_type):
    """Return a radiology-friendly geometry type for export."""
    return ROI_GEOMETRY_TYPES.get(roi_type, roi_type)


def roi_geometry_type_from_export(value):
    """Restore internal ROI type id from an exported geometry type label."""
    if not value:
        return ""
    for roi_type, label in ROI_GEOMETRY_TYPES.items():
        if label == value:
            return roi_type
    return value
