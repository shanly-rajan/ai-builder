"""Deterministic contrast and selector contracts for the ScholarPath light theme."""

from __future__ import annotations

from dataclasses import fields

import pytest

from scholarpath.ui.theme import LIGHT_THEME_PALETTE, LIGHT_THEME_STYLES


def _linear_channel(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: str) -> float:
    assert len(color) == 7
    assert color.startswith("#")
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return (
        0.2126 * _linear_channel(red)
        + 0.7152 * _linear_channel(green)
        + 0.0722 * _linear_channel(blue)
    )


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    ("foreground", "background"),
    (
        (LIGHT_THEME_PALETTE.text, LIGHT_THEME_PALETTE.page_background),
        (LIGHT_THEME_PALETTE.text, LIGHT_THEME_PALETTE.surface),
        (LIGHT_THEME_PALETTE.muted_text, LIGHT_THEME_PALETTE.page_background),
        (LIGHT_THEME_PALETTE.muted_text, LIGHT_THEME_PALETTE.surface),
        (LIGHT_THEME_PALETTE.on_primary, LIGHT_THEME_PALETTE.primary),
        (LIGHT_THEME_PALETTE.link, LIGHT_THEME_PALETTE.page_background),
        (LIGHT_THEME_PALETTE.warning_text, LIGHT_THEME_PALETTE.warning_background),
        (LIGHT_THEME_PALETTE.info_text, LIGHT_THEME_PALETTE.info_background),
        (LIGHT_THEME_PALETTE.error_text, LIGHT_THEME_PALETTE.error_background),
        (LIGHT_THEME_PALETTE.success_text, LIGHT_THEME_PALETTE.success_background),
    ),
)
def test_light_theme_text_pairs_meet_wcag_aa(foreground: str, background: str) -> None:
    assert _contrast_ratio(foreground, background) >= 4.5


def test_light_theme_control_boundary_meets_non_text_contrast() -> None:
    assert _contrast_ratio(LIGHT_THEME_PALETTE.border, LIGHT_THEME_PALETTE.surface) >= 3


@pytest.mark.parametrize(
    "test_id",
    (
        "stWidgetLabel",
        "stCaptionContainer",
        "stMarkdownContainer",
        "stTextInputRootElement",
        "stTextInputField",
        "stTextAreaRootElement",
        "stSelectbox",
        "stSelectboxVirtualDropdown",
        "stMultiSelect",
        "stMultiSelectTagsContainer",
        "stMultiSelectDropdown",
        "stCheckbox",
        "stForm",
        "stAlertContainer",
        "stAlertContentWarning",
        "stAlertContentInfo",
        "stAlertContentError",
        "stAlertContentSuccess",
        "stExpander",
        "stExpanderDetails",
        "stStatusWidget",
        "stMetric",
        "stPopoverButton",
        "stPopoverBody",
    ),
)
def test_light_theme_explicitly_styles_streamlit_surfaces(test_id: str) -> None:
    assert f'data-testid="{test_id}"' in LIGHT_THEME_STYLES


def test_light_theme_styles_focus_placeholder_button_and_portal_states() -> None:
    assert "::placeholder" in LIGHT_THEME_STYLES
    assert ":focus-within" in LIGHT_THEME_STYLES
    assert ":focus-visible" in LIGHT_THEME_STYLES
    assert 'data-testid^="stBaseButton-secondary"' in LIGHT_THEME_STYLES
    assert 'data-testid^="stBaseButton-primary"' in LIGHT_THEME_STYLES
    assert ":has(" in LIGHT_THEME_STYLES
    assert LIGHT_THEME_STYLES.count("{") == LIGHT_THEME_STYLES.count("}")


def test_every_light_palette_color_is_emitted_into_the_stylesheet() -> None:
    for field in fields(LIGHT_THEME_PALETTE):
        assert getattr(LIGHT_THEME_PALETTE, field.name) in LIGHT_THEME_STYLES
