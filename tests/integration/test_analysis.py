import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from alembic import command
from conftest import migration_config
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from shrike.adapters.analysis.ruff import RuffAnalyzer, sandbox_args
from shrike.adapters.llm.mock import MockProvider
from shrike.adapters.llm.openai import OpenAIProvider
from shrike.adapters.persistence.analysis import (
    SqlAnalysisStore,
    SqlSpendingLedger,
    initialize_budget,
)
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlProviderAdmission
from shrike.adapters.persistence.models import (
    AiBudget,
    AiSpendEntry,
    AnalysisReport,
    Installation,
    Repository,
)
from shrike.application.review import ReviewEngine
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.ai_budget import PriceProfile
from shrike.domain.review import Candidate, ReviewError, SelectedFile
from shrike.domain.states import InstallationStatus
from shrike.review_cli import EvalCase, snapshot

pytestmark = pytest.mark.integration


def profile() -> PriceProfile:
    return PriceProfile(
        model="gpt-6-luna",
        source="https://developers.openai.com/api/docs/pricing",
        verified_at=datetime.now(UTC) - timedelta(minutes=1),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        input_usd_per_million="0.10",
        output_usd_per_million="0.50",
        byte_token_bound_approved=True,
    )


def identity(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class NoopAnalyzer:
    version = "fake-static-v1"

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        return ()


def test_budget_initialization_and_hard_boundary(database: Database) -> None:
    ledger = SqlSpendingLedger(database)
    price = profile()
    with pytest.raises(ReviewError, match="budget_unreconciled"):
        ledger.reserve(identity("a"), 100, price, 500, 100)
    with pytest.raises(ReviewError, match="reconciliation_required"):
        initialize_budget(database, 0, confirmed=False)
    initialize_budget(database, 8999900, confirmed=True)
    with pytest.raises(ReviewError, match="already_initialized"):
        initialize_budget(database, 0, confirmed=True)
    assert ledger.reserve(identity("a"), 100, price, 500, 100)
    assert ledger.settle(identity("a"), 500, 100) == 100
    assert ledger.settle(identity("a"), 500, 100) == 100
    with pytest.raises(ReviewError, match="budget_exceeded"):
        ledger.reserve(identity("b"), 100, price, 500, 100)


def test_parallel_reservations_cannot_overspend(database: Database) -> None:
    initialize_budget(database, 8999900, confirmed=True)
    price = profile()

    def reserve(index: int) -> str:
        try:
            SqlSpendingLedger(database).reserve(identity(str(index)), 100, price, 500, 100)
            return "reserved"
        except ReviewError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, (1, 2)))
    assert sorted(outcomes) == ["budget_exceeded", "reserved"]


def test_uncertainty_restart_concurrency_and_no_replay(database: Database) -> None:
    initialize_budget(database, 0, confirmed=True)
    ledger = SqlSpendingLedger(database)
    price = profile()
    ledger.reserve(identity("a"), 100, price, 500, 100)
    assert ledger.settle(identity("a"), 50, None) is None
    restarted = SqlSpendingLedger(database)
    with pytest.raises(ReviewError, match="already_dispatched"):
        restarted.reserve(identity("a"), 100, price, 500, 100)
    with pytest.raises(ReviewError, match="concurrency_limit"):
        restarted.reserve(identity("b"), 100, price, 500, 100)
    with database.session() as session:
        row = session.get(AiSpendEntry, identity("a"))
        assert row is not None and row.state == "uncertain" and row.reserved_micro == 100
        assert row.input_tokens == 50 and row.output_tokens is None
    assert restarted.settle(identity("a"), 0, 0) == 0
    restarted.reserve(identity("b"), 100, price, 500, 100)


def test_per_review_and_evaluation_caps_persist(database: Database) -> None:
    initialize_budget(database, 0, confirmed=True, max_review_micro=150)
    price = profile()
    ledger = SqlSpendingLedger(database, evaluation_session=str(uuid4()), evaluation_limit=1)
    ledger.reserve(identity("a"), 100, price, 500, 100, "same-review")
    ledger.settle(identity("a"), 500, 100)
    restarted = SqlSpendingLedger(
        database, evaluation_session=ledger.evaluation_session, evaluation_limit=1
    )
    with pytest.raises(ReviewError, match="evaluation_request_limit"):
        restarted.reserve(identity("b"), 100, price, 500, 100, "other-review")
    with pytest.raises(ReviewError, match="budget_exceeded"):
        SqlSpendingLedger(database).reserve(identity("c"), 100, price, 500, 100, "same-review")
    SqlSpendingLedger(database).reserve(identity("d"), 100, price, 500, 100, "other-review")


def test_usage_overrun_freezes_budget(database: Database) -> None:
    initialize_budget(database, 0, confirmed=True)
    ledger = SqlSpendingLedger(database)
    ledger.reserve(identity("a"), 100, profile(), 500, 100)
    assert ledger.settle(identity("a"), 20000, 2000) == 3000
    with database.session() as session:
        budget = session.get(AiBudget, 1)
        assert budget is not None and budget.frozen
    with pytest.raises(ReviewError, match="budget_unreconciled"):
        ledger.reserve(identity("b"), 100, profile(), 500, 100)


def test_reservation_rejects_invalid_prices_or_quote(database: Database) -> None:
    initialize_budget(database, 0, confirmed=True)
    ledger = SqlSpendingLedger(database)
    with pytest.raises(ReviewError, match="invalid_cost_reservation"):
        ledger.reserve(identity("a"), 1, profile(), 500, 100)
    with pytest.raises(ReviewError, match="token_bound_unverified"):
        ledger.reserve(
            identity("b"),
            100,
            profile().model_copy(update={"byte_token_bound_approved": False}),
            500,
            100,
        )


def test_scoped_cache_revocation_and_report_purge_independent_from_spend(
    seeded_database: Database,
) -> None:
    db = seeded_database
    request = snapshot(EvalCase(id="fixture", code="value = 10 / 0\n", expected=None)).model_copy(
        update={"private": True}
    )
    scope = ReadScope((RepositoryGrant(710001, 810001),))
    store = SqlAnalysisStore(db, scope)
    engine = ReviewEngine(NoopAnalyzer(), MockProvider(), store)
    report = engine.analyze(request)
    assert len(report.findings) == 1
    assert (
        ReviewEngine(NoopAnalyzer(), MockProvider(), SqlAnalysisStore(db, scope))
        .analyze(request)
        .cache_hit
    )
    with pytest.raises(ReviewError, match="repository_denied"):
        SqlAnalysisStore(db, ReadScope(())).cached(request, "a" * 64)
    with pytest.raises(ReviewError, match="repository_denied"):
        engine.analyze(request.model_copy(update={"private": False}))
    initialize_budget(db, 0, confirmed=True)
    SqlSpendingLedger(db).reserve(identity("expense"), 100, profile(), 500, 100)
    with db.session() as session, session.begin():
        session.execute(delete(AnalysisReport))
        installation = session.scalar(select(Installation).where(Installation.github_id == 710001))
        assert installation is not None
        installation.status = InstallationStatus.SUSPENDED
    with pytest.raises(ReviewError, match="repository_denied"):
        engine.analyze(request)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(AiSpendEntry)) == 1


@pytest.mark.parametrize(
    "response_kind", ["valid", "invalid", "missing_usage", "timeout", "rate_limit"]
)
def test_mocked_hosted_engine_settlement(seeded_database: Database, response_kind: str) -> None:
    calls = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if response_kind == "timeout":
            raise httpx.ReadTimeout("PRIVATE_SOURCE_SENTINEL")
        if response_kind == "rate_limit":
            return httpx.Response(429, text="PRIVATE_SOURCE_SENTINEL")
        raw: dict[str, Any] = {
            "model": "gpt-6-luna",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "invalid" if response_kind == "invalid" else '{"findings":[]}',
                        }
                    ],
                }
            ],
        }
        if response_kind != "missing_usage":
            raw["usage"] = {"input_tokens": 100, "output_tokens": 20}
        return httpx.Response(200, json=raw)

    initialize_budget(seeded_database, 0, confirmed=True)
    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(handle)
    )
    try:
        engine = ReviewEngine(
            NoopAnalyzer(),
            provider,
            SqlAnalysisStore(seeded_database, ReadScope((RepositoryGrant(710001, 810001),))),
            pricing=profile(),
            ledger=SqlSpendingLedger(seeded_database),
            live_enabled=True,
            allow_private=True,
            model_allowlist=("gpt-6-luna",),
        )
        request = snapshot(EvalCase(id="fixture", code="value = 1\n", expected=None)).model_copy(
            update={"private": True}
        )
        result = engine.analyze(request)
        assert len(calls) == 1
        with seeded_database.session() as session:
            entry = session.scalar(select(AiSpendEntry))
            assert entry is not None
            assert entry.state == (
                "settled" if response_kind in {"valid", "invalid"} else "uncertain"
            )
            if response_kind in {"valid", "invalid"}:
                assert entry.input_tokens == 100 and entry.settled_micro == 20
        if response_kind in {"timeout", "rate_limit", "invalid"}:
            assert result.status == "static_only"
            engine.analyze(request)
            assert len(calls) == 1
        if response_kind == "valid":
            assert engine.analyze(request).cache_hit and len(calls) == 1
    finally:
        provider.close()


def test_analysis_downgrade_preserves_prior_data(seeded_database: Database) -> None:
    with seeded_database.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_github")
        assert connection.scalar(select(func.count()).select_from(Repository)) == 3
        command.upgrade(config, "head")
        command.check(config)


def test_real_ruff_and_container_policy() -> None:
    file = SelectedFile(path="example.py", content="result = unknown_value\n", changed_lines=(1,))
    result = RuffAnalyzer().analyze(file)
    assert len(result) == 1 and result[0].rule == "F821" and result[0].line == 1
    # Trusted probe under the identical restrictions; no repository code runs here.
    name = f"shrike-probe-{uuid4().hex}"
    args = sandbox_args(name)
    args[-1] = Path("infra/docker/probe-image.txt").read_text().strip()
    probe = (
        'test "$(id -u)" = 65534 && test ! -e /workspace && test ! -e /run/secrets '
        "&& ! touch /root-write 2>/dev/null && ! wget -T 1 -q -O /dev/null http://192.0.2.1 "
        '&& test "$(cat /sys/fs/cgroup/memory.max)" = 134217728 '
        '&& test "$(cat /sys/fs/cgroup/pids.max)" = 32 && echo sandbox-ok'
    )
    completed = subprocess.run(
        [*args, "sh", "-c", probe], capture_output=True, text=True, timeout=15
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "sandbox-ok"
    assert not any(item in args for item in ("--privileged", "--volume", "-v", "--mount"))


def test_scanner_timeout_and_cleanup() -> None:
    with pytest.raises(ReviewError, match="scanner_failed"):
        RuffAnalyzer(timeout=0.001).analyze(
            SelectedFile(path="x.py", content="a=1\n", changed_lines=(1,))
        )


def test_source_suppression_and_execution_are_ignored() -> None:
    source = 'value = missing  # noqa: F821\nopen("/tmp/must-not-run", "w").write("bad")\n'
    result = RuffAnalyzer().analyze(
        SelectedFile(path="demo.py", content=source, changed_lines=(1, 2))
    )
    assert len(result) == 1 and result[0].rule == "F821"


def test_budget_denial_prevents_mocked_transport_call(seeded_database: Database) -> None:
    initialize_budget(seeded_database, 9000000, confirmed=True)

    def forbidden(req: httpx.Request) -> httpx.Response:
        pytest.fail("Transport must not run when budget is exhausted")

    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(forbidden)
    )
    try:
        engine = ReviewEngine(
            NoopAnalyzer(),
            provider,
            SqlAnalysisStore(seeded_database, ReadScope((RepositoryGrant(710001, 810001),))),
            pricing=profile(),
            ledger=SqlSpendingLedger(seeded_database),
            live_enabled=True,
            allow_private=True,
            model_allowlist=("gpt-6-luna",),
        )
        request = snapshot(EvalCase(id="fixture", code="a=1\n", expected=None)).model_copy(
            update={"private": True}
        )
        assert engine.analyze(request).reason == "budget_exceeded"
    finally:
        provider.close()


def test_missing_ledger_table_fails_closed(database: Database) -> None:
    from sqlalchemy import text

    initialize_budget(database, 0, confirmed=True)
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE ai_spend_entries"))
    with pytest.raises(ReviewError, match="ledger_unavailable"):
        SqlSpendingLedger(database).reserve(identity("never-dispatched"), 100, profile(), 500, 100)


def test_hosted_evaluation_rate_is_durable_and_precedes_paid_reservation(
    seeded_database: Database,
) -> None:
    initialize_budget(seeded_database, 0, confirmed=True)
    SqlProviderAdmission(seeded_database, "hosted-evaluation", 1).acquire()

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Throttled evaluation must not make a paid HTTP attempt")

    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(forbidden)
    )
    try:
        engine = ReviewEngine(
            NoopAnalyzer(),
            provider,
            SqlAnalysisStore(seeded_database, ReadScope((RepositoryGrant(710001, 810001),))),
            pricing=profile(),
            ledger=SqlSpendingLedger(seeded_database),
            live_enabled=True,
            allow_private=True,
            model_allowlist=("gpt-6-luna",),
            admission=SqlProviderAdmission(seeded_database, "hosted-evaluation", 1),
        )
        result = engine.analyze(
            snapshot(EvalCase(id="throttled", code="value = 1\n", expected=None))
        )
        assert result.reason == "provider_throttled" and result.retry_at is not None
        with seeded_database.session() as session:
            assert session.scalar(select(func.count()).select_from(AiSpendEntry)) == 0
        with pytest.raises(ReviewError, match="provider_throttled"):
            SqlProviderAdmission(seeded_database, "hosted-evaluation", 1).acquire()
    finally:
        provider.close()
