# AnnotationPanel

A custom annotation panel for 3D Slicer that supports:
- **Classification labels** — slice-level categories applied at the current anatomical plane
- **Regions of interest (ROI)** — bounding boxes, polygon/freehand contours, and linear measurements; per-ROI and global hide/show toggles in the ROI tab (view state is session-only and not exported)
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

## Workflow

The panel works as a standalone annotation tool. Configure labels on the
configuration screen, then continue to the annotation workspace for
classification, ROI, and segmentation work. A loaded image series is optional.

```text
Open Extension → Configure Labels → (Save Preset if needed) → Annotate → Import / Export
```

On the configuration screen you can manage presets (save, load, delete),
clear labels per category or all at once, and import JSON from disk. You can
**Confirm & Start Annotation** immediately after loading an unmodified preset
from the dropdown. Manually created labels, JSON imports, and imported
annotation packages require **Save as Preset** first; modified loaded presets
must be saved again before continuing.

Load images through Slicer's built-in tools (Data module, drag-and-drop, DICOM).
When a series is present in the scene, the panel links it automatically for export
metadata without exposing series management in the panel UI.

## Export terminology

Formal export writes a folder under the directory you choose:

```text
<export-directory>/
└── <folder-name>/
    ├── annotations.json
    └── segmentation.nii.gz   # when segmentation annotations exist
```

Folder naming uses scan metadata when a series is linked (`Patient_123_Scan`, volume
name, study/series id). Without scan metadata, exports use a standalone fallback such
as `AnnotationSession_2026_06_11/` or `Export_<id-prefix>/`.

`annotations.json` contains classification labels, ROIs, label configuration, and series metadata. Segmentation voxel data is exported separately as `segmentation.nii.gz`, not embedded in the JSON.

**Import Annotations** and **Export Annotations** are available in the annotation
workspace (after configuration is confirmed). Import restores an export folder
(or `annotations.json`) back into the panel. When the imported
`label_configuration` differs from the active configuration, you can replace
the session with the imported project (and return to the configuration screen
for review) or cancel and keep the current configuration unchanged. A loaded scan
is not required.

See [docs/export-format.md](docs/export-format.md) for folder naming, file contents, and import behavior.

Each export includes:

- **Schema version** and **export timestamp**
- **Full label configuration** snapshot
- **Series metadata** including DICOM UIDs, pixel spacing, IJK→RAS matrix, window/level
- **Classification labels** with category id/color, plane, slice geometry, RAS/IJK position
- **Regions of interest** with geometry type, control points, orientation, MRML node references

Legacy keys (`scan`, `class_labels`, `rois`, etc.) are also included for backward compatibility.

| Concept | Primary export key |
|---------|-------------------|
| Image series metadata | `series_metadata` |
| Classification labels | `classification_labels` |
| Regions of interest | `regions_of_interest` |
| Segmentation volume | `segmentation.nii.gz` (sibling file) |
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
