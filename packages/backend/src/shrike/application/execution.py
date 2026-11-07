"""Review use case independent of Celery/HTTP and provider transports."""

import fnmatch
from collections.abc import Callable

from shrike.domain.github import GitHubError, GitHubPullRequest, GitHubRepository
from shrike.domain.queue import Envelope, ReviewClaim
from shrike.domain.review import ReviewError, ReviewInput, ReviewLimits, SourceFile, safe_path
from shrike.ports.execution import ExecutionStore
from shrike.ports.github import GitHubGateway

from .review import ReviewEngine


def canonical(
    claim: ReviewClaim, github: GitHubGateway, app_id: int, checkpoint: Callable[[], None]
) -> tuple[GitHubRepository, GitHubPullRequest]:
    checkpoint()
    installation = github.installation(claim.installation_id)
    if (
        installation.id != claim.installation_id
        or installation.app_id != app_id
        or installation.account_id != claim.account_id
        or installation.suspended
    ):
        raise ReviewError("installation_inaccessible")
    checkpoint()
    repository = github.repository(
        claim.installation_id, claim.repository_id, claim.owner, claim.name
    )
    if (
        repository.id != claim.repository_id
        or repository.owner_id != claim.account_id
        or repository.archived
    ):
        raise ReviewError("repository_inaccessible")
    checkpoint()
    pr = github.pull_request(claim.installation_id, repository, claim.number)
    if (
        pr.id != claim.pr_id
        or pr.number != claim.number
        or pr.base_repository_id != repository.id
        or pr.head_repository_id != repository.id
        or pr.draft
        or pr.state != "open"
        or pr.head_sha != claim.head_sha
        or pr.base_sha != claim.base_sha
    ):
        raise ReviewError("stale_revision")
    return repository, pr


def snapshot(
    claim: ReviewClaim,
    github: GitHubGateway,
    repository: GitHubRepository,
    limits: ReviewLimits,
    checkpoint: Callable[[], None],
) -> ReviewInput:
    checkpoint()
    if github.head_commit(claim.installation_id, repository, claim.head_sha) != claim.head_sha:
        raise ReviewError("invalid_head_identity")
    checkpoint()
    metadata = github.files(claim.installation_id, repository, claim.number)
    if len(metadata) > 1000 or len({item.path for item in metadata}) != len(metadata):
        raise ReviewError("invalid_file_metadata")
    checkpoint()
    diff = github.diff(claim.installation_id, repository, claim.number)
    if len(diff) > limits.max_diff_bytes:
        raise ReviewError("diff_size_limit")
    files: list[SourceFile] = []
    for file in sorted(metadata, key=lambda f: f.path):
        safe_path(file.path)
        if (
            file.status == "removed"
            or not file.path.endswith(".py")
            or any(fnmatch.fnmatchcase(file.path, pattern) for pattern in limits.exclusions)
            or len(files) >= limits.max_files
        ):
            continue
        checkpoint()
        raw = github.blob(claim.installation_id, repository, file.sha)
        if len(raw) > limits.max_file_bytes:
            raise ReviewError("file_size_limit")
        try:
            content = raw.decode("utf-8")
            files.append(SourceFile(path=file.path, content=content))
        except UnicodeDecodeError:
            files.append(SourceFile(path=file.path, content="", kind="binary"))
    return ReviewInput(
        installation_id=claim.installation_id,
        repository_id=claim.repository_id,
        base_sha=claim.base_sha,
        head_sha=claim.head_sha,
        diff=diff.decode("utf-8"),
        files=tuple(files),
        private=repository.private or claim.private,
    )


TRANSIENT = {
    "github_transient",
    "github_rate_limited",
    "github_timeout",
    "scanner_failed",
    "provider_throttled",
    "review_deadline",
    "infrastructure_unavailable",
}
CANCELED = {
    "stale_execution",
    "stale_revision",
    "github_revision_changed",
    "pull_request_not_reviewable",
    "installation_inaccessible",
    "repository_inaccessible",
    "github_access_denied",
    "github_not_found",
    "repository_denied",
}


def execute_review(
    envelope: Envelope,
    store: ExecutionStore,
    github: GitHubGateway,
    app_id: int,
    engine_factory: Callable[[ReviewClaim], ReviewEngine],
) -> ReviewClaim | None:
    claim = store.claim(envelope)
    if claim is None:
        return None
    try:
        engine = engine_factory(claim)

        def checkpoint() -> None:
            store.checkpoint(claim)

        repository, _ = canonical(claim, github, app_id, checkpoint)
        request = snapshot(claim, github, repository, engine.limits, checkpoint)
        report = engine.analyze(request)
        if report.reason == "provider_throttled":
            raise ReviewError("provider_throttled", retry_at=report.retry_at)
        canonical(claim, github, app_id, checkpoint)
        store.complete(claim, report)
    except GitHubError as error:
        store.fail(
            claim,
            error.code,
            transient=error.code in TRANSIENT,
            retry_at=error.retry_at,
            canceled=error.code in CANCELED,
        )
    except ReviewError as error:
        store.fail(
            claim,
            error.code,
            transient=error.code in TRANSIENT,
            canceled=error.code in CANCELED,
            retry_at=error.retry_at,
        )
    except (ValueError, UnicodeError):
        store.fail(claim, "invalid_snapshot")
    except Exception:
        # Third-party exceptions may contain source or connection strings; never persist them.
        store.fail(claim, "infrastructure_unavailable", transient=True)
    return claim
