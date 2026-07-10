"""Tests for the EN/ES i18n layer.

`Strings` (a `TypedDict`) already gives compile-time key-parity via mypy; these
tests add the runtime guarantees: identical keys at runtime and that both
language variants of the digest and the system prompt render without errors.
"""

from __future__ import annotations

import pytest

from job_alert.i18n import EN, ES, MESSAGES, Lang, normalize_lang
from job_alert.scorer import _system_prompt
from job_alert.telegram_digest import _format_message

LANGS: tuple[Lang, ...] = ("es", "en")


def test_en_es_have_identical_keys() -> None:
    assert EN.keys() == ES.keys()


@pytest.mark.parametrize(
    "raw, expected",
    [("en", "en"), ("EN", "en"), (" en ", "en"), ("es", "es"), ("fr", "es"), ("", "es")],
)
def test_normalize_lang(raw: str, expected: Lang) -> None:
    assert normalize_lang(raw) == expected


@pytest.mark.parametrize("lang", LANGS)
def test_digest_renders_both_languages(lang: Lang) -> None:
    empty = _format_message([], lang)
    assert MESSAGES[lang]["no_fits"] == empty

    jobs = [
        {
            "title": "Python Engineer",
            "company": "Acme",
            "location": "Remote",
            "fit_score": 90,
            "reason": "Stack matches",
            "source": "getonboard",
            "url": "https://example.com/job/1",
        }
    ]
    msg = _format_message(jobs, lang)
    assert MESSAGES[lang]["view_offer"] in msg
    assert "top 1 fit(s)" in msg


@pytest.mark.parametrize("lang", LANGS)
def test_system_prompt_renders_both_languages(lang: Lang) -> None:
    prompt = _system_prompt(("python", "ai"), lang)
    # CV, keywords and the JSON schema must survive templating in both langs.
    assert "Sebastián Postigo" in prompt
    assert "python" in prompt
    assert '"fit_score"' in prompt


def test_english_digest_uses_english_copy() -> None:
    assert "No new fits today" in _format_message([], "en")
