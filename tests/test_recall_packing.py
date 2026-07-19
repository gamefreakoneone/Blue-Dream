import datetime as dt
import math

from Blue_dream_agents.prompt_budget import RecallCandidate, pack_recall
from Blue_dream_agents.timezone_utils import LOCAL_TZ


NOW = dt.datetime(2026, 7, 18, 12, tzinfo=LOCAL_TZ)


def candidate(
    identifier,
    *,
    days_old=0,
    similarity=0.8,
    importance=0.5,
    pinned=False,
    memory_type="event",
    text="four chars of memory",
):
    return RecallCandidate(
        id=identifier,
        type=memory_type,
        text=text,
        timestamp=NOW - dt.timedelta(days=days_old),
        similarity=similarity,
        importance=importance,
        pinned=pinned,
    )


def test_score_math_matches_relevance_recency_importance_formula():
    pack = pack_recall(
        [candidate("event", days_old=14, similarity=0.8, importance=0.5)],
        token_budget=100,
        half_life_days=14,
        now=NOW,
    )
    assert pack.included[0].final_score == pytest_approx(
        0.8 * math.exp(-1.0) * 1.5
    )


def pytest_approx(value):
    import pytest

    return pytest.approx(value, rel=1e-10)


def test_stale_high_similarity_loses_to_fresh_moderate_similarity_regression():
    pack = pack_recall(
        [
            candidate("stale-exact", days_old=60, similarity=0.99, importance=0.5),
            candidate("fresh-related", days_old=0, similarity=0.62, importance=0.5),
        ],
        token_budget=100,
        half_life_days=14,
        now=NOW,
    )
    assert [item.id for item in pack.included] == ["fresh-related", "stale-exact"]


def test_pinned_facts_then_events_are_guaranteed_even_when_over_budget():
    pack = pack_recall(
        [
            candidate("ordinary", text="ordinary evidence", similarity=1.0),
            candidate("event-pin", pinned=True, text="event pinned far beyond budget"),
            candidate(
                "fact-pin",
                pinned=True,
                memory_type="fact",
                text="fact pinned far beyond budget",
            ),
        ],
        token_budget=1,
        half_life_days=14,
        now=NOW,
    )
    assert [item.id for item in pack.included] == ["fact-pin", "event-pin"]
    assert pack.used_tokens > 1
    assert pack.excluded_count == 1


def test_budget_excludes_whole_unpinned_items_without_truncation():
    first = candidate("first", text="12345678", similarity=0.9)
    second = candidate("second", text="abcdefgh", similarity=0.8)
    pack = pack_recall(
        [second, first], token_budget=3, half_life_days=14, now=NOW
    )
    assert [item.id for item in pack.included] == ["first"]
    assert pack.included[0].text == "12345678"
    assert pack.excluded_count == 1


def test_equal_scores_have_deterministic_timestamp_then_id_order():
    older = candidate("older", days_old=1)
    alpha = candidate("alpha")
    beta = candidate("beta")
    pack = pack_recall(
        [beta, older, alpha], token_budget=100, half_life_days=10**9, now=NOW
    )
    assert [item.id for item in pack.included] == ["alpha", "beta", "older"]


def test_empty_candidates_returns_empty_pack():
    pack = pack_recall([], token_budget=0, half_life_days=14, now=NOW)
    assert pack.included == []
    assert pack.considered_count == 0
    assert pack.excluded_count == 0
