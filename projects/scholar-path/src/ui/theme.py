"""Interface-only appearance controls for the ScholarPath Streamlit application."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import streamlit as st

THEME_TOGGLE_KEY: Final = "scholarpath_light_mode"
THEME_TOGGLE_LABEL: Final = "Light mode"


class ScholarPathTheme(StrEnum):
    """The two presentation themes supported by the single Streamlit application."""

    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True, slots=True)
class LightThemePalette:
    """Fixed light-theme colors whose important text pairs meet WCAG AA contrast."""

    page_background: str
    surface: str
    subdued_surface: str
    text: str
    muted_text: str
    border: str
    focus: str
    primary: str
    on_primary: str
    link: str
    warning_background: str
    warning_text: str
    warning_border: str
    info_background: str
    info_text: str
    error_background: str
    error_text: str
    success_background: str
    success_text: str


LIGHT_THEME_PALETTE: Final = LightThemePalette(
    page_background="#f5f7fb",
    surface="#ffffff",
    subdued_surface="#eef3f8",
    text="#172033",
    muted_text="#526078",
    border="#63738b",
    focus="#2563eb",
    primary="#245ec7",
    on_primary="#ffffff",
    link="#174ea6",
    warning_background="#fff4ce",
    warning_text="#4f3a00",
    warning_border="#946200",
    info_background="#e8f2ff",
    info_text="#15345b",
    error_background="#fdebec",
    error_text="#7a1f2b",
    success_background="#e9f7ef",
    success_text="#14532d",
)


DARK_THEME_STYLES: Final = """
<style data-scholarpath-theme="dark">
[data-testid="stAppViewContainer"] {
    color-scheme: dark;
    --background-color: #0e1117;
    --secondary-background-color: #171d27;
    --text-color: #f5f7fb;
    --border-color: rgba(111, 158, 238, 0.28);
    background-color: #0e1117;
    background-image: radial-gradient(
        circle at 92% 2%,
        rgba(70, 130, 255, 0.10),
        transparent 28rem
    );
    color: var(--text-color);
}
[data-testid="stAppViewContainer"] [data-testid="stHeader"] {
    background-color: rgba(14, 17, 23, 0.88);
}
[data-testid="stAppViewContainer"] .st-key-scholarpath_hero {
    background: linear-gradient(
        135deg,
        rgba(45, 110, 240, 0.18),
        rgba(34, 197, 160, 0.08)
    );
    border-color: rgba(91, 153, 255, 0.32);
    box-shadow: 0 0.75rem 2.25rem rgba(8, 15, 31, 0.12);
}
[data-testid="stAppViewContainer"] [data-testid="stExpander"],
[data-testid="stAppViewContainer"] [data-testid="stForm"],
[data-testid="stAppViewContainer"] [data-testid="stStatusWidget"] {
    background-color: rgba(23, 29, 39, 0.48);
    border-color: var(--border-color);
}
</style>
"""

LIGHT_THEME_STYLES: Final = f"""
<style data-scholarpath-theme="light">
[data-testid="stAppViewContainer"] {{
    color-scheme: light;
    --background-color: {LIGHT_THEME_PALETTE.page_background};
    --secondary-background-color: {LIGHT_THEME_PALETTE.surface};
    --text-color: {LIGHT_THEME_PALETTE.text};
    --border-color: {LIGHT_THEME_PALETTE.border};
    --scholarpath-page: {LIGHT_THEME_PALETTE.page_background};
    --scholarpath-surface: {LIGHT_THEME_PALETTE.surface};
    --scholarpath-subdued-surface: {LIGHT_THEME_PALETTE.subdued_surface};
    --scholarpath-text: {LIGHT_THEME_PALETTE.text};
    --scholarpath-muted-text: {LIGHT_THEME_PALETTE.muted_text};
    --scholarpath-border: {LIGHT_THEME_PALETTE.border};
    --scholarpath-focus: {LIGHT_THEME_PALETTE.focus};
    --scholarpath-primary: {LIGHT_THEME_PALETTE.primary};
    --scholarpath-on-primary: {LIGHT_THEME_PALETTE.on_primary};
    --scholarpath-link: {LIGHT_THEME_PALETTE.link};
    background-color: var(--scholarpath-page);
    background-image: radial-gradient(
        circle at 92% 2%,
        rgba(62, 123, 224, 0.13),
        transparent 28rem
    );
    color: var(--scholarpath-text);
}}
[data-testid="stAppViewContainer"] [data-testid="stHeader"] {{
    background-color: rgba(245, 247, 251, 0.94);
}}
[data-testid="stAppViewContainer"] .st-key-scholarpath_hero {{
    background: linear-gradient(
        135deg,
        rgba(45, 110, 240, 0.13),
        rgba(34, 197, 160, 0.10)
    );
    border-color: rgba(45, 94, 170, 0.27);
    box-shadow: 0 0.75rem 2.25rem rgba(45, 63, 94, 0.12);
}}
[data-testid="stAppViewContainer"] :is(h1, h2, h3, h4, h5, h6),
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"],
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] * {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] a {{
    color: var(--scholarpath-link) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"],
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] * {{
    color: var(--scholarpath-muted-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"],
[data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] * {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stExpander"],
[data-testid="stAppViewContainer"] [data-testid="stForm"],
[data-testid="stAppViewContainer"] [data-testid="stStatusWidget"] {{
    background-color: var(--scholarpath-surface) !important;
    border-color: var(--scholarpath-border) !important;
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stExpander"] details,
[data-testid="stAppViewContainer"] [data-testid="stExpanderDetails"] {{
    background-color: var(--scholarpath-surface) !important;
    border-color: var(--scholarpath-border) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stExpander"] summary,
[data-testid="stAppViewContainer"] [data-testid="stExpander"] summary * {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stExpander"] summary:hover {{
    background-color: var(--scholarpath-subdued-surface) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stMetric"] {{
    background-color: rgba(45, 110, 240, 0.07);
}}
[data-testid="stAppViewContainer"] [data-testid="stMetric"] * {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stTextInputRootElement"],
[data-testid="stAppViewContainer"] [data-testid="stTextAreaRootElement"],
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] div:has(> input),
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] div:has(
    > [data-testid="stMultiSelectTagsContainer"]
),
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
    background-color: var(--scholarpath-surface) !important;
    border-color: var(--scholarpath-border) !important;
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stAppViewContainer"] [data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] div:has(> input):focus-within,
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] div:has(
    > [data-testid="stMultiSelectTagsContainer"]
):focus-within {{
    border-color: var(--scholarpath-focus) !important;
    box-shadow: 0 0 0 1px var(--scholarpath-focus);
}}
[data-testid="stAppViewContainer"] [data-testid="stTextInputField"],
[data-testid="stAppViewContainer"] [data-testid="stTextInputRootElement"] input,
[data-testid="stAppViewContainer"] [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] input,
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] input {{
    background-color: transparent !important;
    caret-color: var(--scholarpath-text) !important;
    color: var(--scholarpath-text) !important;
    -webkit-text-fill-color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stTextInputField"]::placeholder,
[data-testid="stAppViewContainer"] [data-testid="stTextInputRootElement"] input::placeholder,
[data-testid="stAppViewContainer"] [data-testid="stTextAreaRootElement"] textarea::placeholder,
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] input::placeholder,
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] input::placeholder {{
    color: var(--scholarpath-muted-text) !important;
    opacity: 1;
    -webkit-text-fill-color: var(--scholarpath-muted-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stTextInputRootElement"] input:disabled,
[data-testid="stAppViewContainer"] [data-testid="stTextAreaRootElement"] textarea:disabled {{
    background-color: var(--scholarpath-subdued-surface) !important;
    color: var(--scholarpath-muted-text) !important;
    -webkit-text-fill-color: var(--scholarpath-muted-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] button,
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] button {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [data-tag] {{
    background-color: var(--scholarpath-primary) !important;
    color: var(--scholarpath-on-primary) !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stCheckbox"] [data-testid="stWidgetLabel"],
[data-testid="stAppViewContainer"] [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] * {{
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-secondary"],
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-tertiary"],
[data-testid="stAppViewContainer"] [data-testid="stPopoverButton"] button {{
    background-color: var(--scholarpath-surface) !important;
    border-color: var(--scholarpath-border) !important;
    color: var(--scholarpath-text) !important;
}}
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-primary"] {{
    background-color: var(--scholarpath-primary) !important;
    border-color: var(--scholarpath-primary) !important;
    color: var(--scholarpath-on-primary) !important;
}}
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-"] *,
[data-testid="stAppViewContainer"] [data-testid="stPopoverButton"] button * {{
    color: inherit !important;
}}
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-"]:focus-visible,
[data-testid="stAppViewContainer"] [data-testid="stPopoverButton"] button:focus-visible {{
    outline: 3px solid rgba(37, 99, 235, 0.35) !important;
    outline-offset: 2px;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContainer"] {{
    border: 1px solid transparent;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContainer"]:has(
    [data-testid="stAlertContentWarning"]
) {{
    background-color: {LIGHT_THEME_PALETTE.warning_background} !important;
    border-color: {LIGHT_THEME_PALETTE.warning_border} !important;
    color: {LIGHT_THEME_PALETTE.warning_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContentWarning"],
[data-testid="stAppViewContainer"] [data-testid="stAlertContentWarning"] * {{
    color: {LIGHT_THEME_PALETTE.warning_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContainer"]:has(
    [data-testid="stAlertContentInfo"]
) {{
    background-color: {LIGHT_THEME_PALETTE.info_background} !important;
    border-color: {LIGHT_THEME_PALETTE.info_text} !important;
    color: {LIGHT_THEME_PALETTE.info_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContentInfo"],
[data-testid="stAppViewContainer"] [data-testid="stAlertContentInfo"] * {{
    color: {LIGHT_THEME_PALETTE.info_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContainer"]:has(
    [data-testid="stAlertContentError"]
) {{
    background-color: {LIGHT_THEME_PALETTE.error_background} !important;
    border-color: {LIGHT_THEME_PALETTE.error_text} !important;
    color: {LIGHT_THEME_PALETTE.error_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContentError"],
[data-testid="stAppViewContainer"] [data-testid="stAlertContentError"] * {{
    color: {LIGHT_THEME_PALETTE.error_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContainer"]:has(
    [data-testid="stAlertContentSuccess"]
) {{
    background-color: {LIGHT_THEME_PALETTE.success_background} !important;
    border-color: {LIGHT_THEME_PALETTE.success_text} !important;
    color: {LIGHT_THEME_PALETTE.success_text} !important;
}}
[data-testid="stAppViewContainer"] [data-testid="stAlertContentSuccess"],
[data-testid="stAppViewContainer"] [data-testid="stAlertContentSuccess"] * {{
    color: {LIGHT_THEME_PALETTE.success_text} !important;
}}
[data-testid="stSelectboxVirtualDropdown"],
[data-testid="stMultiSelectDropdown"],
[data-testid="stPopoverBody"] {{
    background-color: {LIGHT_THEME_PALETTE.surface} !important;
    border-color: {LIGHT_THEME_PALETTE.border} !important;
    color: {LIGHT_THEME_PALETTE.text} !important;
}}
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"],
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"] * {{
    color: {LIGHT_THEME_PALETTE.text} !important;
}}
[data-testid="stSelectboxVirtualDropdown"] [role="option"],
[data-testid="stMultiSelectDropdown"] [role="option"] {{
    color: {LIGHT_THEME_PALETTE.text} !important;
}}
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:is(:hover, [data-focused]),
[data-testid="stMultiSelectDropdown"] [role="option"]:is(:hover, [data-focused]) {{
    background-color: {LIGHT_THEME_PALETTE.info_background} !important;
}}
</style>
"""


def theme_styles(theme: ScholarPathTheme) -> str:
    """Return one fixed CSS palette selected only from the typed UI theme."""
    if theme is ScholarPathTheme.LIGHT:
        return LIGHT_THEME_STYLES
    return DARK_THEME_STYLES


def render_appearance_controls() -> ScholarPathTheme:
    """Render an accessible slider toggle whose state is scoped to this UI session."""
    _, control_column = st.columns((5, 1), vertical_alignment="center")
    with control_column:
        light_mode = st.toggle(
            THEME_TOGGLE_LABEL,
            value=False,
            key=THEME_TOGGLE_KEY,
            help="Switch between ScholarPath's dark and light appearance.",
        )
    return ScholarPathTheme.LIGHT if light_mode else ScholarPathTheme.DARK


def inject_theme_styles(theme: ScholarPathTheme) -> None:
    """Apply the selected fixed palette without storing application or graph state."""
    st.markdown(theme_styles(theme), unsafe_allow_html=True)
