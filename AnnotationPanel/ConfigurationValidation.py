"""Validation rules for continuing from the label configuration screen."""

CONFIG_SOURCE_MANUAL = "manual"
CONFIG_SOURCE_PRESET = "preset"
CONFIG_SOURCE_IMPORTED = "imported"

MESSAGE_SAVE_PRESET = "Please save your configuration as a preset before continuing."
MESSAGE_IMPORTED_SAVE_PRESET = (
    "Imported configuration has not been saved as a preset.\n"
    "Please save it before continuing."
)


def configuration_continue_blocked_reason(source, dirty):
    """Return a warning message when Continue should be blocked, else None."""
    if source == CONFIG_SOURCE_PRESET and not dirty:
        return None
    if source == CONFIG_SOURCE_IMPORTED:
        return MESSAGE_IMPORTED_SAVE_PRESET
    return MESSAGE_SAVE_PRESET
