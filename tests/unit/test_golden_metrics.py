import pytest

from scripts.golden_metrics import summarize


def row(key, answerable, status, judge=None, hit=False):
    return {
        "gold": {
            "id": key,
            "answerable": answerable,
            "expected_behavior": "answer" if answerable else "handoff",
        },
        "status": status,
        "actual_behavior": {
            "answered": "answer",
            "insufficient_evidence": "handoff",
            "blocked": "blocked",
        }.get(status, "error"),
        "judge": judge,
        "page_hit_at_5": hit,
        "file_hit_at_5": hit,
    }


def test_empty_evaluation_is_undefined_not_perfect():
    result = summarize([])
    assert result["faithfulness"] is None
    assert result["citation_faithfulness"] is None
    assert result["answer_correctness"] is None
    assert result["answerability"]["f1"] is None


def test_answerability_counts_abstention_false_answer_and_provider_error_separately():
    result = summarize(
        [
            row("tp", True, "answered"),
            row("fn", True, "insufficient_evidence"),
            row("fp", False, "answered"),
            row("tn", False, "blocked"),
            row("failure", False, "error"),
        ]
    )
    assert result["answerability"] == {
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "tn": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "evaluated": 4,
        "technical_error_ids": ["failure"],
    }


def test_claim_support_and_cited_source_support_have_distinct_denominators():
    judgment = {
        "correctness": 0.75,
        "claims": [
            {"supported": True, "citations": [{"supported": True}, {"supported": False}]},
            {"supported": False, "citations": [{"supported": False}]},
        ],
    }
    result = summarize(
        [
            row("a", True, "answered", judgment, True),
            row("b", True, "insufficient_evidence"),
            row("c", False, "insufficient_evidence"),
        ]
    )
    assert result["recall_at_5_page_proxy"] == 0.5
    assert result["answer_correctness"] == 0.375
    assert result["faithfulness"] == 0.5
    assert result["citation_faithfulness"] == pytest.approx(1 / 3)
    assert result["faithfulness_claims"] == 2 and result["citation_links"] == 3


def test_missing_judge_is_not_silently_scored_as_zero_or_pass():
    result = summarize([row("a", True, "answered")])
    assert result["answer_correctness"] is None
    assert result["correctness_unjudged_answer_ids"] == ["a"]
    assert result["unjudged_answer_ids"] == ["a"]


def test_safe_handoff_is_not_equivalent_to_required_blocked_behavior():
    case = row("injection", False, "insufficient_evidence")
    case["gold"]["expected_behavior"] = "blocked"
    result = summarize([case])
    assert result["answerability"]["tn"] == 1
    assert result["behavior_accuracy"] == 0
    assert result["behavior_mismatch_ids"] == ["injection"]


def test_end_to_end_f1_penalizes_technical_failure_on_answerable_case():
    result = summarize([row("success", True, "answered"), row("failure", True, "error")])
    assert result["answerability"]["f1"] == 1
    assert result["answerability_end_to_end"]["f1"] == pytest.approx(2 / 3)
    assert result["answerability_end_to_end"]["fn"] == 1
