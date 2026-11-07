import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from shrike.domain.github import (
    GitHubError,
    GitHubFile,
    GitHubInstallation,
    GitHubPullRequest,
    GitHubRepository,
)
from shrike.domain.publication import PublicationPlan, PublishedComment, PublishedReview
from shrike.domain.review import Coverage, Finding, Report


def github_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (Path(__file__).parent / "fixtures/github" / name).read_text()
    )
    return data


class FakeGitHub:
    def __init__(self) -> None:
        self.installation_data = GitHubInstallation(710001, 12345, 610001, "Organization", False)
        self.repository_data = GitHubRepository(810001, 610001, "shrike-demo", "payments-api", True)
        self.pr_data = GitHubPullRequest(
            910101, 101, 810001, 810001, "a" * 40, "b" * 40, "open", False, 1
        )
        self.inventory: tuple[GitHubRepository, ...] = (self.repository_data,)
        self.calls: list[str] = []
        self.error: GitHubError | None = None
        self.repository_error: GitHubError | None = None
        self.on_pull_request: Callable[[], None] | None = None

    def _call(self, operation: str) -> None:
        self.calls.append(operation)
        if self.error:
            raise self.error

    def installation(self, installation_id: int) -> GitHubInstallation:
        self._call("installation")
        return self.installation_data

    def repositories(self, installation_id: int) -> tuple[GitHubRepository, ...]:
        self._call("repositories")
        return self.inventory

    def repository(
        self, installation_id: int, repository_id: int, owner: str, name: str
    ) -> GitHubRepository:
        self._call("repository")
        if self.repository_error:
            raise self.repository_error
        return self.repository_data

    def pull_request(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> GitHubPullRequest:
        self._call("pull_request")
        if self.on_pull_request:
            self.on_pull_request()
        return self.pr_data

    def files(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[GitHubFile, ...]:
        raise AssertionError("Ingestion must not fetch code")

    def diff(self, installation_id: int, repository: GitHubRepository, number: int) -> bytes:
        raise AssertionError("Ingestion must not fetch code")

    def head_commit(self, installation_id: int, repository: GitHubRepository, sha: str) -> str:
        raise AssertionError("Ingestion must not fetch commits")

    def blob(self, installation_id: int, repository: GitHubRepository, sha: str) -> bytes:
        raise AssertionError("Ingestion must not fetch source")


class ReviewGitHub(FakeGitHub):
    """Synthetic immutable source port for review-worker integration tests only."""

    def __init__(self) -> None:
        super().__init__()
        self.source = b"value = 10 / 0\n"
        self.file_sha = "c" * 40
        self.on_blob: Callable[[], None] | None = None

    def files(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[GitHubFile, ...]:
        self._call("files")
        return (GitHubFile(self.file_sha, "demo.py", "added", 1, 0),)

    def diff(self, installation_id: int, repository: GitHubRepository, number: int) -> bytes:
        self._call("diff")
        return (
            b"diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -0,0 +1 @@\n+"
            + self.source
        )

    def head_commit(self, installation_id: int, repository: GitHubRepository, sha: str) -> str:
        self._call("head_commit")
        return sha

    def blob(self, installation_id: int, repository: GitHubRepository, sha: str) -> bytes:
        self._call("blob")
        if self.on_blob:
            self.on_blob()
        return self.source


def publication_report() -> Report:
    return Report(
        analysis_hash="f" * 64,
        status="completed",
        summary="Synthetic report",
        findings=(
            Finding(
                category="correctness",
                severity="high",
                confidence=0.99,
                path="demo.py",
                line=1,
                problem="Division by zero always fails",
                suggestion="Reject the invalid denominator before computing",
                evidence="value = 10 / 0",
                rule="division-by-zero",
                analyzers=("mock",),
                fingerprint="d" * 64,
            ),
        ),
        coverage=Coverage(selected_files=1, skipped={}, changed_lines=1),
        provider="mock",
        model="mock-v1",
        prompt_version="test-v1",
        analyzer_version="fake-v1",
        input_token_estimate=100,
        estimated_cost_usd=None,
        latency_ms=1,
    )


class PublishingGitHub(ReviewGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[PublishedReview] = []
        self.comments: tuple[PublishedComment, ...] = ()
        self.post_error: GitHubError | None = None
        self.comments_error: GitHubError | None = None
        self.after_write: Callable[[], None] | None = None
        self.before_reviews: Callable[[], None] | None = None
        self.plans: list[PublicationPlan] = []

    def reviews(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[PublishedReview, ...]:
        self._call("reviews")
        if self.before_reviews:
            self.before_reviews()
        return tuple(self.published)

    def create_review(
        self,
        installation_id: int,
        repository: GitHubRepository,
        number: int,
        head_sha: str,
        plan: PublicationPlan,
    ) -> PublishedReview:
        self._call("create_review")
        self.plans.append(plan)
        if self.post_error:
            raise self.post_error
        review = PublishedReview(123, head_sha, plan.body, True, "COMMENTED")
        self.published.append(review)
        self.comments = tuple(
            PublishedComment(200 + i, c.body, True) for i, c in enumerate(plan.comments)
        )
        if self.after_write:
            self.after_write()
        return review

    def review_comments(
        self, installation_id: int, repository: GitHubRepository, number: int, review_id: int
    ) -> tuple[PublishedComment, ...]:
        self._call("review_comments")
        if self.comments_error:
            raise self.comments_error
        return self.comments
