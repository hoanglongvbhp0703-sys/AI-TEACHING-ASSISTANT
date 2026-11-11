import json

import pytest

from scripts.evaluate_golden import judge_record


class JudgeGateway:
    def __init__(self, response):
        self.response = response

    def request(self, *_args):
        return json.dumps(self.response), {"input_tokens": 1}


@pytest.fixture
def assessment():
    return {
        "reference_facts": [
            {"text": "first fact", "covered": True, "reason": "present"},
            {"text": "second fact", "covered": False, "reason": "missing"},
            {"text": "third fact", "covered": False, "reason": "missing"},
        ],
        "incorrect_answer_facts": ["contradiction"],
        "claims": [
            {
                "index": 1,
                "supported": True,
                "reason": "source supports it",
                "citations": [{"source": 1, "supported": True, "reason": "direct evidence"}],
            }
        ],
    }


@pytest.fixture
def answer():
    return {
        "gold": {"question": "question", "history": [], "expected_answer": "reference"},
        "generated": {
            "claims": [{"text": "answer", "evidence": [{"source": 1, "quote": "evidence"}]}]
        },
        "sources": [{"text": "evidence"}],
    }


def test_correctness_is_computed_from_fact_labels_not_an_arbitrary_model_score(answer, assessment):
    result, _usage = judge_record(answer, JudgeGateway(assessment), "test-model")
    assert result["correctness_counts"] == {"matched": 1, "missing": 2, "incorrect": 1}
    assert result["correctness"] == 0.4


def test_inconsistent_faithfulness_and_citation_labels_are_not_published(answer, assessment):
    assessment["claims"][0]["supported"] = False
    with pytest.raises(ValueError, match="contradict"):
        judge_record(answer, JudgeGateway(assessment), "test-model")


def test_judge_cannot_silently_replace_cited_source(answer, assessment):
    assessment["claims"][0]["citations"][0]["source"] = 2
    with pytest.raises(ValueError, match="alignment"):
        judge_record(answer, JudgeGateway(assessment), "test-model")


def test_judge_must_evaluate_every_generated_claim(answer, assessment):
    assessment["claims"] = []
    with pytest.raises(ValueError, match="coverage"):
        judge_record(answer, JudgeGateway(assessment), "test-model")


def test_two_quotes_from_same_chunk_are_one_citation_edge(answer, assessment):
    answer["generated"]["claims"][0]["evidence"].append({"source": 1, "quote": "another excerpt"})
    result, _usage = judge_record(answer, JudgeGateway(assessment), "test-model")
    assert len(result["claims"][0]["citations"]) == 1
