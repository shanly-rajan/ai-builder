"""Repository contracts for the M11 Streamlit Candidate interface."""

import ast
import tomllib
from pathlib import Path
from typing import cast

from scholarpath.observability import GRAPH_VERSION
from scholarpath.ui.app import STAGE_LABELS
from scholarpath.ui.controller import canonical_node_names_from_stream_part

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_STAGE_LABELS = (
    "1. Your Research Degree Profile",
    "2. Supervisor Search Progress",
    "3. Prospective Supervisors",
    "4. Verified Supervisors",
    "5. Review Supervisors",
    "6. Your Supervisor Shortlist",
)


def _session_state_keys(source: str) -> set[str]:
    """Return every literal key read from or written to ``st.session_state``."""
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript):
            owner = node.value
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "st"
                and owner.attr == "session_state"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "st"
            and owner.attr == "session_state"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def test_m11_pins_streamlit_and_provides_the_thin_application_files() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    dependencies = cast(list[str], pyproject["project"]["dependencies"])

    assert [item for item in dependencies if item.casefold().startswith("streamlit")] == [
        "streamlit==1.62.0"
    ]
    for relative_path in (
        "streamlit_app.py",
        "src/ui/app.py",
        "src/ui/service.py",
        "src/ui/controller.py",
    ):
        assert (PROJECT_ROOT / relative_path).is_file(), f"Missing M11 file: {relative_path}"

    entrypoint = (PROJECT_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "from scholarpath.ui.app import main" in entrypoint
    assert "main()" in entrypoint


def test_m11_exposes_exactly_six_canonical_candidate_facing_stages() -> None:
    assert STAGE_LABELS == EXPECTED_STAGE_LABELS
    assert len(STAGE_LABELS) == 6


def test_m11_streams_v2_updates_and_filters_raw_state_from_progress() -> None:
    service_source = (PROJECT_ROOT / "src" / "ui" / "service.py").read_text(encoding="utf-8")

    assert 'stream_mode="updates"' in service_source
    assert 'version="v2"' in service_source
    assert canonical_node_names_from_stream_part(
        {
            "type": "updates",
            "data": {
                "plan_supervisor_searches": {
                    "candidate_profile": "must not reach the presentation event"
                },
                "not_a_canonical_node": {"api_key": "must not reach the presentation event"},
            },
        }
    ) == ("plan_supervisor_searches",)
    assert (
        canonical_node_names_from_stream_part(
            {
                "type": "tasks",
                "data": {
                    "candidate_profile": "must not reach the presentation event",
                    "provider_secret": "must not reach the presentation event",
                },
            }
        )
        == ()
    )


def test_m11_session_state_retains_only_the_opaque_graph_thread_id() -> None:
    app_source = (PROJECT_ROOT / "src" / "ui" / "app.py").read_text(encoding="utf-8")

    assert _session_state_keys(app_source) == {"thread_id"}
    assert "ScholarPathState" not in app_source
    assert "checkpointer" not in app_source.casefold()
    assert "api_key" not in app_source.casefold()
    assert "secret" not in app_source.casefold()


def test_m11_prompt_readme_trace_version_and_no_outreach_boundary() -> None:
    prompt = PROJECT_ROOT / "docs" / "prompts" / "m11-streamlit-user-interface.md"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((PROJECT_ROOT / "src").rglob("*.py"))
    ).casefold()

    assert prompt.is_file()
    assert "Milestone M11" in prompt.read_text(encoding="utf-8")
    assert "streamlit run streamlit_app.py" in readme
    assert GRAPH_VERSION == "m13"
    assert "outreach" not in source
