from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fakes import PublishingGitHub, publication_report
from sqlalchemy import func, select
from test_execution import prepare

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.models import (
    Installation,
    PullRequest,
    Repository,
    ReviewJob,
    ReviewPublication,
)
from shrike.adapters.persistence.publication import SqlPublicationStore
from shrike.application.publication import publish_review, render_plan
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.github import GitHubError
from shrike.domain.review import ReviewError
from shrike.domain.states import InstallationStatus, RepositoryStatus

pytestmark = pytest.mark.integration
SCOPE = ReadScope((RepositoryGrant(710001, 810001),))


def completed(database: Database) -> tuple[PublishingGitHub, UUID, SqlPublicationStore]:
    github = PublishingGitHub()
    _, envelope = prepare(database, github)
    executions = SqlExecutionStore(database)
    claim = executions.claim(envelope)
    assert claim is not None
    executions.complete(claim, publication_report())
    return github, envelope.record_id, SqlPublicationStore(database)


def publish(database: Database, github: PublishingGitHub, job_id: UUID) -> str:
    outcome = publish_review(job_id, SCOPE, SqlPublicationStore(database), github, 12345)
    assert outcome is not None
    return outcome.state


def due(database: Database, job_id: UUID) -> None:
    with database.session() as session, session.begin():
        row = session.get(ReviewPublication, job_id)
        assert row is not None
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)


def test_success_ids_and_idempotency_without_reanalysis(database: Database) -> None:
    github, job_id, store = completed(database)
    assert publish(database, github, job_id) == "published"
    assert publish_review(job_id, SCOPE, store, github, 12345) is None
    with database.session() as session:
        row = session.get(ReviewPublication, job_id)
        job = session.get(ReviewJob, job_id)
        assert row and row.review_id == 123 and row.comment_ids == [200] and row.attempts == 1
        assert row.payload and row.payload_digest
        assert job and job.attempt_count == 1
    assert github.calls.count("create_review") == 1
    assert not {"blob", "head_commit"} & set(github.calls)


def test_partial_comment_read_failure_keeps_review_id_and_reconciles(database: Database) -> None:
    github, job_id, _ = completed(database)
    github.comments_error = GitHubError("github_transient")
    assert publish(database, github, job_id) == "partial"
    with database.session() as session:
        row = session.get(ReviewPublication, job_id)
        assert row and row.review_id == 123 and row.comment_ids == []
    github.comments_error = None
    assert publish(database, github, job_id) == "published"
    assert len(github.plans) == 1


def test_lost_success_response_reconciles_without_second_post(database: Database) -> None:
    github, job_id, _ = completed(database)

    def lose_response() -> None:
        raise GitHubError("github_write_uncertain")

    github.after_write = lose_response
    assert publish(database, github, job_id) == "uncertain"
    github.after_write = None
    assert publish(database, github, job_id) == "published"
    assert len(github.plans) == 1


def test_absent_ambiguous_review_never_reposts(database: Database) -> None:
    github, job_id, _ = completed(database)
    github.post_error = GitHubError("github_write_uncertain")
    assert publish(database, github, job_id) == "uncertain"
    github.post_error = None
    assert publish(database, github, job_id) == "uncertain"
    assert len(github.plans) == 1


def test_preparing_lease_and_inflight_crash_recovery(database: Database) -> None:
    github, job_id, store = completed(database)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: store.claim(job_id, SCOPE), range(2)))
    assert sum(c is not None for c in claims) == 1
    claim = next(c for c in claims if c is not None)
    store.begin_write(claim, render_plan(claim.report, claim.marker))
    with database.session() as session, session.begin():
        row = session.get(ReviewPublication, job_id)
        assert row
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert publish(database, github, job_id) == "uncertain"
    assert not github.plans
    with pytest.raises(ReviewError):
        store.begin_write(claim, render_plan(claim.report, claim.marker))


def test_422_retries_summary_only_after_reconciliation(database: Database) -> None:
    github, job_id, _ = completed(database)
    github.post_error = GitHubError("github_invalid_review")
    assert publish(database, github, job_id) == "failed"
    due(database, job_id)
    github.post_error = None
    assert publish(database, github, job_id) == "published"
    assert github.plans[0].comments and not github.plans[1].comments
    assert "summary location" in github.plans[1].body


def test_definite_failures_are_bounded_and_honor_rate_hint(database: Database) -> None:
    github, job_id, store = completed(database)
    retry = datetime.now(UTC) + timedelta(hours=1)
    github.post_error = GitHubError("github_rate_limited", retry_at=retry)
    for _ in range(3):
        assert publish(database, github, job_id) == "failed"
        with database.session() as session:
            row = session.get(ReviewPublication, job_id)
            assert row and row.available_at >= retry
        assert publish_review(job_id, SCOPE, store, github, 12345) is None
        due(database, job_id)
    assert publish_review(job_id, SCOPE, store, github, 12345) is None
    assert len(github.plans) == 3


@pytest.mark.parametrize("change", ["head", "base", "closed", "draft", "fork"])
def test_canonical_revision_change_prevents_write(database: Database, change: str) -> None:
    github, job_id, _ = completed(database)
    updates = {
        "head": {"head_sha": "e" * 40},
        "base": {"base_sha": "e" * 40},
        "closed": {"state": "closed"},
        "draft": {"draft": True},
        "fork": {"head_repository_id": 999},
    }
    github.pr_data = replace(github.pr_data, **updates[change])  # type: ignore[arg-type]
    assert publish(database, github, job_id) == "suppressed"
    assert not github.plans


def test_late_revision_change_preserves_stale_external_ids(database: Database) -> None:
    github, job_id, _ = completed(database)

    def change_head() -> None:
        github.pr_data = replace(github.pr_data, head_sha="e" * 40)

    github.after_write = change_head
    assert publish(database, github, job_id) == "stale"
    with database.session() as session:
        row = session.get(ReviewPublication, job_id)
        assert row and row.review_id == 123
    assert len(github.plans) == 1


@pytest.mark.parametrize("change", ["installation", "repository", "generation", "head"])
def test_revocation_or_local_change_during_reads_prevents_write(
    database: Database, change: str
) -> None:
    github, job_id, _ = completed(database)

    def revoke() -> None:
        with database.session() as session, session.begin():
            installation = session.scalar(select(Installation))
            repository = session.scalar(select(Repository))
            pr = session.scalar(select(PullRequest))
            assert installation and repository and pr
            if change == "installation":
                installation.status = InstallationStatus.SUSPENDED
            elif change == "repository":
                repository.status = RepositoryStatus.REMOVED
            elif change == "generation":
                installation.access_generation += 1
            else:
                pr.head_sha = "e" * 40

    github.before_reviews = revoke
    assert publish(database, github, job_id) == "suppressed"
    assert not github.plans


def test_cross_repository_scope_and_report_only_are_read_only(database: Database) -> None:
    _, job_id, store = completed(database)
    for scope in [ReadScope(()), ReadScope((RepositoryGrant(710001, 999),))]:
        with pytest.raises(ReviewError, match="repository_denied"):
            store.preview(job_id, scope)
        with pytest.raises(ReviewError, match="repository_denied"):
            store.claim(job_id, scope)
    report, marker = store.preview(job_id, SCOPE)
    assert report.findings and "shrike-review" in marker
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ReviewPublication)) == 0


def test_wrong_app_marker_does_not_suppress_own_feedback(database: Database) -> None:
    github, job_id, store = completed(database)
    _, marker = store.preview(job_id, SCOPE)
    from shrike.domain.publication import PublishedReview

    github.published.append(
        PublishedReview(999, github.pr_data.head_sha, "forged\n\n" + marker, False, "COMMENTED")
    )
    assert publish(database, github, job_id) == "published"
    assert len(github.plans) == 1


def test_preparation_crash_is_safe_to_reclaim_without_resetting_attempts(
    database: Database,
) -> None:
    github, job_id, store = completed(database)
    first = store.claim(job_id, SCOPE)
    assert first
    with database.session() as session, session.begin():
        row = session.get(ReviewPublication, job_id)
        assert row
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert publish(database, github, job_id) == "published"
    with pytest.raises(ReviewError):
        store.begin_write(first, render_plan(first.report, first.marker))
    assert len(github.plans) == 1


def test_missing_comment_ids_are_partial_and_never_reposted(database: Database) -> None:
    github, job_id, _ = completed(database)

    def omit_comments() -> None:
        github.comments = ()

    github.after_write = omit_comments
    assert publish(database, github, job_id) == "partial"
    assert publish(database, github, job_id) == "partial"
    assert len(github.plans) == 1


def test_pending_matching_review_is_uncertain_and_never_resubmitted(database: Database) -> None:
    github, job_id, _ = completed(database)

    def make_pending() -> None:
        github.published[0] = replace(github.published[0], state="PENDING")
        raise GitHubError("github_write_uncertain")

    github.after_write = make_pending
    assert publish(database, github, job_id) == "uncertain"
    assert publish(database, github, job_id) == "uncertain"
    assert len(github.plans) == 1


def test_cli_opted_in_publication_and_safe_console_output(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from shrike import publication_cli

    github, job_id, _ = completed(database)
    key_path = tmp_path / "synthetic.pem"
    key_path.write_text("synthetic-unused-key")
    monkeypatch.setenv("DATABASE_URL", database.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("GITHUB_PUBLISHING_ENABLED", "true")
    monkeypatch.setenv("GITHUB_PUBLISH_REPOSITORY_GRANTS", "710001:810001")
    monkeypatch.setattr(github, "close", lambda: None, raising=False)
    monkeypatch.setattr(publication_cli, "GitHubAppClient", lambda *args, **kwargs: github)
    assert publication_cli.main(["--job-id", str(job_id)]) == 0
    assert not github.plans
    assert publication_cli.main(["--job-id", str(job_id), "--publish"]) == 0
    assert publication_cli.main(["--job-id", str(job_id), "--publish"]) == 0
    output = capsys.readouterr().out
    assert '"state": "published"' in output and '"state": "no_action"' in output
    assert "value =" not in output and "demo.py" not in output and "synthetic-unused" not in output
    assert len(github.plans) == 1
