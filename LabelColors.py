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
    "#006400",
    "#8B008B",
    "#FF1493",
    "#00CED1",
    "#FFD700",
    "#708090",
    "#2F4F4F",
    "#CD853F",
    "#4682B4",
    "#D2691E",
    "#5F9EA0",
    "#6495ED",
    "#DA70D6",
    "#32CD32",
    "#FF6347",
    "#40E0D0",
    "#EE82EE",
    "#F0E68C",
    "#DDA0DD",
    "#98FB98",
    "#F08080",
    "#87CEEB",
    "#DEB887",
    "#00FA9A",
    "#1E90FF",
    "#ADFF2F",
    "#FF4500",
    "#6A5ACD",
    "#20B2AA",
    "#B22222",
    "#228B22",
]

DEFAULT_LABEL_COLOR = LABEL_COLOR_PALETTE[0]

# Deterministic palette rotations so each category starts with a different color.
_CATEGORY_ROTATION_OFFSETS = {
    "classification": 0,
    "roi": 18,
    "segmentation": 36,
}


def get_category_palette(category_key):
    """Return a rotated copy of the base palette for the given category."""
    palette = list(LABEL_COLOR_PALETTE)
    if not palette:
        return palette
    offset = _CATEGORY_ROTATION_OFFSETS.get(category_key, 0) % len(palette)
    if offset:
        palette = palette[offset:] + palette[:offset]
    return palette


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


def _hex_to_rgb_channels(color):
    """Return normalized 0-255 RGB channels, or None if invalid."""
    normalized = normalize_hex_color(color)
    if not normalized:
        return None
    return (
        int(normalized[1:3], 16),
        int(normalized[3:5], 16),
        int(normalized[5:7], 16),
    )


def relative_luminance(color):
    """WCAG relative luminance for a hex color (0.0–1.0)."""
    channels = _hex_to_rgb_channels(color)
    if channels is None:
        return 0.0

    def linearize(value):
        channel = value / 255.0
        if channel <= 0.03928:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(value) for value in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_text_color(background_color, light="#ffffff", dark="#1a1a1a"):
    """Return a readable text color for the given background hex color."""
    normalized = normalize_hex_color(background_color)
    if not normalized:
        normalized = normalize_hex_color(DEFAULT_LABEL_COLOR)

    # Heuristic used by common color libraries for light/dark text on arbitrary backgrounds.
    if (relative_luminance(normalized) + 0.05) ** 2 > 0.15:
        return dark
    return light


def darken_hex_color(color, factor=0.82):
    """Return a slightly darkened copy of a hex color for borders and accents."""
    channels = _hex_to_rgb_channels(color)
    if channels is None:
        return normalize_hex_color(DEFAULT_LABEL_COLOR) or DEFAULT_LABEL_COLOR
    red, green, blue = channels
    scale = max(0.0, min(1.0, factor))
    return (
        f"#{int(red * scale):02x}{int(green * scale):02x}{int(blue * scale):02x}"
    )


def classification_label_button_stylesheet(label_color):
    """Build stylesheet for a checkable classification label button."""
    color = normalize_hex_color(label_color) or normalize_hex_color(DEFAULT_LABEL_COLOR)
    text_color = contrast_text_color(color)
    border_color = darken_hex_color(color)
    return (
        f"QPushButton {{ font-size: 11px; padding: 2px 8px; border: 1px solid {color}; "
        f"border-radius: 3px; }}"
        f"QPushButton:checked {{ background-color: {color}; color: {text_color}; "
        f"border-color: {border_color}; }}"
    )


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
