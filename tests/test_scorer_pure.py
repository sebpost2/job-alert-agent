"""Pure-logic tests for the scorer: regex pre-filter and prompt assembly.

These exercise the cheap path that runs before any Groq call, so we never
need to mock the LLM here. The slower mocked-LLM path lives in
`test_scorer_llm.py`.
"""

from __future__ import annotations

import pytest

from job_alert.i18n import MESSAGES
from job_alert.scorer import (
    _hard_skip_reason,
    _system_prompt,
)


@pytest.mark.parametrize(
    "title, expected_token",
    [
        ("Médico ocupacional", "médic"),
        ("Enfermera UCI nocturna", "enfermer"),
        ("Psicólogo clínico", "psic"),
        ("Contador Senior", "contador"),
        ("Abogado corporativo", "abogad"),
        ("Community Manager LATAM", "community manager"),
        ("Social Media Specialist", "social media"),
        ("Account Executive SaaS", "account executive"),
        ("Reclutador IT", "reclutador"),
        ("Diseñador Gráfico Senior", "diseñador gráfico"),
        ("Graphic Designer", "graphic designer"),
        ("Sales Representative", "sales"),
    ],
)
def test_hard_skip_non_it_titles(title: str, expected_token: str) -> None:
    reason = _hard_skip_reason(title)
    assert reason is not None
    assert "non-IT" in reason
    assert expected_token in reason.lower()


@pytest.mark.parametrize(
    "title",
    [
        "Staff Engineer Backend",
        "Principal Engineer Platform",
        "VP of Engineering",
        "Head of Data",
        "Director of Product",
        "Chief Technology Officer",
        "CTO Fractional",
    ],
)
def test_hard_skip_high_seniority(title: str) -> None:
    reason = _hard_skip_reason(title)
    assert reason is not None
    assert "Seniority" in reason


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "AI Product Engineer",
        "Full-Stack Software Engineer",
        "Data Platform Engineer",
        "QA Automation Engineer (Python)",
        "Backend Developer Python",
        "Junior Frontend Engineer",
        "DevOps Engineer Semi-Senior",
        "Forward Deployed Engineer Agentic Platform",
    ],
)
def test_hard_skip_passes_through_real_targets(title: str) -> None:
    """The 9 jobs from the user's pipeline must NOT be filtered cheaply."""
    assert _hard_skip_reason(title) is None


def test_hard_skip_does_not_match_salesforce() -> None:
    """`Salesforce` contains 'sales' but we must not catch it as a sales role."""
    assert _hard_skip_reason("Salesforce Developer") is None


def test_system_prompt_includes_cv_and_keywords() -> None:
    keywords = ("python", "ai", "remote")
    prompt = _system_prompt(keywords)

    assert "Sebastián Postigo" in prompt, "CV summary must be injected"
    for kw in keywords:
        assert kw in prompt, f"keyword {kw} must appear in the prompt"
    assert MESSAGES["en"]["json_shape_hint"].format() in prompt
    assert '"fit_score"' in prompt and '"verdict"' in prompt


def test_system_prompt_hard_skips_explicit_years_requirement() -> None:
    """Lock down the post-audit fix: Benchling (7+ years) was scored as fit
    before this rule was added. The LLM must be told to descard regardless
    of stack match when 5+ years is a hard requirement, but NOT when it's
    just "preferred"/"nice to have"."""
    prompt = _system_prompt(("python",))
    assert "5+ años de experiencia" in prompt or "5+ years" in prompt
    # The "preferred / nice to have" carve-out must be present so the LLM
    # doesn't over-skip jobs that mention experience aspirationally.
    assert "preferred" in prompt.lower() or "nice to have" in prompt.lower()


@pytest.mark.parametrize(
    "language_token",
    [
        "árabe",
        "arabic",
        "mandarín",
        "mandarin",
        "alemán",
        "german",
        "francés",
        "french",
        "portugués",
        "portuguese",
        "japonés",
        "japanese",
    ],
)
def test_system_prompt_hard_skips_specific_non_es_en_languages(
    language_token: str,
) -> None:
    """Lock down the post-audit fix: Cohere (Arabic required) was scored as
    fit before this rule. The prompt must enumerate enough examples that the
    model learns the pattern instead of trying to interpret one phrase."""
    prompt = _system_prompt(("python",)).lower()
    assert language_token.lower() in prompt
