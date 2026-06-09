"""Shared label color palette and dynamic assignment helpers."""

import colorsys

# Distinct, colorblind-friendly palette used across label categories.
LABEL_COLOR_PALETTE = [
    "#4CAF50",
    "#f44336",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#ffe119",
    "#FF9800",
    "#8B4513",
    "#808080",
    "#e6194b",
    "#3cb44b",
    "#f032e6",
    "#469990",
    "#9A6324",
    "#800000",
    "#000075",
    "#bfef45",
    "#fabed4",
    "#dcbeff",
    "#fffac8",
    "#aaffc3",
    "#ffd8b1",
    "#a9a9a9",
]

DEFAULT_LABEL_COLOR = LABEL_COLOR_PALETTE[0]


def normalize_hex_color(color):
    """Normalize a hex color string for consistent comparison."""
    if not color:
        return ""
    text = str(color).strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return ""
    try:
        int(text, 16)
    except ValueError:
        return ""
    return f"#{text.lower()}"


def _generated_distinct_color(index):
    hue = (index * 0.618033988749895) % 1.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.5, 0.65)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


def next_available_color(used_colors, palette=None):
    """Pick the first palette color not already used in this label category."""
    palette = palette or LABEL_COLOR_PALETTE
    used = {
        normalized
        for color in used_colors
        if (normalized := normalize_hex_color(color))
    }

    for color in palette:
        normalized = normalize_hex_color(color)
        if normalized and normalized not in used:
            return normalized

    index = 0
    while index < 256:
        candidate = normalize_hex_color(_generated_distinct_color(len(used) + index))
        if candidate and candidate not in used:
            return candidate
        index += 1

    return normalize_hex_color(DEFAULT_LABEL_COLOR) or "#4caf50"
