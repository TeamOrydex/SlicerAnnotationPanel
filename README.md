# AnnotationPanel

A custom annotation panel for 3D Slicer that supports:
- Class-level labels (whole-scan classification tags)
- ROI annotations (ellipse, rectangle, polygon, freehand curve, line)
- Segmentation masks (paint, erase, threshold, flood fill, scissors)

## Structure

```
AnnotationPanel/
├── AnnotationPanel.py          # Slicer scripted loadable module entry point
├── PanelWidget.py              # Root QWidget: tabs and action bar
├── AnnotationModel.py          # Data model (dataclass → dict → JSON)
├── ClassLabelTab.py            # Class-level label UI
├── ROITab.py                   # ROI drawing tools (Markups integration)
├── SegmentationTab.py          # Segmentation tab (embedded Segment Editor)
├── TestHarnessModule/          # Standalone test module for Slicer
├── Tests/                      # Unit tests for the data model
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
python Tests/TestAnnotationModel.py -v
```

### Integration Testing (in Slicer)

Load the **Annotation Panel Test Harness** module in Slicer. It provides buttons to load a sample volume, add sample ROIs, add sample segmentation, and test the export workflow.

## Requirements

- 3D Slicer 5.x+ (Python 3.9+, Qt via PythonQt)
- No external dependencies — uses only Python stdlib and Slicer's bundled libraries
