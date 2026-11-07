"""Operator-only snapshot analysis/evaluation. No HTTP/queue/publication coupling."""

import argparse
import difflib
import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import Field, SecretStr, TypeAdapter

from shrike.adapters.analysis.memory import MemoryAnalysisStore
from shrike.adapters.analysis.ruff import RuffAnalyzer
from shrike.adapters.llm.mock import MockProvider
from shrike.adapters.llm.openai import OpenAIProvider
from shrike.adapters.persistence.analysis import (
    SqlAnalysisStore,
    SqlSpendingLedger,
    initialize_budget,
)
from shrike.adapters.persistence.database import Database
from shrike.analysis_config import AnalysisSettings
from shrike.application.review import ReviewEngine
from shrike.config import Settings, parse_grants
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.ai_budget import PriceProfile
from shrike.domain.review import ModelReply, ReviewError, ReviewInput, SourceFile, StrictModel
from shrike.ports.review import AnalysisStore, LLMProvider


class EvalCase(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    code: str = Field(max_length=204800, repr=False)
    expected: str | None


def snapshot(case: EvalCase) -> ReviewInput:
    diff = "diff --git a/demo.py b/demo.py\n" + "".join(
        difflib.unified_diff(
            [], case.code.splitlines(keepends=True), fromfile="a/demo.py", tofile="b/demo.py"
        )
    )
    return ReviewInput(
        installation_id=710001,
        repository_id=810001,
        base_sha="a" * 40,
        head_sha="b" * 40,
        diff=diff,
        files=(SourceFile(path="demo.py", content=case.code),),
        private=True,
    )


def bounded_read(path: Path, maximum: int = 2097152) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ReviewError("input_size_limit")
    return data


class QuoteProvider:
    name = "openai"

    def __init__(self, model: str) -> None:
        self.model = model

    def review(self, context: str, max_output_tokens: int) -> ModelReply:
        raise ReviewError("dry_run_only")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shrike bounded snapshot analysis; mock is the default"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--snapshot", type=Path, required=True)
    analyze.add_argument("--report", type=Path, help="Explicit private report output; never stdout")
    analyze.add_argument("--dry-run", action="store_true")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument(
        "--dataset", type=Path, default=Path("tests/fixtures/analysis/cases.json")
    )
    evaluate.add_argument("--live", action="store_true")
    evaluate.add_argument("--max-requests", type=int)
    evaluate.add_argument("--session", type=UUID)
    budget = commands.add_parser("budget-init")
    budget.add_argument("--prior-spend-usd", type=Decimal, required=True)
    budget.add_argument("--confirm-reconciled", action="store_true")
    args = parser.parse_args()
    database = None
    provider: LLMProvider = MockProvider()
    try:
        config = AnalysisSettings()
        if args.command == "budget-init":
            database = Database(Settings().database_url.get_secret_value())
            amount = args.prior_spend_usd * 1000000
            if not amount.is_finite() or amount != amount.to_integral_value():
                raise ReviewError("invalid_prior_spend")
            initialize_budget(
                database,
                int(amount),
                confirmed=args.confirm_reconciled,
                total_micro=int(Decimal(os.environ.get("AI_BUDGET_TOTAL_USD", "10.00")) * 1000000),
                warning_micro=int(
                    Decimal(os.environ.get("AI_BUDGET_WARNING_USD", "7.50")) * 1000000
                ),
                hard_micro=int(
                    Decimal(os.environ.get("AI_BUDGET_HARD_STOP_USD", "9.00")) * 1000000
                ),
                max_review_micro=int(
                    Decimal(os.environ.get("AI_MAX_REVIEW_COST_USD", "0.02")) * 1000000
                ),
                max_live=int(os.environ.get("LLM_MAX_LIVE_CONCURRENCY", "1")),
            )
            print(json.dumps({"event": "budget_initialized"}))
            return
        dry = args.command == "analyze" and args.dry_run
        evaluation = args.command == "evaluate"
        if evaluation and not args.live and config.provider != "mock":
            raise ReviewError("evaluation_requires_mock")
        if (
            evaluation
            and args.live
            and (
                config.provider != "openai"
                or not config.live_eval_enabled
                or args.session is None
                or args.max_requests is None
                or not 1 <= args.max_requests <= config.live_eval_max
            )
        ):
            raise ReviewError("live_evaluation_not_enabled")
        ledger = None
        pricing = None
        store: AnalysisStore = MemoryAnalysisStore(ReadScope((RepositoryGrant(710001, 810001),)))
        if config.provider == "openai":
            if config.pricing_path is not None:
                pricing = PriceProfile.model_validate_json(bounded_read(config.pricing_path, 16384))
            if dry:
                provider = QuoteProvider(config.model)
            else:
                if (
                    not config.live_enabled
                    or os.environ.get("CI")
                    or os.environ.get("PYTEST_CURRENT_TEST")
                    or os.environ.get("APP_ENV") == "test"
                ):
                    raise ReviewError("live_not_enabled")
                if pricing is None:
                    raise ReviewError("pricing_unavailable")
                pricing.check(config.model, live=True)
                database = Database(Settings().database_url.get_secret_value())
                grants = parse_grants(os.environ.get("DEV_REPOSITORY_GRANTS", ""))
                store = SqlAnalysisStore(database, ReadScope(grants))
                ledger = SqlSpendingLedger(
                    database,
                    evaluation_session=str(args.session) if evaluation else None,
                    evaluation_limit=args.max_requests if evaluation else None,
                )
                provider = OpenAIProvider(
                    config.model,
                    SecretStr(os.environ.get("LLM_API_KEY", "")),
                    timeout=config.timeout,
                )
        elif os.environ.get("DATABASE_URL"):
            database = Database(Settings().database_url.get_secret_value())
            store = SqlAnalysisStore(
                database, ReadScope(parse_grants(os.environ.get("DEV_REPOSITORY_GRANTS", "")))
            )
        engine = ReviewEngine(
            RuffAnalyzer(),
            provider,
            store,
            config.limits(),
            ledger=ledger,
            pricing=pricing,
            live_enabled=config.live_enabled,
            allow_private=config.allow_private,
            model_allowlist=tuple(config.allowlist.split(",")),
        )
        if evaluation:
            cases = TypeAdapter(list[EvalCase]).validate_json(bounded_read(args.dataset))
            if not 1 <= len(cases) <= 100:
                raise ReviewError("dataset_size_limit")
            if args.live:
                cases = cases[: args.max_requests]
            hits = false_positives = misses = cache_hits = static_hits = mock_hits = 0
            for case in cases:
                result = engine.analyze(snapshot(case))
                rules = {finding.rule for finding in result.findings}
                cache_hits += result.cache_hit
                if case.expected is not None:
                    hit = case.expected in rules
                    hits += hit
                    misses += not hit
                    static_hits += sum(
                        "ruff" in f.analyzers and f.rule == case.expected for f in result.findings
                    )
                    mock_hits += sum(
                        "mock" in f.analyzers and f.rule == case.expected for f in result.findings
                    )
                else:
                    false_positives += bool(rules)
                if args.live and result.status == "static_only":
                    raise ReviewError(result.reason or "live_evaluation_stopped")
            print(
                json.dumps(
                    {
                        "cases": len(cases),
                        "hits": hits,
                        "misses": misses,
                        "false_positive_cases": false_positives,
                        "static_hits": static_hits,
                        "mock_hits": mock_hits,
                        "cache_hits": cache_hits,
                        "provider": provider.name,
                    }
                )
            )
            if misses or false_positives:
                parser.exit(1, "Evaluation expectations were not met\n")
        else:
            request = ReviewInput.model_validate_json(bounded_read(args.snapshot, 6291456))
            report = engine.analyze(request, dry_run=dry)
            if args.report is not None:
                # Explicit artifact, not an operational log; caller controls access and retention.
                with args.report.open("x", encoding="utf-8") as output:
                    output.write(report.model_dump_json(indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "status": report.status,
                        "findings": len(report.findings),
                        "cache_hit": report.cache_hit,
                        "reason": report.reason,
                        "estimated_cost_usd": report.estimated_cost_usd,
                        "input_token_estimate": report.input_token_estimate,
                    }
                )
            )
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, ReviewError)
            else "analysis_configuration_or_execution_failed"
        )
        parser.exit(2, f"Shrike analysis refused or failed: {code}\n")
    finally:
        if isinstance(provider, OpenAIProvider):
            provider.close()
        if database is not None:
            database.dispose()


if __name__ == "__main__":
    main()
