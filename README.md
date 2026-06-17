# AnnotationPanel

A custom annotation panel for 3D Slicer that supports:
- **Classification labels** — slice-level categories applied at the current anatomical plane
- **Regions of interest (ROI)** — bounding boxes, polygon/freehand contours, and linear measurements; per-ROI and global hide/show toggles in the ROI tab (view state is session-only and not exported)
- **Segmentations** — voxel-level segment painting (paint, erase, threshold, scissors)

## Intended Use Cases

- **ML training data** — annotate CT/MRI studies with classification labels, ROI geometry, and segmentation masks in one session, then export a structured package for training pipelines.
- **Multi-annotator studies** — distribute a named preset so every team member uses the same label schema; export packages are self-contained and portable across machines.
- **Clinical research review** — mark slice-level findings, draw organ or lesion boundaries, and paint voxel segmentations without leaving a single panel.
- **Iterative annotation** — export mid-session, hand off to a colleague, and resume from the same state via import; configuration conflicts are resolved explicitly rather than silently.
- **Scan-independent setup** — define and save label configurations before imaging data arrives; link a volume later and re-export with full DICOM metadata.

## Features

### Classification Annotation
Assign slice-level labels across Axial, Coronal, and Sagittal planes in a single action. Each label captures exact slice indexes and spatial offsets for all three orientations.

![Classification Annotation](static/classification-annotation.png)

### ROI Annotation
Draw regions of interest using five markup types — 2D bounding box, 3D bounding box, polygon contour, freehand contour, and linear measurement. Each ROI category is pre-bound to a drawing tool at configuration time.

![ROI Annotation](static/roi-annotation.png)

### Segmentation Annotation
Paint, threshold, erase, and refine voxel-level segmentations with 14 curated Segment Editor effects embedded directly in the panel.

![Segmentation Annotation](static/seg-threshold.png)

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
    ├── segmentation.nii.gz       # when segmentation annotations exist
    ├── segmentation.nrrd         # when segmentation annotations exist
    └── segmentation.seg.nrrd     # when segmentation annotations exist
```

Folder naming uses scan metadata when a series is linked (`Patient_123_Scan`, volume
name, study/series id). Without scan metadata, exports use a standalone fallback such
as `AnnotationSession_2026_06_11/` or `Export_<id-prefix>/`.

`annotations.json` contains classification labels, ROIs, label configuration, and series metadata. Segmentation voxel data is exported separately as `segmentation.nii.gz`, `segmentation.nrrd`, and `segmentation.seg.nrrd` (Slicer-native with names and colors), not embedded in the JSON.

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

| Concept | Primary export key |
|---------|-------------------|
| Image series metadata | `series_metadata` |
| Classification labels | `classification_labels` |
| Regions of interest | `regions_of_interest` |
| Segmentation volume | `segmentation.seg.nrrd` (preferred), `segmentation.nii.gz`, or `segmentation.nrrd` (sibling files) |
| Anatomical planes | `Axial`, `Coronal`, `Sagittal` |

## Installation

1. Open 3D Slicer
2. Go to **View → Extensions Manager**
3. Search for **AnnotationPanel**
4. Click **Install** and restart Slicer when prompted

The module will appear under the **Quantification** category.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/FEATURES.md](docs/FEATURES.md) | Full feature descriptions, use cases, and screenshots |
| [docs/FEATURES_OVERVIEW.md](docs/FEATURES_OVERVIEW.md) | Browsable feature index with links into FEATURES.md |
| [docs/export-format.md](docs/export-format.md) | Export folder layout, JSON schema, and import behavior |
| [docs/label-configuration-import.md](docs/label-configuration-import.md) | Preset JSON format and field reference |
| [docs/example_preset.json](docs/example_preset.json) | Example Lungs CT preset ready to import |

## Requirements

- 3D Slicer 5.x+ (Python 3.9+, Qt via PythonQt)
- No external dependencies — uses only Python stdlib and Slicer's bundled libraries
