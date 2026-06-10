"""Load and save label-configuration presets from the extension presets folder."""

import json
import os
import re

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PRESETS_DIR_NAME = "presets"
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESOLVED_PRESETS_DIR = None


def _qt_line_text(line_edit):
    """Read text from a QLineEdit in both PythonQt (.text) and PyQt (.text())."""
    text = line_edit.text
    return text() if callable(text) else (text or "")


def _candidate_preset_dirs():
    dirs = [os.path.join(MODULE_DIR, PRESETS_DIR_NAME)]
    try:
        import slicer

        dirs.append(
            os.path.join(slicer.app.slicerUserDataPath(), "AnnotationPanel", PRESETS_DIR_NAME)
        )
    except Exception:
        pass
    dirs.append(os.path.join(os.path.expanduser("~"), ".AnnotationPanel", PRESETS_DIR_NAME))
    unique = []
    for path in dirs:
        normalized = os.path.normpath(path)
        if normalized not in unique:
            unique.append(normalized)
    return unique


def _is_dir_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def get_presets_dir():
    """Return a writable presets directory, cached after first resolution."""
    global _RESOLVED_PRESETS_DIR
    if _RESOLVED_PRESETS_DIR and os.path.isdir(_RESOLVED_PRESETS_DIR):
        return _RESOLVED_PRESETS_DIR

    for path in _candidate_preset_dirs():
        if _is_dir_writable(path):
            _RESOLVED_PRESETS_DIR = path
            return path

    fallback = _candidate_preset_dirs()[-1]
    os.makedirs(fallback, exist_ok=True)
    _RESOLVED_PRESETS_DIR = fallback
    return fallback


def normalize_preset_name(name):
    return (name or "").strip()


def preset_name_key(name):
    return normalize_preset_name(name).casefold()


def sanitize_preset_filename(name):
    """Convert a display name to a safe JSON filename stem."""
    normalized = normalize_preset_name(name)
    if not normalized:
        raise ValueError("Preset name is required.")
    safe = _INVALID_FILENAME_CHARS.sub("_", normalized).strip(". ")
    if not safe:
        raise ValueError("Preset name is invalid.")
    return safe


def preset_filepath(name):
    return os.path.join(get_presets_dir(), f"{sanitize_preset_filename(name)}.json")


def list_preset_names():
    """Return sorted preset names discovered in the presets folder."""
    presets_dir = get_presets_dir()
    names = []
    try:
        filenames = os.listdir(presets_dir)
    except OSError:
        return names
    for filename in filenames:
        if filename.lower().endswith(".json"):
            names.append(os.path.splitext(filename)[0])
    return sorted(names, key=str.casefold)


def find_preset_name(name):
    """Return the on-disk preset name matching ``name`` case-insensitively."""
    target = preset_name_key(name)
    if not target:
        return None
    for existing in list_preset_names():
        if preset_name_key(existing) == target:
            return existing
    return None


def is_preset_name_taken(name, exclude_name=None):
    """True if another preset already uses this name."""
    key = preset_name_key(name)
    if not key:
        return False
    exclude_key = preset_name_key(exclude_name) if exclude_name else None
    for existing in list_preset_names():
        existing_key = preset_name_key(existing)
        if exclude_key and existing_key == exclude_key:
            continue
        if existing_key == key:
            return True
    return False


def save_preset(name, config_dict):
    """Write a preset JSON file. Raises ValueError on invalid or duplicate names."""
    normalized = normalize_preset_name(name)
    if not normalized:
        raise ValueError("Preset name is required.")
    if is_preset_name_taken(normalized):
        raise ValueError(f'A preset named "{normalized}" already exists.')

    path = preset_filepath(normalized)
    payload = dict(config_dict)
    payload["preset_name"] = normalized
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_preset(name):
    """Load preset JSON by display name."""
    resolved = find_preset_name(name) or sanitize_preset_filename(name)
    path = os.path.join(get_presets_dir(), f"{resolved}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f'Preset "{name}" not found.')
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
