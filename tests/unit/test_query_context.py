import pytest

from app.rag.query_rewriter import RewriteOutput, resolve_rewrite
from app.services.progress_service import terminal_progress


@pytest.mark.parametrize(
    "question",
    [
        "Machine Learning là gì",
        "Học máy là gì?",
        "Thuật toán hồi quy là gì",
        "Trong học máy chúng ta đánh giá mô hình thế nào?",
    ],
)
def test_standalone_question_kept_even_if_model_suggests_previous_topic(question):
    output = RewriteOutput(
        relation="standalone", standalone_question="Hồi quy tuyến tính", used_turn_ids=[]
    )
    result = resolve_rewrite(question, [{"turn_id": "history-1"}], output)
    assert result["resolved_question"] == question and result["used_turn_ids"] == []


def test_contextual_followup_replaces_pronoun_without_concatenating_history():
    output = RewriteOutput(
        relation="follow_up",
        standalone_question="KNN có nhược điểm gì?",
        used_turn_ids=["history-1"],
    )
    result = resolve_rewrite("Nó có nhược điểm gì?", [{"turn_id": "history-1"}], output)
    assert result["original_question"] == "Nó có nhược điểm gì?"
    assert result["resolved_question"] == "KNN có nhược điểm gì?"


def test_unknown_history_reference_is_rejected():
    from app.core.errors import AppError

    output = RewriteOutput(
        relation="follow_up", standalone_question="KNN là gì?", used_turn_ids=["invented"]
    )
    with pytest.raises(AppError):
        resolve_rewrite("Nó là gì?", [{"turn_id": "real"}], output)


def test_ambiguous_rewrite_preserves_original():
    result = resolve_rewrite(
        "Cái đó là gì?",
        [{"turn_id": "real"}],
        RewriteOutput(relation="ambiguous", standalone_question="Bịa một chủ đề", used_turn_ids=[]),
    )
    assert (
        result["resolved_question"] == "Cái đó là gì?" and result["status"] == "ambiguous_fallback"
    )


def test_quota_notice_does_not_claim_rag_completion():
    result = terminal_progress("quota_exceeded", None, False, False)
    assert (
        result["percent"] == 0 and result["status"] == "rejected" and result["llm_called"] is False
    )
    answered = terminal_progress("answered", None, True, True)
    assert answered["percent"] == 100 and answered["llm_called"] is True
