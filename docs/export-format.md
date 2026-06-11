# Annotation Export Format

Formal export from the Annotation Panel writes a scan-specific folder under the
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
5. Generated fallback: `scan-<record-id-prefix>`

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

Loading `annotations.json` from an export folder will automatically discover a
sibling `segmentation.nii.gz` when segmentation metadata is absent from JSON.

Older draft files named `annotation.json` that embed segmentation metadata in
JSON continue to load as before.

## Follow-up work

- Validate imported NIfTI label values against configured segmentation classes
  when label configuration is present.
- Optional explicit `segmentation_volume` reference field in export JSON for
  downstream tooling that cannot rely on sibling filename conventions.
