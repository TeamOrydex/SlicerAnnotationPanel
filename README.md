# AnnotationPanel

A custom annotation panel for 3D Slicer that supports:
- Class-level labels (whole-scan classification tags)
- ROI annotations (ellipse, rectangle, polygon)
- Segmentation masks (brush, threshold, flood fill)
- Freeform JSON metadata

Includes annotator/reviewer workflow: annotators create and submit annotations, reviewers approve or reject with comments.

## Structure

```
AnnotationPanel/
├── AnnotationPanel.py          # Slicer scripted loadable module entry point
├── AnnotationPanelWidget.py    # Root QWidget: tabs, mode toggle, status, action bar
├── AnnotationModel.py          # Data model (dataclass → dict → JSON)
├── ClassLabelTab.py            # Class-level label UI
├── ROITab.py                   # ROI tab (Phase 2)
├── SegmentationTab.py          # Segmentation tab (Phase 3)
├── FreeformJsonTab.py          # Freeform JSON tab (Phase 4)
├── ReviewBar.py                # Review controls (approve/reject/comment)
├── TestAnnotationModel.py      # Unit tests for the data model
├── TestHarnessModule.py        # Standalone test module for Slicer
└── Resources/Icons/            # Module icons
```

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
python -m pytest TestAnnotationModel.py -v
# or
python TestAnnotationModel.py
```

### Integration Testing (in Slicer)

Load the **Annotation Panel Test Harness** module in Slicer. It provides a button to load a sample volume and displays the annotation panel with dummy study/series IDs.

## Development Phases

- **Phase 1** ✓ Panel shell + Class Label tab
- **Phase 2**: ROI tab (Markups integration)
- **Phase 3**: Segmentation tab (Segment Editor effects)
- **Phase 4**: Freeform JSON tab
- **Phase 5**: Reviewer workflow enhancements
- **Phase 6**: Integration + test harness

## Requirements

- 3D Slicer 5.x+ (Python 3.9+, Qt via PythonQt)
- No external dependencies — uses only Python stdlib and Slicer's bundled libraries
