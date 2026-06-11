# Annotation Export Format

Formal export from the Annotation Panel writes a folder under the
directory chosen in the export dialog.

## Folder layout

```text
<selected-export-directory>/
└── <scan-folder>/
    ├── annotations.json
    └── segmentation.nii.gz   # present when segmentation annotations exist
```

Example:

```text
Export/
└── Patient_123_Scan/
    ├── annotations.json
    └── segmentation.nii.gz
```

## Folder naming

The scan folder name is derived from available metadata, in priority order:

1. Scan filename stem (without extension)
2. Volume name
3. Study identifier (`study_id`)
4. Series identifier (`series_id`)
5. Standalone fallback: `AnnotationSession_YYYY_MM_DD` (UTC date)
6. Last resort: `Export_<record-id-prefix>`

When no series is linked, step 5 or 6 applies so export still succeeds.

Invalid path characters are replaced with underscores. If a folder with the
same name already exists, a numeric suffix is appended (`_2`, `_3`, ...).

## annotations.json

Contains classification labels, ROI annotations, label configuration, and
series metadata. Segmentation voxel data is **not** included in this file.

Primary keys:

| Concept | Key |
|---------|-----|
| Schema version | `schema_version` |
| Export timestamp | `exported_at` |
| Label configuration | `label_configuration` |
| Image series metadata | `series_metadata` |
| Classification labels | `classification_labels` |
| Regions of interest | `regions_of_interest` |

Legacy aliases (`label_config`, `scan`, `class_labels`, `rois`) are still
written for backward compatibility.

Draft saves (`Save Draft`) continue to use a single JSON file and may still
include segmentation metadata for in-progress work.

## segmentation.nii.gz

Multi-label segmentation masks exported as a NIfTI labelmap volume. Labelmap data is
converted to a scalar volume before writing because Slicer's labelmap storage nodes
do not support direct NIfTI export.

Each segment label value in the volume corresponds to the combined labelmap
produced from all configured segmentation classes.

## Import behavior

Use **Import Annotations** in the panel action bar. You can select:

- An **export folder** containing `annotations.json` and optional `segmentation.nii.gz`
- A single **`annotations.json`** file (sibling `segmentation.nii.gz` is discovered automatically)

Import does **not** require a loaded scan. Annotations restore into the active
session whether or not a series is loaded.

### What is restored

| Source | Restored into |
|--------|----------------|
| `label_configuration` | Active preset (saved as `Import-<scan-name>`) and all three label tables |
| `classification_labels` | Classification tab (mapped by `category_id`) |
| `regions_of_interest` | ROI tab and MRML markup nodes (mapped by `category_id`) |
| `segmentation.nii.gz` | Segmentation tab (label values mapped to `segment_labels` order) |

`label_configuration` is authoritative: names, colors, and descriptions from the
JSON config sync onto imported annotations using stable label ids.

### Partial import

| Situation | Behavior |
|-----------|----------|
| `annotations.json` missing, NIfTI present | Segmentation loads; warning shown |
| NIfTI missing, JSON present | Classification and ROI load; warning shown |
| Invalid JSON | Error dialog; no crash |

### Segmentation label mapping

Exported NIfTI uses labelmap values `1`, `2`, `3`, … in the same order as
`segment_labels` in `label_configuration`. On import, each value maps back to
the corresponding configured class. Missing classes are added as empty segments.

### Draft files

Older draft JSON files that embed segmentation metadata in JSON (instead of a
sibling NIfTI) continue to load through the same import path.

## Follow-up work

- Optional explicit `segmentation_volume` reference field in export JSON for
  downstream tooling that cannot rely on sibling filename conventions.
