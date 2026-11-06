from shrike.domain.github import GitHubError
from shrike.domain.ingestion import IngestionResult
from shrike.ports.github import GitHubGateway
from shrike.ports.ingestion import IngestionStore


def process_one(store: IngestionStore, github: GitHubGateway, app_id: int) -> bool:
    claim = store.claim()
    if claim is None:
        return False
    incoming = claim.incoming
    if claim.blocked_reason:
        store.fail(claim, claim.blocked_reason)
        return True
    assert incoming.installation_id is not None
    try:
        try:
            installation = github.installation(incoming.installation_id)
        except GitHubError as error:
            if error.code == "github_not_found":
                raise GitHubError("installation_unavailable") from None
            if error.code == "github_access_denied":
                raise GitHubError("installation_inaccessible") from None
            raise
        if (
            installation.id != incoming.installation_id
            or installation.app_id != app_id
            or installation.account_id != incoming.account_id
            or installation.account_type != incoming.account_type
        ):
            raise GitHubError("invalid_github_identity")
        if installation.suspended:
            store.complete(
                claim, IngestionResult(installation, (), reason="installation_suspended")
            )
        elif incoming.event != "pull_request":
            repositories = github.repositories(installation.id)
            if any(repo.owner_id != installation.account_id for repo in repositories):
                raise GitHubError("invalid_github_identity")
            store.complete(claim, IngestionResult(installation, repositories))
        else:
            assert incoming.repository_id is not None and incoming.owner and incoming.name
            repository = github.repository(
                installation.id, incoming.repository_id, incoming.owner, incoming.name
            )
            if (
                repository.id != incoming.repository_id
                or repository.owner_id != installation.account_id
            ):
                raise GitHubError("invalid_github_identity")
            assert incoming.number is not None
            pr = github.pull_request(installation.id, repository, incoming.number)
            if (
                pr.id != incoming.pr_id
                or pr.number != incoming.number
                or pr.base_repository_id != repository.id
            ):
                raise GitHubError("invalid_github_identity")
            reason = None
            if pr.head_repository_id != repository.id:
                reason = "untrusted_fork"
            elif pr.draft or pr.state != "open":
                reason = "pull_request_not_reviewable"
            elif repository.archived:
                reason = "repository_archived"
            store.complete(claim, IngestionResult(installation, (repository,), pr, reason))
    except GitHubError as error:
        store.fail(claim, error.code, error.retry_at)
    except Exception:
        # Never persist third-party exception strings or private response data.
        store.fail(claim, "ingestion_internal_error")
    return True
