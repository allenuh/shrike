"""One bounded Responses request. Transport is injectable; no SDK/HTTP retries."""

import json
import logging
import time

import httpx2 as httpx
from pydantic import SecretStr

from shrike.application.prompts import payload
from shrike.domain.review import ModelReply, ReviewError


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        model: str,
        key: SecretStr,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30,
    ) -> None:
        if not key.get_secret_value() or key.get_secret_value().startswith("<"):
            raise ReviewError("credentials_missing")
        self.model = model
        self.timeout = timeout
        for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
            logging.getLogger(name).disabled = True
        self.client = httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=5),
            headers={
                "Authorization": f"Bearer {key.get_secret_value()}",
                "Accept-Encoding": "identity",
            },
        )

    def close(self) -> None:
        self.client.close()

    def review(self, context: str, max_output_tokens: int) -> ModelReply:
        started = time.monotonic()
        try:
            with self.client.stream(
                "POST",
                "https://api.openai.com/v1/responses",
                json=payload(self.model, context, max_output_tokens),
            ) as response:
                if response.status_code == 429:
                    raise ReviewError("provider_rate_limited")
                if response.status_code in (401, 403):
                    raise ReviewError("provider_unauthorized")
                if response.status_code != 200:
                    raise ReviewError("provider_failed")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ReviewError("provider_encoding")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 262144 or time.monotonic() - started > self.timeout:
                        raise ReviewError("provider_response_limit")
            raw = json.loads(body)
            if raw.get("model") != self.model:
                raise ReviewError("provider_incomplete")
            texts = [
                part["text"]
                for item in raw["output"]
                if item.get("type") == "message"
                for part in item["content"]
                if part.get("type") == "output_text"
            ]
            usage = raw.get("usage") or {}
            tokens = [usage.get("input_tokens"), usage.get("output_tokens")]
            if any(n is not None and (type(n) is not int or not 0 <= n <= 1000000) for n in tokens):
                raise ReviewError("provider_invalid_usage")
            text = texts[0] if len(texts) == 1 and raw.get("status") == "completed" else ""
            return ModelReply(
                text=text, model=self.model, input_tokens=tokens[0], output_tokens=tokens[1]
            )
        except httpx.TimeoutException:
            raise ReviewError("provider_timeout") from None
        except (httpx.RequestError, ValueError, KeyError, TypeError):
            raise ReviewError("provider_failed") from None
