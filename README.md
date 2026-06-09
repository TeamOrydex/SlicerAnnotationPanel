# AnnotationPanel

A custom annotation panel for 3D Slicer that supports:
- **Classification labels** — slice-level categories applied at the current anatomical plane
- **Regions of interest (ROI)** — bounding boxes, polygon/freehand contours, and linear measurements
- **Segmentations** — voxel-level segment painting (paint, erase, threshold, scissors)

## Structure

```
AnnotationPanel/
├── AnnotationPanel.py          # Slicer scripted loadable module entry point
├── PanelWidget.py              # Root QWidget: tabs and action bar
├── AnnotationModel.py          # Data model (dataclass → dict → JSON)
├── RadiologyTerms.py           # Anatomical plane and export terminology
├── SliceInfo.py                # Slice view capture and plane mapping
├── ClassLabelTab.py            # Classification label UI
├── ROITab.py                   # ROI drawing tools (Markups integration)
├── SegmentationTab.py          # Segmentation tab (embedded Segment Editor)
├── ConfigurationScreen.py      # Label configuration and presets
├── TestHarnessModule/          # Standalone test module for Slicer
├── Tests/                      # Unit tests for the data model
└── Resources/Icons/            # Module icons
```

## Export terminology

Exports are intentionally verbose so downstream tools can simplify as needed. Each export includes:

- **Schema version** and **export timestamp**
- **Full label configuration** snapshot
- **Series metadata** including DICOM UIDs, pixel spacing, IJK→RAS matrix, window/level
- **Classification labels** with category id/color, plane, slice geometry, RAS/IJK position
- **Regions of interest** with geometry type, control points, orientation, MRML node references
- **Segmentation** with segment ids, voxel counts, and label-to-segment mapping

Legacy keys (`scan`, `class_labels`, `rois`, etc.) are also included for backward compatibility.

| Concept | Primary export key |
|---------|-------------------|
| Image series metadata | `series_metadata` |
| Classification labels | `classification_labels` |
| Regions of interest | `regions_of_interest` |
| Anatomical planes | `Axial`, `Coronal`, `Sagittal` |

## Installation

Add this repository's root directory to Slicer's additional module paths:
1. Open 3D Slicer
2. Go to Edit → Application Settings → Modules
3. Add the path to this `AnnotationPanel/` directory
4. Restart Slicer

The module will appear under the "Annotation" category.

## Testing

### Unit Tests (standalone Python)

```bash
cd AnnotationPanel
python Tests/TestAnnotationModel.py -v
```

### Integration Testing (in Slicer)

Load the **Annotation Panel Test Harness** module in Slicer. It provides buttons to load a sample volume, add sample ROIs, add sample segmentation, and test the export workflow.

## Requirements

- 3D Slicer 5.x+ (Python 3.9+, Qt via PythonQt)
- No external dependencies — uses only Python stdlib and Slicer's bundled libraries
