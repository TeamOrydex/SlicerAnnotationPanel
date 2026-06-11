# Annotation Export Format

Formal export from the Annotation Panel writes a folder under the
directory chosen in the export dialog.

## Folder layout

```text
<selected-export-directory>/
└── <scan-folder>/
    ├── annotations.json
    ├── segmentation.nii.gz       # plain labelmap (when segmentation exists)
    ├── segmentation.nrrd         # plain labelmap (when segmentation exists)
    └── segmentation.seg.nrrd     # Slicer-native (names and colors preserved)
```

Example:

```text
Export/
└── Patient_123_Scan/
    ├── annotations.json
    ├── segmentation.nii.gz
    ├── segmentation.nrrd
    └── segmentation.seg.nrrd
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

Contains classification labels, ROI annotations, label configuration, series
metadata, and lightweight segmentation metadata. Segmentation voxel data is
**not** included in this file (see sibling segmentation volume files below).

Primary keys:

| Concept | Key |
|---------|-----|
| Schema version | `schema_version` |
| Export timestamp | `exported_at` |
| Label configuration | `label_configuration` |
| Image series metadata | `series_metadata` |
| Classification labels | `classification_labels` |
| Regions of interest | `regions_of_interest` |
| Segmentation metadata | `segmentation` |

Formal export writes **canonical keys only**. Import still accepts legacy
aliases (`label_config`, `scan`, `class_labels`, `rois`) from older export
files and draft JSON saves.

### Creation timestamps

Each annotation type may include a `created_at` field (ISO 8601 UTC, e.g.
`2026-06-11T15:42:31Z`) recording when the annotation was first created:

| Type | Location | Notes |
|------|----------|-------|
| Classification | `classification_labels[].created_at` | Set when the user adds a label |
| ROI | `regions_of_interest[].created_at` | Set when the shape is finalized |
| Segmentation | `segmentation.segments[].created_at` | Set when the segment is first created |

`created_at` is not updated by edits (move, resize, rename, or paint). Imported
timestamps are preserved; older files without `created_at` remain importable.

## segmentation.nii.gz

Multi-label segmentation masks exported as a NIfTI labelmap volume. Labelmap data is
converted to a scalar volume before writing because Slicer's labelmap storage nodes
do not support direct NIfTI export.

Each segment label value in the volume corresponds to the combined labelmap
produced from all configured segmentation classes.

## segmentation.nrrd

Plain NRRD labelmap with the same voxel values and spatial metadata as
`segmentation.nii.gz`. Intended for tools that prefer NRRD over NIfTI.

Segment names and colors are **not** embedded in this file. Use
`segmentation.seg.nrrd` or `annotations.json` (`label_configuration.segment_labels`)
for label semantics.

## segmentation.seg.nrrd

Slicer-native segmentation export. Preserves segment names, colors, and geometry
metadata in a single file.

Use this file when loading segmentations directly in 3D Slicer via **Data → Add
Data** — it loads as a segmentation with correct names and colors without a
separate color table.

### Segmentation metadata in annotations.json

When segmentation annotations exist, formal export also writes a trimmed
`segmentation` object in `annotations.json`:

| Key | Purpose |
|-----|---------|
| `segments` | Per-segment metadata (`id`, `name`, `segment_id`, `label_config_id`, `created_at`) |
| `label_to_segment_map` | Maps configured label ids to MRML segment ids |

Modification events, spatial extent, and voxel counts are omitted from formal
export to keep the JSON compact. Full segmentation metadata remains available in
draft JSON exports.

## Import behavior

Use **Import Annotations** in the annotation workspace (after configuration is
confirmed). You can select:

- An **export folder** containing `annotations.json` and optional segmentation volume(s)
- A single **`annotations.json`** file (sibling segmentation files are discovered automatically)
- A single segmentation file (`segmentation.nii.gz`, `segmentation.nrrd`, or
  `segmentation.seg.nrrd`)

When multiple segmentation files are present, import prefers `segmentation.seg.nrrd`,
then `segmentation.nii.gz`, then `segmentation.nrrd`.

Import does **not** require a loaded scan. Annotations restore into the active
session whether or not a series is loaded.

### Configuration reconciliation

After a package loads successfully, the panel compares the imported
`label_configuration` with the active session configuration (label ids, names,
colors, and ROI drawing tools).

| Outcome | Behavior |
|---------|----------|
| Configurations match | Classification, ROI, and segmentation data load under the current configuration |
| Configurations differ — **Import New Configuration** | Existing configuration and annotations are replaced; imported preset is saved as `Import-<scan-name>`; user returns to the configuration screen to review before continuing |
| Configurations differ — **Keep Current Configuration** | Import is cancelled; no partial changes are applied |

### What is restored

| Source | Restored into |
|--------|----------------|
| `label_configuration` | Active preset (saved as `Import-<scan-name>`) and all three label tables when configuration is replaced |
| `classification_labels` | Classification tab (mapped by `category_id`; `created_at` preserved) |
| `regions_of_interest` | ROI tab and MRML markup nodes (mapped by `category_id`; `created_at` preserved) |
| `segmentation` | Segment `created_at` and `label_to_segment_map` (mapped onto imported MRML segments) |
| `segmentation.seg.nrrd` | Segmentation tab (names and colors preserved) |
| `segmentation.nii.gz` or `segmentation.nrrd` | Segmentation tab (label values mapped to `segment_labels` order) |

`label_configuration` is authoritative: names, colors, and descriptions from the
JSON config sync onto imported annotations using stable label ids.

### Partial import

| Situation | Behavior |
|-----------|----------|
| `annotations.json` missing, segmentation volume present | Segmentation loads; warning shown |
| All segmentation volumes missing, JSON present | Classification and ROI load; warning shown |
| Invalid JSON | Error dialog; no crash |

### Segmentation label mapping

Plain labelmap exports (`segmentation.nii.gz`, `segmentation.nrrd`) use values
`1`, `2`, `3`, … in the same order as `segment_labels` in `label_configuration`.
On import, each value maps back to the corresponding configured class. Missing
classes are added as empty segments.

`segmentation.seg.nrrd` carries segment names and colors in the file itself.

### Draft files

Older draft JSON files that embed segmentation metadata in JSON (instead of a
sibling NIfTI) continue to load through the same import path.

## Follow-up work

- Optional explicit `segmentation_volume` reference field in export JSON for
  downstream tooling that cannot rely on sibling filename conventions.
