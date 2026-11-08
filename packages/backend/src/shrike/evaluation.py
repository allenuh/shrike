"""Offline labeled evaluation. Fixture source is data and is never executed."""

import argparse
import difflib
import hashlib
import json
import math
import os
import platform
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import Field, TypeAdapter, model_validator

from shrike.adapters.analysis.memory import MemoryAnalysisStore
from shrike.adapters.analysis.ruff import RuffAnalyzer
from shrike.adapters.llm.mock import MockProvider
from shrike.application.review import ReviewEngine
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.review import Report, ReviewInput, SourceFile, StrictModel, safe_path
from shrike.ports.review import Analyzer


class Label(StrictModel):
    rule: str = Field(min_length=1, max_length=80)
    line: int = Field(gt=0, le=1000000)


class Baseline(StrictModel):
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    min_precision: float = Field(ge=0, le=1)
    min_recall: float = Field(ge=0, le=1)
    max_clean_case_false_positive_rate: float = Field(ge=0, le=1)

    def accepts(self, result: dict[str, Any]) -> bool:
        metrics = result["metrics"]
        return bool(
            result["dataset_sha256"] == self.dataset_sha256
            and metrics["precision"] is not None
            and metrics["precision"] >= self.min_precision
            and metrics["recall"] is not None
            and metrics["recall"] >= self.min_recall
            and metrics["clean_case_false_positive_rate"] is not None
            and metrics["clean_case_false_positive_rate"] <= self.max_clean_case_false_positive_rate
        )


class Case(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    before: str = Field(max_length=204800, repr=False)
    after: str = Field(max_length=204800, repr=False)
    labels: tuple[Label, ...] = Field(max_length=100)
    rationale: str = Field(min_length=10, max_length=1000)
    path: str = "demo.py"

    @model_validator(mode="after")
    def valid_labels(self) -> "Case":
        safe_path(self.path)
        locations = [(label.rule, label.line) for label in self.labels]
        if len(set(locations)) != len(locations):
            raise ValueError("Duplicate labels")
        if any(label.line > len(self.after.splitlines()) for label in self.labels):
            raise ValueError("Label outside head file")
        return self

    def snapshot(self) -> ReviewInput:
        diff = f"diff --git a/{self.path} b/{self.path}\n" + "".join(
            difflib.unified_diff(
                self.before.splitlines(keepends=True),
                self.after.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
            )
        )
        return ReviewInput(
            installation_id=710001,
            repository_id=810001,
            base_sha="a" * 40,
            head_sha="b" * 40,
            diff=diff,
            files=(SourceFile(path=self.path, content=self.after),),
            private=False,
        )


def percentile(values: list[float], quantile: float) -> float | None:
    """Nearest-rank percentile; no interpolation or invented observations."""
    if not 0 < quantile <= 1:
        raise ValueError("Quantile must be in (0, 1]")
    return sorted(values)[math.ceil(len(values) * quantile) - 1] if values else None


def environment() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "logical_cpus": os.cpu_count(),
        "tool_versions": {
            name: version(name)
            for name in (
                "fastapi",
                "uvicorn",
                "SQLAlchemy",
                "psycopg",
                "redis",
                "celery",
                "httpx2",
                "ruff",
            )
        },
    }


def dataset_digest(raw: bytes) -> str:
    canonical = json.dumps(
        json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def score(case: Case, report: Report) -> dict[str, Any]:
    expected = {(case.path, label.rule, label.line) for label in case.labels}
    remaining = set(expected)
    tp = fp = location_errors = 0
    for finding in report.findings:
        identity = (finding.path, finding.rule, finding.line)
        if identity in remaining:
            tp += 1
            remaining.remove(identity)
        else:
            fp += 1
            location_errors += int(
                any(path == finding.path and rule == finding.rule for path, rule, _ in expected)
                and identity not in expected
            )
    return {
        "case_id": case.id,
        "labels": len(expected),
        "predictions": len(report.findings),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": len(remaining),
        "location_errors": location_errors,
        "clean": not expected,
        "status": report.status,
        "reason": report.reason,
        "rejected_findings": report.rejected_findings,
        "latency_ms": report.latency_ms,
        "input_token_upper_bound": report.input_token_estimate,
        "estimated_model_cost_usd": report.estimated_cost_usd,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp, fp, fn = (
        sum(row[key] for row in rows)
        for key in ("true_positives", "false_positives", "false_negatives")
    )
    clean = [row for row in rows if row["clean"]]
    return {
        "case_observations": len(rows),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "clean_cases": len(clean),
        "clean_cases_with_findings": sum(row["predictions"] > 0 for row in clean),
        "clean_case_false_positive_rate": (
            sum(row["predictions"] > 0 for row in clean) / len(clean) if clean else None
        ),
        "location_errors": sum(row["location_errors"] for row in rows),
        "latency_p50_ms": percentile([row["latency_ms"] for row in rows], 0.5),
        "latency_p95_ms": percentile([row["latency_ms"] for row in rows], 0.95),
    }


def evaluate(cases: list[Case], analyzer: Analyzer, repeats: int = 1) -> dict[str, Any]:
    if not 1 <= repeats <= 5 or not 1 <= len(cases) <= 100:
        raise ValueError("Evaluation bounds exceeded")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case identity")
    rows = []
    started = time.monotonic()
    for repeat in range(repeats):
        for case in cases:
            # Never consult ambient provider settings/keys or reuse an earlier case's cache.
            engine = ReviewEngine(
                analyzer,
                MockProvider(),
                MemoryAnalysisStore(ReadScope((RepositoryGrant(710001, 810001),))),
            )
            report = engine.analyze(case.snapshot())
            if report.provider != "mock" or report.cache_hit:
                raise ValueError("Evaluation must use a cold mock provider")
            rows.append({**score(case, report), "repeat": repeat + 1})
    return {
        "schema_version": 1,
        "kind": "shrike-labeled-evaluation",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "environment": environment(),
        "provider": "mock",
        "analyzer": analyzer.version,
        "cache": "cold per case",
        "repeats": repeats,
        "duration_seconds": time.monotonic() - started,
        "metrics": aggregate(rows),
        "estimated_model_cost_usd": "0.000000",
        "hosted_cost_usd": None,
        "infrastructure_cost_usd": None,
        "cases": rows,
    }


def write_result(path: Path, result: dict[str, Any]) -> None:
    # New files only: preserve previous runs, and do not accidentally clobber secrets.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shrike bounded mock-only labeled evaluation")
    parser.add_argument(
        "--dataset", type=Path, default=Path("tests/fixtures/evaluation/cases.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--check-baseline", type=Path)
    args = parser.parse_args()
    try:
        with args.dataset.open("rb") as handle:
            raw = handle.read(2097153)
        if len(raw) > 2097152:
            raise ValueError("Dataset too large")
        cases = TypeAdapter(list[Case]).validate_json(raw)
        result = evaluate(cases, RuffAnalyzer(), args.repeats)
        result["dataset_sha256"] = dataset_digest(raw)
        accepted = True
        if args.check_baseline:
            baseline = Baseline.model_validate_json(args.check_baseline.read_bytes())
            accepted = baseline.accepts(result)
            result["baseline_passed"] = accepted
        write_result(args.output, result)
        print(json.dumps(result["metrics"], allow_nan=False))
        # Measurement, not a claim of perfect quality. Regression gates are separate tests.
        return 0 if accepted else 1
    except Exception:
        print('{"error":"evaluation_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
