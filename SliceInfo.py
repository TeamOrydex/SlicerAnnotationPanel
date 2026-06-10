"""
Helpers for reading slice context and volume metadata from Slicer.
"""
import logging

from RadiologyTerms import slice_view_to_plane, plane_to_slice_view

logger = logging.getLogger(__name__)

_last_active_slice_view = "Red"
_slice_observers = []


def _matrix_to_list(matrix):
    values = []
    for row in range(4):
        for col in range(4):
            values.append(float(matrix.GetElement(row, col)))
    return values


def _get_slicer_version():
    try:
        import slicer
        return slicer.app.applicationVersion if hasattr(slicer.app, "applicationVersion") else ""
    except Exception:
        return ""


def install_slice_tracking():
    """Remember which slice view the user last scrolled or interacted with."""
    global _slice_observers
    remove_slice_tracking()
    try:
        import qt
        import slicer
        layout_manager = slicer.app.layoutManager()
        if not layout_manager:
            return

        for name in layout_manager.sliceViewNames():
            slice_widget = layout_manager.sliceWidget(name)
            if not slice_widget:
                continue
            slice_node = slice_widget.mrmlSliceNode()
            if not slice_node:
                continue

            def _on_slice_modified(caller, event, view_name=name):
                global _last_active_slice_view
                _last_active_slice_view = view_name

            tag = slice_node.AddObserver(slice_node.SliceModifiedEvent, _on_slice_modified)
            _slice_observers.append((slice_node, tag))

            slice_view = slice_widget.sliceView()
            if slice_view:
                interactor = slice_view.interactor()
                if interactor:
                    def _on_interactor_event(caller, event, view_name=name):
                        global _last_active_slice_view
                        _last_active_slice_view = view_name

                    import vtk
                    for event_id in (
                        vtk.vtkCommand.LeftButtonPressEvent,
                        vtk.vtkCommand.RightButtonPressEvent,
                    ):
                        tag = interactor.AddObserver(event_id, _on_interactor_event)
                        _slice_observers.append((interactor, tag))

                def _remember_view(view_name=name):
                    global _last_active_slice_view
                    _last_active_slice_view = view_name

                class _SliceViewTracker(qt.QObject):
                    def eventFilter(self, obj, event):
                        if event.type() in (qt.QEvent.MouseButtonPress, qt.QEvent.Wheel):
                            _remember_view()
                        return False

                tracker = _SliceViewTracker(slice_view)
                slice_view.installEventFilter(tracker)
                _slice_observers.append((slice_view, tracker))
    except Exception as e:
        logger.warning(f"Could not install slice tracking: {e}")


def remove_slice_tracking():
    global _slice_observers
    for node, tag in _slice_observers:
        try:
            import qt
            if isinstance(tag, qt.QObject):
                node.removeEventFilter(tag)
            else:
                node.RemoveObserver(tag)
        except Exception:
            pass
    _slice_observers = []


def set_active_slice_view(view_name):
    """Explicitly set the active slice view (Red/Green/Yellow)."""
    global _last_active_slice_view
    if view_name:
        _last_active_slice_view = view_name


def get_active_slice_view():
    """Return the slice view the user most recently interacted with."""
    try:
        import slicer
        layout_manager = slicer.app.layoutManager()
        if not layout_manager:
            return _last_active_slice_view or "Red"
        names = list(layout_manager.sliceViewNames())
        if _last_active_slice_view in names:
            return _last_active_slice_view
        return names[0] if names else "Red"
    except Exception:
        return _last_active_slice_view or "Red"


def _slice_view_name_for_widget(widget, layout_manager):
    """Find Red/Green/Yellow slice view name containing a Qt widget."""
    if widget is None or layout_manager is None:
        return None
    current = widget
    while current is not None:
        for name in layout_manager.sliceViewNames():
            slice_widget = layout_manager.sliceWidget(name)
            if slice_widget is None:
                continue
            if current is slice_widget:
                return name
            slice_view = slice_widget.sliceView()
            if slice_view and current is slice_view:
                return name
        try:
            current = current.parent()
        except Exception:
            break
    return None


def capture_slice_context_at_cursor(volume_node=None):
    """Capture slice context from whichever slice view is under the mouse cursor."""
    try:
        import qt
        import slicer
        app = qt.QApplication.instance()
        layout_manager = slicer.app.layoutManager()
        if not app or not layout_manager:
            return _empty_slice_info()

        widget = app.widgetAt(qt.QCursor.pos())
        view_name = _slice_view_name_for_widget(widget, layout_manager)
        if view_name:
            set_active_slice_view(view_name)
            return capture_slice_info_for_view(view_name, volume_node)
    except Exception as e:
        logger.debug(f"Could not capture slice context at cursor: {e}")
    return _empty_slice_info()


def remember_slice_view_interaction(view_name, volume_node=None):
    """Record a slice-view interaction and return its captured context."""
    if view_name:
        set_active_slice_view(view_name)
    return capture_slice_info_for_view(view_name or get_active_slice_view(), volume_node)


def _ras_to_ijk(volume_node, ras_point):
    try:
        import vtk
        ras = [ras_point[0], ras_point[1], ras_point[2], 1.0]
        ras_to_ijk = vtk.vtkMatrix4x4()
        volume_node.GetRASToIJKMatrix(ras_to_ijk)
        ijk = [0.0, 0.0, 0.0, 0.0]
        ras_to_ijk.MultiplyPoint(ras, ijk)
        return [int(round(ijk[0])), int(round(ijk[1])), int(round(ijk[2]))]
    except Exception:
        return []


def _dicom_field_for_volume(volume_node, tag):
    try:
        import slicer
        inst_uids = volume_node.GetAttribute("DICOM.instanceUIDs")
        if not inst_uids:
            return ""
        uid = inst_uids.split()[0]
        return slicer.dicomDatabase.fieldForInstance(uid, tag) or ""
    except Exception:
        return ""


def ras_to_voxel_ijk(volume_node, ras_point):
    """Convert a RAS point to rounded IJK voxel indices for a volume."""
    return _ras_to_ijk(volume_node, ras_point)


def capture_volume_metadata(volume_node):
    """Capture comprehensive metadata about a loaded volume/series."""
    meta = {
        "volume_node_id": "",
        "volume_name": "",
        "dimensions": [],
        "pixel_spacing": [],
        "image_origin": [],
        "ijk_to_ras_matrix": [],
        "modality": "",
        "patient_id": "",
        "study_description": "",
        "series_description": "",
        "study_instance_uid": "",
        "series_instance_uid": "",
        "series_number": "",
        "study_date": "",
        "instance_uids": [],
        "window_center": None,
        "window_width": None,
    }
    if volume_node is None:
        return meta

    try:
        meta["volume_node_id"] = volume_node.GetID() or ""
        meta["volume_name"] = volume_node.GetName() or ""

        image_data = volume_node.GetImageData()
        if image_data:
            meta["dimensions"] = list(image_data.GetDimensions())
        meta["pixel_spacing"] = [float(v) for v in volume_node.GetSpacing()]
        meta["image_origin"] = [float(v) for v in volume_node.GetOrigin()]

        import vtk
        ijk_to_ras = vtk.vtkMatrix4x4()
        volume_node.GetIJKToRASMatrix(ijk_to_ras)
        meta["ijk_to_ras_matrix"] = _matrix_to_list(ijk_to_ras)

        inst_uids = volume_node.GetAttribute("DICOM.instanceUIDs")
        if inst_uids:
            meta["instance_uids"] = inst_uids.split()
            meta["modality"] = _dicom_field_for_volume(volume_node, "0008,0060")
            meta["patient_id"] = _dicom_field_for_volume(volume_node, "0010,0020")
            meta["study_description"] = _dicom_field_for_volume(volume_node, "0008,1030")
            meta["series_description"] = _dicom_field_for_volume(volume_node, "0008,103e")
            meta["study_instance_uid"] = _dicom_field_for_volume(volume_node, "0020,000d")
            meta["series_instance_uid"] = _dicom_field_for_volume(volume_node, "0020,000e")
            meta["series_number"] = _dicom_field_for_volume(volume_node, "0020,0011")
            meta["study_date"] = _dicom_field_for_volume(volume_node, "0008,0020")

        display_node = volume_node.GetDisplayNode()
        if display_node:
            try:
                meta["window_center"] = float(display_node.GetWindowLevel()[0])
                meta["window_width"] = float(display_node.GetWindowLevel()[1])
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not capture volume metadata: {e}")
    return meta


def anatomical_slice_index_from_ijk(plane, voxel_index_ijk):
    """Return the voxel index along the slice-normal axis for an anatomical plane."""
    if not voxel_index_ijk or len(voxel_index_ijk) < 3:
        return 0
    normalized = slice_view_to_plane(plane)
    if normalized == "Axial":
        return int(voxel_index_ijk[2])
    if normalized == "Coronal":
        return int(voxel_index_ijk[1])
    if normalized == "Sagittal":
        return int(voxel_index_ijk[0])
    return int(voxel_index_ijk[2])


def _empty_slice_info():
    return {
        "plane": "",
        "slicer_slice_view": "",
        "slice_number": 0,
        "slice_offset_mm": 0.0,
        "position_ras": [],
        "voxel_index_ijk": [],
        "slice_to_ras_matrix": [],
        "field_of_view": [],
        "slice_spacing": 0.0,
        "slice_normal_ras": [],
        "volume_node_id": "",
        "volume_name": "",
        # Legacy aliases used internally by tabs during capture.
        "slice_view": "",
        "slice_index": 0,
        "slice_position_ras": [],
        "volume_slice_ijk": [],
    }


def capture_slice_info_for_view(slicer_view, volume_node=None):
    """Capture slice context for a specific Slicer slice view (Red/Green/Yellow)."""
    info = _empty_slice_info()
    try:
        import slicer
        layout_manager = slicer.app.layoutManager()
        if not layout_manager:
            return info

        if slicer_view not in layout_manager.sliceViewNames():
            names = list(layout_manager.sliceViewNames())
            slicer_view = names[0] if names else "Red"

        info["slicer_slice_view"] = slicer_view
        info["plane"] = slice_view_to_plane(slicer_view)
        info["slice_view"] = info["plane"]

        slice_widget = layout_manager.sliceWidget(slicer_view)
        if not slice_widget:
            return info

        slice_logic = slice_widget.sliceLogic()
        slice_node = slice_widget.mrmlSliceNode()
        if not slice_logic or not slice_node:
            return info

        offset = float(slice_logic.GetSliceOffset())
        info["slice_offset_mm"] = offset

        slice_to_ras = slice_node.GetSliceToRAS()
        info["slice_to_ras_matrix"] = _matrix_to_list(slice_to_ras)

        out = [0.0, 0.0, 0.0, 0.0]
        slice_to_ras.MultiplyPoint([0.0, 0.0, 0.0, 1.0], out)
        info["position_ras"] = [float(out[0]), float(out[1]), float(out[2])]
        info["slice_position_ras"] = info["position_ras"]

        try:
            fov = [0.0, 0.0]
            slice_node.GetFieldOfView(fov)
            info["field_of_view"] = [float(fov[0]), float(fov[1])]
        except Exception:
            pass

        try:
            info["slice_spacing"] = float(slice_node.GetSliceSpacing())
        except Exception:
            pass

        info["slice_normal_ras"] = [
            float(slice_to_ras.GetElement(0, 2)),
            float(slice_to_ras.GetElement(1, 2)),
            float(slice_to_ras.GetElement(2, 2)),
        ]

        if volume_node:
            info["volume_node_id"] = volume_node.GetID() or ""
            info["volume_name"] = volume_node.GetName() or ""
            info["voxel_index_ijk"] = _ras_to_ijk(volume_node, info["position_ras"])
            info["volume_slice_ijk"] = info["voxel_index_ijk"]

        anatomical_index = anatomical_slice_index_from_ijk(
            info["plane"], info.get("voxel_index_ijk", [])
        )
        if anatomical_index:
            info["slice_number"] = anatomical_index
            info["slice_index"] = anatomical_index
        else:
            try:
                if volume_node and hasattr(slice_logic, "GetSliceIndexFromOffset"):
                    dicom_index = slice_logic.GetSliceIndexFromOffset(offset, volume_node)
                elif hasattr(slice_logic, "GetSliceIndexFromOffset"):
                    dicom_index = slice_logic.GetSliceIndexFromOffset(offset)
                else:
                    dicom_index = -1
                if dicom_index >= 0:
                    info["slice_number"] = int(dicom_index)
                    info["slice_index"] = int(dicom_index)
                else:
                    info["slice_number"] = int(round(offset))
                    info["slice_index"] = info["slice_number"]
            except Exception:
                info["slice_number"] = int(round(offset))
                info["slice_index"] = info["slice_number"]
    except Exception as e:
        logger.warning(f"Could not capture slice info for view {slicer_view}: {e}")
    return info


def capture_slice_info(volume_node=None):
    """Capture slice view, geometry, RAS/IJK position, and volume linkage."""
    try:
        import slicer
        layout_manager = slicer.app.layoutManager()
        if not layout_manager:
            return _empty_slice_info()

        slicer_view = get_active_slice_view()
        if slicer_view not in layout_manager.sliceViewNames():
            names = list(layout_manager.sliceViewNames())
            slicer_view = names[0] if names else "Red"
    except Exception:
        slicer_view = get_active_slice_view() or "Red"

    return capture_slice_info_for_view(slicer_view, volume_node)


def capture_all_planes_slice_info(volume_node=None):
    """Capture slice context for Axial, Coronal, and Sagittal views at once."""
    planes = []
    for slicer_view in ("Red", "Green", "Yellow"):
        info = capture_slice_info_for_view(slicer_view, volume_node)
        if info.get("plane"):
            planes.append(info)
    return planes
