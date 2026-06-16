# Annotation Panel — Features Overview

**Annotation Panel** is a 3D Slicer extension that brings classification, ROI, and segmentation annotation into one preset-driven workflow with portable export packages.

Browse the features below for a short summary of each capability. Select any feature to read the full description, use cases, and screenshots in **[FEATURES.md](./FEATURES.md)**.

---

## Core Features

### Configuration and setup

**[1. Unified Annotation Workspace](./FEATURES.md#unified-annotation-workspace)**  
Work in one panel with Classification, ROI, and Segmentation tabs that share the same labels and export path.

**[2. Label Configuration Screen](./FEATURES.md#label-configuration-screen)**  
Define classification labels, ROI categories (each with a drawing tool), and segment labels before you start annotating.

**[3. Preset Management](./FEATURES.md#preset-management)**  
Save, load, delete, and import label configurations so you and your team reuse the same protocol every session.

### Annotation

**[4. Classification Annotation](./FEATURES.md#classification-annotation)**  
Assign slice-level labels and capture Axial, Coronal, and Sagittal positions in a single Add action.

**[5. ROI Annotation](./FEATURES.md#roi-annotation)**  
Draw bounding boxes, polygon and freehand contours, and linear measurements — each ROI category uses the tool you configured for it.

**[6. ROI Session Management](./FEATURES.md#roi-session-management)**  
Hide or show individual ROIs, move and extend shapes, jump slice views to a selected ROI, and manage a full ROI list in one table.

**[7. Segmentation Annotation](./FEATURES.md#segmentation-annotation)**  
Paint, threshold, erase, and refine voxel-level segmentations using a focused set of Segment Editor tools built into the panel.

### Flexibility

**[8. Volume-Optional Annotation](./FEATURES.md#volume-optional-annotation)**  
Configure labels and begin annotating before imaging data is loaded; add the scan later when it arrives.

### Sharing and continuity

**[9. Formal Export Package](./FEATURES.md#formal-export-package)**  
Export a complete folder with annotation metadata and segmentation volumes ready to share or use in downstream tools.

**[10. Import and Resume](./FEATURES.md#import-and-resume)**  
Reopen a previous export folder and continue editing classifications, ROIs, and segmentations where you left off.

**[11. Configuration Conflict Resolution](./FEATURES.md#configuration-conflict-resolution)**  
When an imported package uses different labels than your current session, choose whether to adopt the imported schema or keep your own.

**[12. Edit Configuration with Reconciliation](./FEATURES.md#edit-configuration-with-reconciliation)**  
Return to the label setup screen mid-project; renames and color changes update existing annotations, with clear warnings when labels are removed.

**[13. ROI-Only Partial Export](./FEATURES.md#roi-only-partial-export)**  
Export just your ROI list as JSON when you only need markup geometry, without the full annotation package.

---

## Additional reference

**[User Workflows](./FEATURES.md#user-workflows)**  
Step-by-step guides for first-time setup, preset reuse, annotating with or without a scan, export, import, and team preset sharing.

**[Annotation Capabilities](./FEATURES.md#annotation-capabilities)**  
Detailed tables of what you can do in each tab — classification metadata, ROI tool types, and segmentation effects.

**[Data Management](./FEATURES.md#data-management-features)**  
How presets are stored, when you must save before continuing, and what happens to annotations when labels change.

**[Supported Output Formats](./FEATURES.md#supported-output-formats)**  
Which files an export produces and when to use each format.

**[What Makes This Different](./FEATURES.md#what-makes-this-different)**  
A concise comparison of capabilities that distinguish Annotation Panel from using Slicer tools separately.

---

## Workflow at a glance

```text
Open Slicer → Annotation Panel
    ↓
Configure labels → Save or load a preset → Confirm & Start
    ↓
Classify | Draw ROIs | Segment
    ↓
Export → share folder → Import on another machine to continue
```

---

## Further reading

| Document | Content |
|----------|---------|
| [FEATURES.md](./FEATURES.md) | Full feature descriptions, workflows, and reference material |
| [README.md](./README.md) | Installation and project structure |
| [docs/export-format.md](./docs/export-format.md) | Export folder layout and JSON schema |
| [docs/label-configuration-import.md](./docs/label-configuration-import.md) | Preset JSON format |
| [docs/preset.json](./docs/preset.json) | Example spleen CT preset |
