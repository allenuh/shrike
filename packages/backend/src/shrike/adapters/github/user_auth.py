"""GitHub App user authorization; no redirects, retries, payload logs or refresh tokens."""

import json
import logging
import re
from urllib.parse import parse_qs, urlsplit

import httpx2 as httpx
from pydantic import BaseModel, Field, SecretStr

from shrike.adapters.github.client import API_VERSION
from shrike.domain.access import RepositoryGrant
from shrike.domain.auth import AuthenticationError, UserCredential, UserIdentity


class IdentityData(BaseModel):
    id: int = Field(gt=0, lt=2**63, strict=True)
    login: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,99}$")


class GitHubUserAuthorization:
    def __init__(
        self,
        app_id: int,
        client_id: str,
        client_secret: SecretStr,
        callback: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id, self.client_id, self.secret, self.callback = (
            app_id,
            client_id,
            client_secret,
            callback,
        )
        for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
            logging.getLogger(name).disabled = True
        self.http = httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=5,
            headers={
                "Accept": "application/json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "Shrike/0.1",
            },
        )

    def close(self) -> None:
        self.http.close()

    def _json(
        self,
        method: str,
        url: str,
        *,
        token: SecretStr | None = None,
        data: dict[str, str] | None = None,
    ) -> tuple[object, str]:
        try:
            headers = {"Authorization": "Bearer " + token.get_secret_value()} if token else {}
            with self.http.stream(method, url, headers=headers, data=data) as response:
                if response.status_code in {401, 403, 404}:
                    raise AuthenticationError()
                if response.status_code != 200:
                    raise AuthenticationError("authorization_unavailable")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if len(raw) + len(chunk) > 2097152:
                        raise AuthenticationError("authorization_unavailable")
                    raw.extend(chunk)
                return json.loads(raw), response.headers.get("link", "")
        except AuthenticationError:
            raise
        except Exception:
            raise AuthenticationError("authorization_unavailable") from None

    def exchange(self, code: str, verifier: str) -> UserCredential:
        value, _ = self._json(
            "POST",
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": self.client_id,
                "client_secret": self.secret.get_secret_value(),
                "code": code,
                "redirect_uri": self.callback,
                "code_verifier": verifier,
            },
        )
        if not isinstance(value, dict):
            raise AuthenticationError()
        token, expiry = value.get("access_token"), value.get("expires_in", 3600)
        if (
            not isinstance(token, str)
            or not 1 <= len(token) <= 16384
            or value.get("token_type", "").lower() != "bearer"
            or type(expiry) is not int
            or expiry <= 0
        ):
            raise AuthenticationError()
        return UserCredential(SecretStr(token), min(3600, expiry))

    def identity(self, token: SecretStr) -> UserIdentity:
        value, _ = self._json("GET", "https://api.github.com/user", token=token)
        try:
            identity = IdentityData.model_validate(value)
            return UserIdentity(identity.id, identity.login)
        except Exception:
            raise AuthenticationError() from None

    def _pages(self, path: str, key: str, token: SecretStr) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for page in range(1, 12):
            value, link = self._json(
                "GET", f"https://api.github.com{path}?per_page=100&page={page}", token=token
            )
            if not isinstance(value, dict) or not isinstance(value.get(key), list):
                raise AuthenticationError("authorization_unavailable")
            batch = value[key]
            if (
                len(batch) > 100
                or any(not isinstance(item, dict) for item in batch)
                or type(value.get("total_count")) is not int
                or value["total_count"] > 1000
            ):
                raise AuthenticationError("authorization_unavailable")
            records.extend(batch)
            if len(records) > 1000:
                raise AuthenticationError("authorization_unavailable")
            if 'rel="next"' not in link:
                if len(records) != value["total_count"]:
                    raise AuthenticationError("authorization_unavailable")
                return records
            matches = re.findall(r'<([^>]+)>;\s*rel="next"', link)
            if len(matches) != 1 or len(link) > 8192:
                raise AuthenticationError("authorization_unavailable")
            target = urlsplit(matches[0])
            if (
                target.scheme != "https"
                or target.netloc != "api.github.com"
                or target.path != path
                or target.fragment
                or parse_qs(target.query) != {"page": [str(page + 1)], "per_page": ["100"]}
            ):
                raise AuthenticationError("authorization_unavailable")
        raise AuthenticationError("authorization_unavailable")

    def grants(self, token: SecretStr) -> tuple[RepositoryGrant, ...]:
        grants: set[RepositoryGrant] = set()
        for installation in self._pages("/user/installations", "installations", token):
            installation_id = installation.get("id")
            if type(installation_id) is not int or not 0 < installation_id < 2**63:
                raise AuthenticationError("authorization_unavailable")
            if installation.get("app_id") != self.app_id or installation.get("suspended_at"):
                continue
            for repo in self._pages(
                f"/user/installations/{installation_id}/repositories", "repositories", token
            ):
                repo_id = repo.get("id")
                if type(repo_id) is not int or not 0 < repo_id < 2**63:
                    raise AuthenticationError("authorization_unavailable")
                grants.add(RepositoryGrant(installation_id, repo_id))
                if len(grants) > 1000:
                    raise AuthenticationError("authorization_unavailable")
        return tuple(
            sorted(grants, key=lambda g: (g.installation_github_id, g.repository_github_id))
        )
