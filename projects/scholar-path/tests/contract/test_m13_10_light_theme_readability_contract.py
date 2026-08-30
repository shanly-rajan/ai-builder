"""Repository contract for the bounded M13.10 light-theme readability repair."""

from pathlib import Path

from scholarpath.ui.theme import DARK_THEME_STYLES, LIGHT_THEME_PALETTE, LIGHT_THEME_STYLES

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_light_theme_repair_is_archived_and_documented() -> None:
    prompt = (PROJECT_ROOT / "docs" / "prompts" / "m13-10-light-theme-readability.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "In light mode, readability should not be compromised like attached" in prompt
    assert "M13.10 completes the light-theme compatibility layer" in readme
    assert "## M13.10 light-theme readability boundary" in architecture
    assert "WCAG contrast contracts" in architecture


def test_light_theme_is_explicit_and_dark_theme_remains_separate() -> None:
    assert 'data-scholarpath-theme="light"' in LIGHT_THEME_STYLES
    assert 'data-scholarpath-theme="dark"' in DARK_THEME_STYLES
    assert LIGHT_THEME_PALETTE.warning_background in LIGHT_THEME_STYLES
    assert LIGHT_THEME_PALETTE.warning_background not in DARK_THEME_STYLES
    assert 'data-testid="stTextAreaRootElement"' in LIGHT_THEME_STYLES
    assert 'data-testid="stAlertContentWarning"' in LIGHT_THEME_STYLES


def test_streamlit_selector_contract_is_protected_by_exact_dependency_pin() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"streamlit==1.62.0"' in pyproject
