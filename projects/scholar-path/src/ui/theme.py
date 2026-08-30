"""Interface-only appearance controls for the ScholarPath Streamlit application."""

from enum import StrEnum
from typing import Final

import streamlit as st

THEME_TOGGLE_KEY: Final = "scholarpath_light_mode"
THEME_TOGGLE_LABEL: Final = "Light mode"


class ScholarPathTheme(StrEnum):
    """The two presentation themes supported by the single Streamlit application."""

    DARK = "dark"
    LIGHT = "light"


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

LIGHT_THEME_STYLES: Final = """
<style data-scholarpath-theme="light">
[data-testid="stAppViewContainer"] {
    color-scheme: light;
    --background-color: #f5f7fb;
    --secondary-background-color: #ffffff;
    --text-color: #172033;
    --border-color: rgba(45, 94, 170, 0.24);
    background-color: #f5f7fb;
    background-image: radial-gradient(
        circle at 92% 2%,
        rgba(62, 123, 224, 0.13),
        transparent 28rem
    );
    color: var(--text-color);
}
[data-testid="stAppViewContainer"] [data-testid="stHeader"] {
    background-color: rgba(245, 247, 251, 0.90);
}
[data-testid="stAppViewContainer"] .st-key-scholarpath_hero {
    background: linear-gradient(
        135deg,
        rgba(45, 110, 240, 0.13),
        rgba(34, 197, 160, 0.10)
    );
    border-color: rgba(45, 94, 170, 0.27);
    box-shadow: 0 0.75rem 2.25rem rgba(45, 63, 94, 0.12);
}
[data-testid="stAppViewContainer"] [data-testid="stExpander"],
[data-testid="stAppViewContainer"] [data-testid="stForm"],
[data-testid="stAppViewContainer"] [data-testid="stStatusWidget"] {
    background-color: rgba(255, 255, 255, 0.78);
    border-color: var(--border-color);
}
[data-testid="stAppViewContainer"] [data-testid="stMetric"] {
    background-color: rgba(45, 110, 240, 0.07);
}
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
