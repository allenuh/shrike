"""Bounded, read-only GitHub.com adapter. Credentials and source never enter errors/logs."""

import base64
import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import httpx2 as httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import AwareDatetime, BaseModel, Field, SecretStr, TypeAdapter, ValidationError

from shrike.domain.github import (
    GitHubError,
    GitHubFile,
    GitHubInstallation,
    GitHubPullRequest,
    GitHubRepository,
)

from .schemas import FileData, GitHubModel, InstallationData, PullRequestData, RepositoryData

API_ORIGIN = "https://api.github.com"
API_VERSION = "2026-03-10"
READ_PERMISSIONS = {"metadata": "read", "contents": "read", "pull_requests": "read"}


class TokenData(GitHubModel):
    token: SecretStr = Field(min_length=1, max_length=16384)
    expires_at: AwareDatetime


@dataclass
class CachedToken:
    value: SecretStr = field(repr=False)
    expires_at: float


def _repo(data: RepositoryData) -> GitHubRepository:
    return GitHubRepository(
        data.id, data.owner.id, data.owner.login, data.name, data.private, data.archived
    )


def _parse[T: BaseModel](data: bytes, model: type[T]) -> T:
    try:
        return model.model_validate_json(data)
    except (ValidationError, ValueError, RecursionError):
        raise GitHubError("invalid_github_response") from None


class GitHubAppClient:
    def __init__(
        self,
        app_id: int,
        private_key: bytes,
        *,
        client_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        max_files: int = 20,
        max_file_bytes: int = 204800,
        max_diff_bytes: int = 524288,
    ) -> None:
        try:
            key = load_pem_private_key(private_key, password=None)
            if not isinstance(key, RSAPrivateKey) or key.key_size < 2048 or app_id <= 0:
                raise ValueError
        except Exception:
            raise GitHubError("invalid_app_configuration") from None
        self.app_id, self._key, self._issuer = app_id, private_key, client_id or str(app_id)
        self.clock, self.sleep = clock, sleep
        self.max_files, self.max_file_bytes, self.max_diff_bytes = (
            max_files,
            max_file_bytes,
            max_diff_bytes,
        )
        self._tokens: OrderedDict[tuple[int, int | None], CachedToken] = OrderedDict()
        self._lock = threading.Lock()
        for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
            logging.getLogger(name).disabled = True
        self._http = httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=5,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "Accept-Encoding": "identity",
                "User-Agent": "Shrike/0.1",
            },
        )

    @classmethod
    def from_key_file(cls, app_id: int, path: Path) -> "GitHubAppClient":
        try:
            with path.open("rb") as handle:
                private_key = handle.read(65537)
            if len(private_key) > 65536:
                raise ValueError
        except (OSError, ValueError):
            raise GitHubError("invalid_app_configuration") from None
        # Additional constructor parameters are supplied explicitly by composition roots instead.
        return cls(app_id, private_key)

    def close(self) -> None:
        self._tokens.clear()
        self._http.close()

    def _jwt(self) -> str:
        now = int(self.clock())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._issuer}, self._key, algorithm="RS256"
        )

    def _retry_time(self, headers: httpx.Headers) -> datetime:
        now = self.clock()
        try:
            hint = headers.get("retry-after")
            if hint:
                stamp = (
                    now + max(1, int(hint))
                    if hint.isdigit()
                    else parsedate_to_datetime(hint).timestamp()
                )
            elif headers.get("x-ratelimit-remaining") == "0":
                stamp = float(headers["x-ratelimit-reset"]) + 1
            else:
                stamp = now + 60
            return datetime.fromtimestamp(max(now + 1, stamp), UTC)
        except (ValueError, TypeError, KeyError, OverflowError, OSError):
            return datetime.fromtimestamp(now + 60, UTC)

    def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        body: dict[str, object] | None = None,
        accept: str = "application/vnd.github+json",
        limit: int = 2097152,
    ) -> tuple[bytes, str | None]:
        for attempt in range(3):
            try:
                start = time.monotonic()
                with self._http.stream(
                    method,
                    API_ORIGIN + path,
                    json=body,
                    headers={"Authorization": "Bearer " + token, "Accept": accept},
                ) as response:
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise GitHubError("unsupported_content_encoding")
                    length = response.headers.get("content-length")
                    if length is not None and (not length.isdigit() or int(length) > limit):
                        raise GitHubError("github_response_too_large")
                    result = bytearray()
                    for chunk in response.iter_bytes():
                        if len(result) + len(chunk) > limit:
                            raise GitHubError("github_response_too_large")
                        if time.monotonic() - start > 10:
                            raise GitHubError(
                                "github_transient",
                                retry_at=datetime.fromtimestamp(self.clock() + 5, UTC),
                            )
                        result.extend(chunk)
                    data, status = bytes(result), response.status_code
                    if status == 429 or (
                        status == 403
                        and (
                            "retry-after" in response.headers
                            or response.headers.get("x-ratelimit-remaining") == "0"
                            or b"rate limit" in data.lower()
                        )
                    ):
                        raise GitHubError(
                            "github_rate_limited", retry_at=self._retry_time(response.headers)
                        )
                    if status >= 500:
                        if attempt < 2:
                            self.sleep(0.25 * 2**attempt)
                            continue
                        raise GitHubError(
                            "github_transient",
                            retry_at=datetime.fromtimestamp(self.clock() + 5, UTC),
                        )
                    if status == 401:
                        raise GitHubError("github_authentication_failed")
                    if status in {403, 404, 410, 422}:
                        raise GitHubError(
                            "github_not_found" if status in {404, 410} else "github_access_denied"
                        )
                    if status not in {200, 201}:
                        raise GitHubError("unexpected_github_status")
                    return data, response.headers.get("link")
            except httpx.RequestError:
                if attempt < 2:
                    self.sleep(0.25 * 2**attempt)
                    continue
                raise GitHubError(
                    "github_transient", retry_at=datetime.fromtimestamp(self.clock() + 5, UTC)
                ) from None
        raise AssertionError("Unreachable")

    def _token(self, installation_id: int, repository_id: int | None) -> str:
        if not 0 < installation_id < 2**63:
            raise GitHubError("invalid_github_identity")
        scope = (installation_id, repository_id)
        with self._lock:
            cached = self._tokens.get(scope)
            if cached and cached.expires_at > self.clock() + 60:
                self._tokens.move_to_end(scope)
                return cached.value.get_secret_value()
            body: dict[str, object] = {
                "permissions": READ_PERMISSIONS
                if repository_id is not None
                else {"metadata": "read"}
            }
            if repository_id is not None:
                body["repository_ids"] = [repository_id]
            raw, _ = self._request(
                "POST",
                f"/app/installations/{installation_id}/access_tokens",
                self._jwt(),
                body=body,
            )
            token = _parse(raw, TokenData)
            expires = token.expires_at.timestamp()
            if not self.clock() + 60 < expires <= self.clock() + 3700:
                raise GitHubError("invalid_github_response")
            self._tokens[scope] = CachedToken(token.token, expires)
            self._tokens.move_to_end(scope)
            if len(self._tokens) > 128:
                self._tokens.popitem(last=False)
            return token.token.get_secret_value()

    def _get(
        self,
        installation_id: int,
        repository_id: int | None,
        path: str,
        *,
        accept: str = "application/vnd.github+json",
        limit: int = 2097152,
    ) -> tuple[bytes, str | None]:
        for attempt in range(2):
            token = self._token(installation_id, repository_id)
            try:
                return self._request("GET", path, token, accept=accept, limit=limit)
            except GitHubError as error:
                if error.code != "github_authentication_failed" or attempt:
                    raise
                with self._lock:
                    self._tokens.pop((installation_id, repository_id), None)
        raise AssertionError("Unreachable")

    def installation(self, installation_id: int) -> GitHubInstallation:
        if not 0 < installation_id < 2**63:
            raise GitHubError("invalid_github_identity")
        raw, _ = self._request("GET", f"/app/installations/{installation_id}", self._jwt())
        data = _parse(raw, InstallationData)
        if data.id != installation_id or data.app_id != self.app_id:
            raise GitHubError("invalid_github_identity")
        return GitHubInstallation(
            data.id, data.app_id, data.account.id, data.account.type, data.suspended_at is not None
        )

    def _pages(
        self, installation_id: int, repository_id: int | None, path: str, *, inventory: bool = False
    ) -> list[object]:
        items: list[object] = []
        bound = 1000 if inventory else self.max_files
        for page in range(1, 12):
            raw, link = self._get(
                installation_id, repository_id, f"{path}?per_page=100&page={page}"
            )
            try:
                payload = json.loads(raw)
                if inventory and (
                    not isinstance(payload, dict)
                    or type(payload.get("total_count")) is not int
                    or payload["total_count"] < 0
                ):
                    raise ValueError
                if inventory and payload["total_count"] > 1000:
                    raise GitHubError("github_inventory_limit")
                batch = payload["repositories"] if inventory else payload
                if not isinstance(batch, list) or len(batch) > 100:
                    raise ValueError
                items.extend(batch)
                if len(items) > bound:
                    raise GitHubError(
                        "github_file_limit" if not inventory else "github_inventory_limit"
                    )
                if not link or 'rel="next"' not in link:
                    if inventory and payload["total_count"] != len(items):
                        raise ValueError
                    return items
                if len(link) > 8192:
                    raise ValueError
                matches = re.findall(r'<([^>]+)>;\s*rel="next"', link)
                if len(matches) != 1:
                    raise ValueError
                target = urlsplit(matches[0])
                if (
                    target.scheme != "https"
                    or target.netloc != "api.github.com"
                    or target.path != path
                    or target.fragment
                    or parse_qs(target.query) != {"per_page": ["100"], "page": [str(page + 1)]}
                ):
                    raise ValueError
            except (ValueError, KeyError, TypeError, RecursionError):
                raise GitHubError("invalid_github_pagination") from None
        raise GitHubError("github_pagination_limit")

    def repositories(self, installation_id: int) -> tuple[GitHubRepository, ...]:
        try:
            records = TypeAdapter(list[RepositoryData]).validate_python(
                self._pages(installation_id, None, "/installation/repositories", inventory=True)
            )
            if len({record.id for record in records}) != len(records):
                raise ValueError
            return tuple(_repo(record) for record in records)
        except (ValueError, ValidationError):
            raise GitHubError("invalid_github_response") from None

    @staticmethod
    def _path(repository: GitHubRepository) -> str:
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", repository.owner)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repository.name)
            or repository.name in {".", ".."}
            or not 0 < repository.id < 2**63
        ):
            raise GitHubError("invalid_github_identity")
        return f"/repos/{quote(repository.owner, safe='')}/{quote(repository.name, safe='')}"

    def repository(
        self, installation_id: int, repository_id: int, owner: str, name: str
    ) -> GitHubRepository:
        path = self._path(GitHubRepository(repository_id, 1, owner, name, True))
        raw, _ = self._get(installation_id, repository_id, path)
        record = _parse(raw, RepositoryData)
        if record.id != repository_id:
            raise GitHubError("invalid_github_identity")
        return _repo(record)

    def pull_request(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> GitHubPullRequest:
        if not 0 < number <= 2147483647:
            raise GitHubError("invalid_github_identity")
        raw, _ = self._get(
            installation_id, repository.id, f"{self._path(repository)}/pulls/{number}"
        )
        data = _parse(raw, PullRequestData)
        if data.base.repo is None or data.base.repo.id != repository.id or data.number != number:
            raise GitHubError("invalid_github_identity")
        return GitHubPullRequest(
            data.id,
            data.number,
            repository.id,
            data.head.repo.id if data.head.repo else None,
            data.base.sha,
            data.head.sha,
            data.state,
            data.draft,
            data.changed_files,
        )

    def _reviewable(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> GitHubPullRequest:
        pr = self.pull_request(installation_id, repository, number)
        if pr.head_repository_id != repository.id or pr.draft or pr.state != "open":
            raise GitHubError("pull_request_not_reviewable")
        if pr.changed_files > self.max_files:
            raise GitHubError("github_file_limit")
        return pr

    def files(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[GitHubFile, ...]:
        pr = self._reviewable(installation_id, repository, number)
        try:
            data = TypeAdapter(list[FileData]).validate_python(
                self._pages(
                    installation_id, repository.id, f"{self._path(repository)}/pulls/{number}/files"
                )
            )
            if len(data) != pr.changed_files or len({item.filename for item in data}) != len(data):
                raise ValueError
        except (ValueError, ValidationError):
            raise GitHubError("invalid_github_response") from None
        self._same_revision(pr, self._reviewable(installation_id, repository, number))
        return tuple(
            GitHubFile(item.sha, item.filename, item.status, item.additions, item.deletions)
            for item in data
        )

    @staticmethod
    def _same_revision(before: GitHubPullRequest, after: GitHubPullRequest) -> None:
        if (before.id, before.base_sha, before.head_sha) != (
            after.id,
            after.base_sha,
            after.head_sha,
        ):
            raise GitHubError("github_revision_changed", retry_at=datetime.now(UTC))

    def diff(self, installation_id: int, repository: GitHubRepository, number: int) -> bytes:
        pr = self._reviewable(installation_id, repository, number)
        raw, _ = self._get(
            installation_id,
            repository.id,
            f"{self._path(repository)}/pulls/{number}",
            accept="application/vnd.github.diff",
            limit=self.max_diff_bytes,
        )
        self._same_revision(pr, self._reviewable(installation_id, repository, number))
        return raw

    def head_commit(self, installation_id: int, repository: GitHubRepository, sha: str) -> str:
        self._sha(sha)
        raw, _ = self._get(
            installation_id, repository.id, f"{self._path(repository)}/commits/{sha}"
        )
        try:
            if json.loads(raw)["sha"] != sha:
                raise ValueError
        except (ValueError, KeyError, TypeError, RecursionError):
            raise GitHubError("invalid_github_response") from None
        return sha

    @staticmethod
    def _sha(sha: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", sha):
            raise GitHubError("invalid_github_identity")

    def blob(self, installation_id: int, repository: GitHubRepository, sha: str) -> bytes:
        self._sha(sha)
        raw, _ = self._get(
            installation_id,
            repository.id,
            f"{self._path(repository)}/git/blobs/{sha}",
            limit=self.max_file_bytes * 2 + 4096,
        )
        try:
            data = json.loads(raw)
            if (
                data["sha"] != sha
                or data["encoding"] != "base64"
                or type(data["size"]) is not int
                or not 0 <= data["size"] <= self.max_file_bytes
            ):
                raise ValueError
            content = base64.b64decode("".join(data["content"].splitlines()), validate=True)
            digest = hashlib.sha1 if len(sha) == 40 else hashlib.sha256
            if (
                len(content) != data["size"]
                or digest(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
                != sha
            ):
                raise ValueError
            return content
        except (ValueError, KeyError, TypeError, RecursionError, AttributeError):
            raise GitHubError("invalid_or_oversized_blob") from None
