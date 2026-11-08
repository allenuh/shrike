import json
from pathlib import Path
from typing import Any

import pytest
from fakes import publication_report
from pydantic import TypeAdapter, ValidationError

from shrike.application.diff import select_files
from shrike.domain.review import Candidate, ReviewLimits, SelectedFile
from shrike.evaluation import (
    Baseline,
    Case,
    Label,
    aggregate,
    dataset_digest,
    evaluate,
    percentile,
    score,
    write_result,
)


class EmptyAnalyzer:
    version = "trusted-empty-test-analyzer"

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        return ()


def case(**changes: Any) -> Case:
    return Case.model_validate(
        {
            "id": "synthetic",
            "before": "",
            "after": "value = 10 / 0\n",
            "labels": [{"rule": "division-by-zero", "line": 1}],
            "rationale": "Literal denominator is zero and execution raises.",
            **changes,
        }
    )


def test_exact_one_to_one_scoring_counts_extra_predictions_on_positive_case() -> None:
    report = publication_report()
    duplicate = report.findings[0].model_copy(update={"line": 2})
    row = score(case(), report.model_copy(update={"findings": (*report.findings, duplicate)}))
    assert (row["true_positives"], row["false_positives"], row["false_negatives"]) == (1, 1, 0)
    assert row["location_errors"] == 1
    wrong = score(case(), report.model_copy(update={"findings": (duplicate,)}))
    assert (wrong["true_positives"], wrong["false_positives"], wrong["false_negatives"]) == (
        0,
        1,
        1,
    )
    repeated = score(case(), report.model_copy(update={"findings": report.findings * 2}))
    assert repeated["true_positives"] == 1 and repeated["false_positives"] == 1


def test_metrics_denominators_and_clean_false_positives() -> None:
    report = publication_report()
    rows = [score(case(), report), score(case(labels=[]), report)]
    metrics = aggregate(rows)
    assert metrics["precision"] == 0.5 and metrics["recall"] == 1
    assert metrics["f1"] == pytest.approx(2 / 3)
    assert metrics["clean_case_false_positive_rate"] == 1
    empty = aggregate([])
    assert empty["precision"] is None and empty["recall"] is None
    assert percentile([], 0.95) is None
    assert percentile([1, 3, 2, 4], 0.95) == 4
    with pytest.raises(ValueError):
        percentile([1], 0)


def test_evaluation_cold_cache_mock_only_content_free_and_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentinel = "SYNTHETIC_SECRET_NOT_TO_BE_READ"
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", sentinel)
    result = evaluate([case()], EmptyAnalyzer(), repeats=2)
    assert result["provider"] == "mock"
    assert result["metrics"]["true_positives"] == 2
    assert result["estimated_model_cost_usd"] == "0.000000"
    assert result["hosted_cost_usd"] is None
    text = json.dumps(result)
    assert sentinel not in text and "value = 10 / 0" not in text and "demo.py" not in text
    path = tmp_path / "new" / "report.json"
    write_result(path, result)
    assert json.loads(path.read_text()) == result
    with pytest.raises(FileExistsError):
        write_result(path, result)
    for cases, repeats in [([], 1), ([case()], 0), ([case()] * 2, 1)]:
        with pytest.raises(ValueError):
            evaluate(cases, EmptyAnalyzer(), repeats)


def test_dataset_labels_are_unique_changed_head_lines() -> None:
    cases = TypeAdapter(list[Case]).validate_json(
        Path("tests/fixtures/evaluation/cases.json").read_bytes()
    )
    assert len(cases) == len({c.id for c in cases}) == 32
    for item in cases:
        files, _ = select_files(item.snapshot(), ReviewLimits())
        changed = {line for file in files for line in file.changed_lines}
        assert all(label.line in changed for label in item.labels), item.id
    with pytest.raises(ValidationError):
        case(labels=[Label(rule="F821", line=2)])
    with pytest.raises(ValidationError):
        case(labels=[Label(rule="F821", line=1)] * 2)
    with pytest.raises(ValidationError):
        case(path="../secret.py")


def test_regression_floor_rejects_changed_dataset_and_quality_regression() -> None:
    baseline = Baseline(
        dataset_sha256="a" * 64,
        min_precision=0.875,
        min_recall=0.875,
        max_clean_case_false_positive_rate=2 / 17,
    )
    result: dict[str, Any] = {
        "dataset_sha256": "a" * 64,
        "metrics": {"precision": 0.875, "recall": 0.875, "clean_case_false_positive_rate": 2 / 17},
    }
    assert baseline.accepts(result)
    for key, value in [
        ("precision", 0.874),
        ("recall", None),
        ("clean_case_false_positive_rate", 0.12),
    ]:
        changed = {**result, "metrics": {**result["metrics"], key: value}}
        assert not baseline.accepts(changed)
    assert not baseline.accepts({**result, "dataset_sha256": "b" * 64})
    assert dataset_digest(b'{"a":1}\n') == dataset_digest(b'{ "a": 1 }\r\n')
