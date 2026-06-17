# Label configuration import guide

Use this format when creating a JSON preset for the **Label Configuration** screen in Annotation Panel.

## How to import

1. Open Annotation Panel in 3D Slicer.
2. On the **Label Configuration** screen, either:
   - choose a saved preset from the **Presets** dropdown (if any exist), or
   - click **Import from JSON** and select a `.json` file from anywhere on disk.
3. Confirm when prompted — loading a preset or import **replaces** all labels currently shown in the three category tables.
4. Review the loaded labels.
5. Click **Confirm & Start Annotation** when the configuration is ready:
   - **Loaded preset** from the dropdown: continue immediately if you have not edited the labels.
   - **Manual labels** or **Import from JSON**: click **Save as Preset** first (unique name required).
   - **Imported annotation package**: click **Save as Preset** before continuing, even if a temporary import preset was created automatically.
   - **Modified loaded preset**: save your changes as a preset before continuing.

To save labels you created manually or imported from JSON, click **Save as Preset**, enter a **unique preset name** (required), and the configuration is written as JSON into the extension's `presets/` folder beside the module. Saved presets then appear in the dropdown automatically.

**Delete Preset** removes the selected preset JSON from disk (with confirmation). **Clear Labels** in each category section removes only that category's rows. **Clear Everything** removes all labels from all three tables. Destructive actions always prompt for confirmation.

---

## Top-level structure

The file is a single JSON object with **three arrays**, one per label category:

| Key (preferred) | Legacy key (also accepted) | Purpose |
|-----------------|----------------------------|---------|
| `classification_labels` | `class_labels` | Whole-slice classification categories (e.g. Normal / Abnormal) |
| `roi_categories` | `roi_labels` | Categories for drawn regions of interest |
| `segment_labels` | `segmentation_classes` | Voxel-level segment names for the segmentation tab |

Each array contains zero or more **label objects**. At least **one label total** across all three arrays is required before you can start annotation. Manually created and imported configurations must be saved as a preset before continuing; an unmodified preset loaded from the dropdown is already considered saved.

---

## Label object fields

Each entry in an array is an object with these fields:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | **Yes** | string | Display name shown in dropdowns and exports. Must be unique within its category. |
| `color` | No | string | Hex color for the label swatch and annotations. Default: `#ff0000`. Use `#RRGGBB` (e.g. `#8B4513`). |
| `description` | No | string | Optional tooltip / export metadata describing the label. |
| `id` | No | string | Stable UUID for the label. If omitted, a new UUID is generated on import. |
| `drawing_tool` | No | string | **ROI categories only.** Internal drawing tool id (`rectangle_2d`, `rectangle_3d`, `polygon`, `freehand_curve`, `line`). Display names such as `Polygon Contour` are also accepted on import. Default when omitted: `rectangle_3d` (Bounding Box). |

---

## Minimal example

```json
{
  "classification_labels": [
    {
      "name": "Non-Small Cell Lung Cancer (NSCLC)",
      "color": "#f44336",
      "description": "Primary diagnosis; encompasses large cell carcinoma, squamous cell carcinoma, and adenocarcinoma subtypes"
    },
    {
      "name": "Adenocarcinoma",
      "color": "#ffc107",
      "description": "Most common NSCLC subtype; typically peripheral and may present as a ground-glass opacity on CT"
    }
  ],
  "roi_categories": [
    {
      "name": "GTV-1",
      "color": "#4caf50",
      "description": "Gross Tumor Volume of the primary lung malignancy",
      "drawing_tool": "rectangle_3d"
    }
  ],
  "segment_labels": [
    {
      "name": "GTV-1",
      "color": "#00ff78",
      "description": "Voxel-level segmentation of the primary gross tumor volume"
    }
  ]
}
```

---

## Full example (multi-category workflow)

Example preset with all three label categories populated:

```json
{
  "classification_labels": [
    {
      "id": "594fdde5-40aa-4b02-a946-89ccdfb2cb69",
      "name": "Non-Small Cell Lung Cancer (NSCLC)",
      "color": "#f44336",
      "description": "Primary diagnosis for all patients in this collection; encompasses large cell carcinoma, squamous cell carcinoma, and adenocarcinoma histological subtypes"
    },
    {
      "id": "366d0af1-6fbe-4e7f-934b-5b0de7faaa1c",
      "name": "Large Cell Carcinoma",
      "color": "#ff5722",
      "description": "Undifferentiated NSCLC subtype that does not fit squamous or glandular patterns; tends to present as a large peripheral mass and carries a poor prognosis"
    },
    {
      "id": "2a01ce7d-1321-404c-be20-3705dd308899",
      "name": "Squamous Cell Carcinoma",
      "color": "#ff9800",
      "description": "NSCLC subtype strongly associated with smoking; typically arises centrally near the bronchi and may present with cavitation on CT"
    },
    {
      "id": "9c08f89c-c598-4146-bf72-c5b3f6117fa0",
      "name": "Adenocarcinoma",
      "color": "#ffc107",
      "description": "Most common NSCLC subtype; typically peripheral in location and may present as a ground-glass opacity, part-solid, or solid nodule on CT"
    },
    {
      "id": "48900027-0993-478e-86eb-39ae02d9a2c9",
      "name": "Stage IIIb",
      "color": "#9c27b0",
      "description": "Advanced locoregional disease; defined by T any N3 M0 or T4 N2 M0; indicates contralateral mediastinal or supraclavicular lymph node involvement without distant metastasis"
    },
    {
      "id": "6ae68106-1ccf-47f9-b74f-00c229d156fe",
      "name": "Stage IIIa",
      "color": "#673ab7",
      "description": "Locoregional disease with ipsilateral mediastinal or subcarinal lymph node involvement (N2); potentially resectable in select cases"
    },
    {
      "id": "c04b9751-d8b1-4517-b52f-b3f07b94db32",
      "name": "Stage IIb",
      "color": "#3f51b5",
      "description": "Tumor with limited nodal involvement (N1) or a larger T3 tumor with no nodal spread; surgical resection is the primary treatment option"
    },
    {
      "id": "767f7d29-93a9-4d65-8b4a-b817537c578d",
      "name": "Stage Ia / Ib",
      "color": "#2196f3",
      "description": "Early-stage disease confined to the lung without lymph node involvement; Ia is smaller than 3 cm, Ib is between 3 and 5 cm; best surgical outcomes"
    },
    {
      "id": "e4e41dce-3026-4b84-898d-6c5a49d93e97",
      "name": "Deceased",
      "color": "#607d8b",
      "description": "Patient outcome; deadstatus.event = 1 in the NSCLC-Radiomics clinical spreadsheet; survival time recorded in days from diagnosis"
    },
    {
      "id": "9114ebd4-04b9-460f-83c7-6edc7a799883",
      "name": "Alive",
      "color": "#4caf50",
      "description": "Patient outcome; deadstatus.event = 0 in the NSCLC-Radiomics clinical spreadsheet; patient was alive at last follow-up"
    }
  ],
  "roi_categories": [
    {
      "id": "f81b6085-9da1-40c9-98cc-311dcb1ee456",
      "name": "GTV-1",
      "color": "#4caf50",
      "description": "Gross Tumor Volume of the primary lung malignancy; manually contoured by a radiation oncologist; used as the target volume in radiotherapy planning",
      "drawing_tool": "rectangle_3d"
    },
    {
      "id": "d81368e4-ff2c-44be-95c8-294eb9951900",
      "name": "Left Lung",
      "color": "#2196f3",
      "description": "Entire left lung parenchyma; delineated as an organ at risk in radiotherapy planning to limit radiation dose and prevent pneumonitis",
      "drawing_tool": "rectangle_3d"
    },
    {
      "id": "3834d694-48da-40a3-bea9-dc1ba26a4b8c",
      "name": "Right Lung",
      "color": "#1565c0",
      "description": "Entire right lung parenchyma; delineated as an organ at risk in radiotherapy planning; the right lung has three lobes compared to two on the left",
      "drawing_tool": "rectangle_3d"
    },
    {
      "id": "241182b4-6bd8-4c82-bbf2-482e9cb35be4",
      "name": "Spinal Cord",
      "color": "#ff9800",
      "description": "Spinal cord delineated as a critical organ at risk; strict dose constraints are applied to avoid radiation myelopathy, an irreversible and potentially fatal complication",
      "drawing_tool": "freehand_curve"
    }
  ],
  "segment_labels": [
    {
      "id": "63f949b8-a4ec-4a95-b731-a8ac96e36c96",
      "name": "GTV-1",
      "color": "#00ff78",
      "description": "Voxel-level segmentation of the primary gross tumor volume; contoured slice-by-slice by a radiation oncologist; used for radiomics feature extraction and volumetric analysis"
    },
    {
      "id": "b8e8c9a6-7bec-40e4-b00c-1e83a8e43ddb",
      "name": "Left Lung",
      "color": "#4040ff",
      "description": "Full segmentation of the left lung including parenchyma and airways; used for lung volume calculation and dose-volume histogram analysis in radiotherapy planning"
    },
    {
      "id": "e80f8c0d-0e15-4ec8-9eb8-b0ed1528ccec",
      "name": "Right Lung",
      "color": "#005500",
      "description": "Full segmentation of the right lung; the larger of the two lungs with three lobes; used for volumetric and dosimetric analysis in radiotherapy"
    },
    {
      "id": "8a4bc5b8-8f9d-4f82-a2ae-7382ec455bfe",
      "name": "Spinal Cord",
      "color": "#ffc060",
      "description": "Precise voxel-level delineation of the spinal cord canal; critical structure in thoracic radiotherapy planning with strict maximum dose constraints to prevent myelopathy"
    }
  ],
  "preset_name": "Lungs CT"
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
- **ROI drawing tools** — Each `roi_categories` entry may set `drawing_tool`. Selecting that category in the ROI tab activates the configured tool. Changing a category's drawing tool after annotation removes existing ROIs for that category.
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

- `ConfigurationScreen.py` — Label configuration UI
- `PresetStorage.py` — Save/load presets from the extension `presets/` folder
- `AnnotationModel.py` — `LabelConfig` and `LabelDefinition` schema
- `LabelColors.py` — Default color palette for manual label creation
