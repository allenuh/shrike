"""Publish persisted analysis independently; uncertain writes are read-only forever."""

import hashlib
import html
import re
from contextlib import suppress
from uuid import UUID

from shrike.application.diff import changed_diff
from shrike.application.execution import canonical
from shrike.domain.access import ReadScope
from shrike.domain.github import GitHubError, GitHubRepository
from shrike.domain.publication import (
    InlineComment,
    PublicationClaim,
    PublicationOutcome,
    PublicationPlan,
    PublishedReview,
)
from shrike.domain.review import Report, ReviewError, ReviewLimits
from shrike.ports.publication import PublicationGateway, PublicationStore


def plain(value: str, limit: int = 450) -> str:
    """Render model prose as bounded text, without mentions, HTML, images or links."""
    value = " ".join(value.split())[:limit]
    value = html.escape(value).replace("@", "@\u200b").replace("://", ":\u200b//")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", value)[:700]


def finding_marker(body: str) -> str | None:
    match = re.search(r"<!-- shrike-finding:([a-f0-9]{64}) -->$", body)
    return match[0] if match else None


def render_plan(
    report: Report, marker: str, diff: str | None = None, *, summary_only: bool = False
) -> PublicationPlan:
    additions: dict[str, set[int]] = {}
    if diff is not None and not summary_only:
        try:
            additions, _, unsupported = changed_diff(diff, ReviewLimits())
            additions = {p: lines for p, lines in additions.items() if p not in unsupported}
        except ReviewError:
            pass  # Never guess positions from an incomplete, unsupported or invalid diff.
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    eligible = [
        f
        for f in report.findings
        if f.category in {"correctness", "security", "reliability"}
        and f.severity in {"medium", "high", "critical"}
        and f.confidence >= 0.85
        and f.evidence.strip()
    ]
    comments: list[InlineComment] = []
    fallback: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    selected = 0
    for f in sorted(eligible, key=lambda f: (rank[f.severity], f.path, f.line, f.rule)):
        key = (f.path, f.line, f.problem.casefold())
        if key in seen or selected >= 10:
            continue
        seen.add(key)
        selected += 1
        token = hashlib.sha256((f.path + str(f.line) + f.rule + f.problem).encode()).hexdigest()
        body = (
            f"**{f.severity.upper()} · {f.category}**: {plain(f.problem)}\n\n"
            f"Suggested action: {plain(f.suggestion)}\n\n<!-- shrike-finding:{token} -->"
        )
        if f.line in additions.get(f.path, set()):
            comments.append(InlineComment(path=f.path, line=f.line, body=body))
        else:
            fallback.append(f"- {plain(f.path, 512)}:{f.line} (summary location)\n\n{body}")
    label = "deterministic mock-assisted" if report.provider == "mock" else "AI-assisted"
    body = (
        f"## Shrike review\n\nAdvisory, {label}; analysis status: {report.status}.\n\n"
        f"Coverage: {report.coverage.selected_files} files; "
        f"{report.coverage.changed_lines} changed lines; "
        f"{sum(report.coverage.skipped.values())} files skipped. "
        f"{selected} findings selected; {len(report.findings) - selected} filtered or capped.\n\n"
        "This is bounded analysis, not a guarantee of correctness or security."
    )
    if report.reason or report.coverage.skipped or report.status != "completed":
        body += "\n\nCoverage is incomplete or degraded; inspect the internal report for details."
    if not selected:
        body += "\n\nNo findings met the publication threshold in the analyzed scope."
    elif comments:
        body += f"\n\nSee {len(comments)} inline findings for actionable issues."
    if fallback:
        body += "\n\n### Summary findings\n\n" + "\n\n".join(fallback)
    return PublicationPlan(body=body + "\n\n" + marker, comments=tuple(comments))


def _access(
    claim: PublicationClaim, store: PublicationStore, github: PublicationGateway, app_id: int
) -> GitHubRepository:
    c = claim.context
    store.checkpoint(claim)
    installation = github.installation(c.installation_id)
    if (
        installation.id != c.installation_id
        or installation.app_id != app_id
        or installation.account_id != c.account_id
        or installation.suspended
    ):
        raise ReviewError("installation_inaccessible")
    store.checkpoint(claim)
    repo = github.repository(c.installation_id, c.repository_id, c.owner, c.name)
    if repo.id != c.repository_id or repo.owner_id != c.account_id or repo.archived:
        raise ReviewError("repository_inaccessible")
    return repo


def publish_review(
    job_id: UUID, scope: ReadScope, store: PublicationStore, github: PublicationGateway, app_id: int
) -> PublicationOutcome | None:
    claim = store.claim(job_id, scope)
    if claim is None:
        return None
    c = claim.context
    review: PublishedReview | None = None
    wrote = False
    plan = claim.plan
    try:
        repo = _access(claim, store, github, app_id)
        store.checkpoint(claim)
        matches = [
            r
            for r in github.reviews(c.installation_id, repo, c.number)
            if r.own and r.commit_id == c.head_sha and r.body.endswith("\n\n" + claim.marker)
        ]
        if len(matches) > 1:
            raise ReviewError("publication_conflict")
        if matches:
            review = matches[0]
        elif claim.uncertain or claim.review_id is not None:
            raise ReviewError("publication_unconfirmed")
        else:
            canonical(c, github, app_id, lambda: store.checkpoint(claim, current=True))
            diff = None
            if not claim.summary_only:
                store.checkpoint(claim, current=True)
                with suppress(UnicodeError):
                    diff = github.diff(c.installation_id, repo, c.number).decode("utf-8")
            plan = render_plan(claim.report, claim.marker, diff, summary_only=claim.summary_only)
            # Repeat canonical validation after all reads, directly before committing intent.
            canonical(c, github, app_id, lambda: store.checkpoint(claim, current=True))
            store.begin_write(claim, plan)
            wrote = True
            review = github.create_review(c.installation_id, repo, c.number, c.head_sha, plan)
        if not review.own or review.commit_id != c.head_sha or review.state != "COMMENTED":
            raise ReviewError("publication_unconfirmed")
        if not review.body.endswith("\n\n" + claim.marker):
            raise ReviewError("publication_unconfirmed")
        # Canonical post-check detects the unavoidable compare/write race and keeps IDs.
        canonical(c, github, app_id, lambda: store.checkpoint(claim, current=True))
        store.checkpoint(claim)
        comments = github.review_comments(c.installation_id, repo, c.number, review.id)
        plan = claim.plan if not wrote else plan
        expected = {finding_marker(comment.body) for comment in plan.comments} if plan else set()
        ids = tuple(
            comment.id
            for comment in comments
            if comment.own and finding_marker(comment.body) in expected
        )
        actual = {finding_marker(comment.body) for comment in comments if comment.own}
        complete = plan is not None and expected <= actual and len(ids) == len(expected)
        outcome = PublicationOutcome(
            job_id,
            "published" if complete else "partial",
            review.id,
            ids,
            None if complete else "comment_ids_incomplete",
        )
    except (GitHubError, ReviewError) as error:
        stale = error.code in {
            "stale_revision",
            "stale_publication",
            "github_revision_changed",
            "repository_denied",
            "installation_inaccessible",
            "repository_inaccessible",
            "pull_request_not_reviewable",
        }
        state = "stale" if review and stale else "suppressed" if stale else "failed"
        if review and not stale:
            state = "partial" if review.state == "COMMENTED" else "uncertain"
            if error.code == "publication_unconfirmed":
                state = "uncertain"
        elif not stale and (
            claim.uncertain
            or (
                wrote
                and error.code
                not in {
                    "github_invalid_review",
                    "github_access_denied",
                    "github_not_found",
                    "github_authentication_failed",
                    "github_rate_limited",
                }
            )
        ):
            state = "uncertain"
        outcome = PublicationOutcome(
            job_id,
            state,
            review.id if review else claim.review_id,
            reason=error.code,
            retry_at=error.retry_at,
        )
    except Exception:
        outcome = PublicationOutcome(
            job_id,
            "uncertain" if wrote or claim.uncertain else "failed",
            review.id if review else claim.review_id,
            reason="publication_unavailable",
        )
    store.finish(claim, outcome)
    return outcome
