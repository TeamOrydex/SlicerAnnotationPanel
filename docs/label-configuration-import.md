# Label configuration import guide

Use this format when creating a JSON preset for the **Label Configuration** screen in Annotation Panel.

## How to import

1. Open Annotation Panel in 3D Slicer.
2. On the **Label Configuration** screen, click **Import from JSON**.
3. Select your `.json` file.
4. Confirm when prompted — importing **replaces** all labels currently shown in the three category tables.
5. Review the loaded labels, then click **Confirm & Start Annotation**.

You can also export a starting point from the same screen with **Save as Preset**.

---

## Top-level structure

The file is a single JSON object with **three arrays**, one per label category:

| Key (preferred) | Legacy key (also accepted) | Purpose |
|-----------------|----------------------------|---------|
| `classification_labels` | `class_labels` | Whole-slice classification categories (e.g. Normal / Abnormal) |
| `roi_categories` | `roi_labels` | Categories for drawn regions of interest |
| `segment_labels` | `segmentation_classes` | Voxel-level segment names for the segmentation tab |

Each array contains zero or more **label objects**. At least **one label total** across all three arrays is required before you can start annotation.

---

## Label object fields

Each entry in an array is an object with these fields:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | **Yes** | string | Display name shown in dropdowns and exports. Must be unique within its category. |
| `color` | No | string | Hex color for the label swatch and annotations. Default: `#ff0000`. Use `#RRGGBB` (e.g. `#8B4513`). |
| `description` | No | string | Optional tooltip / export metadata describing the label. |
| `id` | No | string | Stable UUID for the label. If omitted, a new UUID is generated on import. |

---

## Minimal example

```json
{
  "classification_labels": [
    {
      "name": "Normal",
      "color": "#4CAF50",
      "description": "No abnormality identified"
    },
    {
      "name": "Abnormal",
      "color": "#f44336",
      "description": "Abnormality present"
    }
  ],
  "roi_categories": [
    {
      "name": "Lesion",
      "color": "#e6194b",
      "description": "Focal lesion region"
    }
  ],
  "segment_labels": [
    {
      "name": "Lesion",
      "color": "#e6194b",
      "description": "Lesion segmentation"
    }
  ]
}
```

---

## Full example (Spleen CT workflow)

This matches the built-in **Spleen CT Annotation** preset structure:

```json
{
  "classification_labels": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Normal",
      "color": "#4CAF50",
      "description": "Normal spleen size and appearance"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "name": "Enlarged",
      "color": "#FF9800",
      "description": "Splenomegaly"
    },
    {
      "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "name": "Abnormal",
      "color": "#f44336",
      "description": "Focal or diffuse abnormality"
    }
  ],
  "roi_categories": [
    {
      "name": "Spleen",
      "color": "#8B4513",
      "description": "Spleen boundary region"
    },
    {
      "name": "Lesion",
      "color": "#e6194b",
      "description": "Focal splenic lesion"
    },
    {
      "name": "Infarct",
      "color": "#911eb4",
      "description": "Splenic infarct"
    },
    {
      "name": "Accessory Spleen",
      "color": "#4363d8",
      "description": "Accessory splenic tissue"
    },
    {
      "name": "Artifact",
      "color": "#808080",
      "description": "Imaging artifact"
    }
  ],
  "segment_labels": [
    {
      "name": "Spleen",
      "color": "#8B4513",
      "description": "Spleen parenchyma"
    },
    {
      "name": "Lesion",
      "color": "#e6194b",
      "description": "Focal lesion segmentation"
    },
    {
      "name": "Infarct",
      "color": "#911eb4",
      "description": "Infarcted tissue"
    }
  ]
}
```

---

## Legacy key names

Older presets may use the legacy top-level keys. Import accepts **either** naming scheme:

```json
{
  "class_labels": [
    { "name": "Normal", "color": "#4CAF50" }
  ],
  "roi_labels": [
    { "name": "Tumor", "color": "#e6194b" }
  ],
  "segmentation_classes": [
    { "name": "Tumor Core", "color": "#e6194b" }
  ]
}
```

When you **Save as Preset** from the panel, exports use the preferred keys: `classification_labels`, `roi_categories`, and `segment_labels`.

---

## Tips and constraints

- **Category scope** — Label names only need to be unique *within* one array. The same name (e.g. `Lesion`) may appear in both `roi_categories` and `segment_labels` with different roles.
- **Colors** — Use distinct hex colors within each category so labels are easy to tell apart in the UI. If you add labels manually in the panel, unused palette colors are assigned automatically.
- **IDs** — Include stable `id` values when you need to round-trip configs or merge with existing annotation exports that reference `label_config_id`.
- **Empty categories** — Any of the three arrays may be empty `[]` if you do not use that annotation mode, as long as at least one label exists somewhere.
- **Not a full annotation export** — This file defines **label definitions only**. It does not contain drawn ROIs, painted segments, or classification annotations. Those live in the full annotation JSON export under `label_configuration` inside an annotation record.

---

## Validation checklist

Before sharing a preset file:

- [ ] Valid JSON (no trailing commas, double-quoted keys and strings)
- [ ] At least one label with a non-empty `name`
- [ ] No duplicate `name` values within the same array
- [ ] Colors in `#RRGGBB` form when provided
- [ ] File extension `.json` for the import dialog filter

---

## Related files in this repository

- `ConfigurationScreen.py` — Import/export UI and built-in presets
- `AnnotationModel.py` — `LabelConfig` and `LabelDefinition` schema
- `LabelColors.py` — Default color palette for manual label creation
