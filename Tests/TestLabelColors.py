"""Unit tests for LabelColors contrast helpers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from LabelColors import (
    LABEL_COLOR_PALETTE,
    classification_label_button_stylesheet,
    contrast_text_color,
    darken_hex_color,
    normalize_hex_color,
    relative_luminance,
)


class TestNormalizeHexColor(unittest.TestCase):
    def test_expands_three_digit_hex(self):
        self.assertEqual(normalize_hex_color("#f00"), "#ff0000")

    def test_rejects_invalid_hex(self):
        self.assertEqual(normalize_hex_color("not-a-color"), "")


class TestContrastTextColor(unittest.TestCase):
    def test_dark_background_uses_light_text(self):
        self.assertEqual(contrast_text_color("#f44336"), "#ffffff")
        self.assertEqual(contrast_text_color("#000075"), "#ffffff")
        self.assertEqual(contrast_text_color("#006400"), "#ffffff")

    def test_light_background_uses_dark_text(self):
        self.assertEqual(contrast_text_color("#ffe119"), "#1a1a1a")
        self.assertEqual(contrast_text_color("#fffac8"), "#1a1a1a")
        self.assertEqual(contrast_text_color("#bfef45"), "#1a1a1a")

    def test_palette_colors_are_readable(self):
        light_text = "#ffffff"
        dark_text = "#1a1a1a"
        seen = set()
        for color in LABEL_COLOR_PALETTE:
            normalized = normalize_hex_color(color)
            self.assertTrue(normalized, f"Expected valid palette color: {color}")
            text_color = contrast_text_color(normalized)
            self.assertIn(text_color, (light_text, dark_text))
            seen.add(text_color)
        self.assertEqual(seen, {light_text, dark_text})

    def test_invalid_color_falls_back_to_default(self):
        self.assertIn(contrast_text_color(""), ("#ffffff", "#1a1a1a"))


class TestRelativeLuminance(unittest.TestCase):
    def test_black_is_darkest_and_white_is_brightest(self):
        self.assertLess(relative_luminance("#000000"), relative_luminance("#808080"))
        self.assertLess(relative_luminance("#808080"), relative_luminance("#ffffff"))


class TestDarkenHexColor(unittest.TestCase):
    def test_darkens_valid_color(self):
        self.assertEqual(darken_hex_color("#ffffff", factor=0.5), "#7f7f7f")

    def test_invalid_color_falls_back(self):
        self.assertTrue(darken_hex_color("invalid").startswith("#"))


class TestClassificationLabelButtonStylesheet(unittest.TestCase):
    def test_selected_state_uses_label_color_not_blue(self):
        stylesheet = classification_label_button_stylesheet("#f44336")
        self.assertIn("background-color: #f44336", stylesheet)
        self.assertNotIn("#2196F3", stylesheet)
        self.assertNotIn("#1976D2", stylesheet)

    def test_selected_state_includes_contrast_text(self):
        stylesheet = classification_label_button_stylesheet("#ffe119")
        self.assertIn("background-color: #ffe119", stylesheet)
        self.assertIn("color: #1a1a1a", stylesheet)

    def test_unselected_state_keeps_colored_border(self):
        stylesheet = classification_label_button_stylesheet("#4CAF50")
        self.assertIn("border: 1px solid #4caf50", stylesheet.lower())


if __name__ == "__main__":
    unittest.main()
