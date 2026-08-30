"""Pure contracts for the opt-in ScholarPath demonstration profile."""

from scholarpath.ui.app import (
    DEMO_PROFILE_RESEARCH_STATEMENT,
    DEMO_PROFILE_RESEARCH_TOPICS,
    demo_profile_widget_values,
)


def test_demo_profile_widget_values_match_the_curated_reviewer_example() -> None:
    values = demo_profile_widget_values()

    assert values == {
        "profile_research_statement": DEMO_PROFILE_RESEARCH_STATEMENT,
        "profile_research_topics": DEMO_PROFILE_RESEARCH_TOPICS,
        "profile_preferred_regions": "",
        "profile_study_modes": [],
        "profile_research_orientation": "No preference",
        "profile_methodological_interests": "",
        "profile_exclusions": "",
    }


def test_demo_profile_widget_values_returns_fresh_mutable_widget_data() -> None:
    first = demo_profile_widget_values()
    second = demo_profile_widget_values()

    assert first is not second
    assert first["profile_study_modes"] is not second["profile_study_modes"]
