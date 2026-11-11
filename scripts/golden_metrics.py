"""Explicit metric aggregation for the project's golden evaluation (not RAGAS)."""


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def unique_citations(citations):
    """Multiple quotes from the same chunk are one claim-to-source citation edge."""
    unique = {}
    for index, citation in enumerate(citations):
        key = citation.get("source", ("position", index))
        if key in unique and unique[key]["supported"] != citation["supported"]:
            raise ValueError("Judge duplicate citation labels contradict each other")
        unique.setdefault(key, citation)
    return list(unique.values())


def summarize(rows):
    positives = [r for r in rows if r["gold"]["answerable"]]
    valid = [r for r in rows if r["status"] in {"answered", "blocked", "insufficient_evidence"}]
    errors = [r["gold"]["id"] for r in rows if r not in valid]
    tp = sum(r["gold"]["answerable"] and r["status"] == "answered" for r in valid)
    fp = sum(not r["gold"]["answerable"] and r["status"] == "answered" for r in valid)
    fn = sum(r["gold"]["answerable"] and r["status"] != "answered" for r in valid)
    tn = len(valid) - tp - fp - fn
    # End-to-end answerability predicts "answerable" only when an answer is delivered.
    # A positive case ending in technical error is therefore a false negative.
    e2e_fn = len(positives) - tp
    e2e_tn = len(rows) - len(positives) - fp
    scored = [r for r in positives if r.get("judge") is not None or r["status"] != "answered"]
    correctness = sum(r["judge"]["correctness"] if r["status"] == "answered" else 0 for r in scored)
    judged = [r for r in rows if r["status"] == "answered" and r.get("judge") is not None]
    claims = [c for r in judged for c in r["judge"]["claims"]]
    links = [link for c in claims for link in unique_citations(c["citations"])]
    return {
        "cases": len(rows),
        "answerable_cases": len(positives),
        "recall_at_5_page_proxy": ratio(
            sum(r.get("page_hit_at_5", False) for r in positives), len(positives)
        ),
        "file_hit_at_5": ratio(
            sum(r.get("file_hit_at_5", False) for r in positives), len(positives)
        ),
        "answer_correctness": ratio(correctness, len(scored)),
        "correctness_denominator": len(scored),
        "correctness_unjudged_answer_ids": [
            r["gold"]["id"]
            for r in positives
            if r["status"] == "answered" and r.get("judge") is None
        ],
        "faithfulness": ratio(sum(c["supported"] for c in claims), len(claims)),
        "faithfulness_claims": len(claims),
        "citation_faithfulness": ratio(sum(link["supported"] for link in links), len(links)),
        "citation_links": len(links),
        "judged_answer_count": len(judged),
        "unjudged_answer_ids": [
            r["gold"]["id"] for r in rows if r["status"] == "answered" and r.get("judge") is None
        ],
        "answerability": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn),
            "evaluated": len(valid),
            "technical_error_ids": errors,
        },
        "answerability_end_to_end": {
            "tp": tp,
            "fp": fp,
            "fn": e2e_fn,
            "tn": e2e_tn,
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + e2e_fn),
            "f1": ratio(2 * tp, 2 * tp + fp + e2e_fn),
            "evaluated": len(rows),
            "note": "answered is the only positive prediction; a negative-label technical error is a non-answer, not proof of a safe refusal.",
        },
        "behavior_accuracy": ratio(
            sum(r.get("actual_behavior") == r["gold"]["expected_behavior"] for r in rows), len(rows)
        ),
        "behavior_mismatch_ids": [
            r["gold"]["id"]
            for r in rows
            if r.get("actual_behavior") != r["gold"]["expected_behavior"]
        ],
    }
