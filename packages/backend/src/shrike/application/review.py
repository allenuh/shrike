import hashlib
import json
import re
import threading
import time

from pydantic import ValidationError

from shrike.application.diff import select_files
from shrike.application.evidence import eval_input
from shrike.application.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_context, payload
from shrike.domain.ai_budget import PriceProfile, dollars
from shrike.domain.review import (
    Finding,
    ModelOutput,
    Report,
    ReviewError,
    ReviewInput,
    ReviewLimits,
)
from shrike.ports.ai_budget import SpendingLedger
from shrike.ports.execution import RequestAdmission
from shrike.ports.review import AnalysisStore, Analyzer, LLMProvider


class ReviewEngine:
    def __init__(
        self,
        analyzer: Analyzer,
        provider: LLMProvider,
        store: AnalysisStore,
        limits: ReviewLimits | None = None,
        *,
        ledger: SpendingLedger | None = None,
        pricing: PriceProfile | None = None,
        live_enabled: bool = False,
        allow_private: bool = False,
        model_allowlist: tuple[str, ...] = (),
        admission: RequestAdmission | None = None,
    ) -> None:
        self.analyzer, self.provider, self.store = analyzer, provider, store
        self.limits = limits or ReviewLimits()
        self.ledger, self.pricing = ledger, pricing
        self.live_enabled, self.allow_private = live_enabled, allow_private
        self.model_allowlist = model_allowlist
        self.admission = admission
        self._concurrency = threading.BoundedSemaphore(self.limits.max_concurrency)
        self._repositories = tuple(threading.Lock() for _ in range(64))

    def analyze(self, request: ReviewInput, *, dry_run: bool = False) -> Report:
        with self._concurrency, self._repositories[request.repository_id % 64]:
            return self._analyze(request, dry_run=dry_run)

    def _analyze(self, request: ReviewInput, *, dry_run: bool = False) -> Report:
        start = time.monotonic()
        self.store.authorize(request)
        files, coverage = select_files(request, self.limits)
        context, count, omitted = build_context(files, self.limits)
        coverage = coverage.model_copy(update={"context_lines": count})
        # Count complete serialized input bytes plus a deliberately conservative framing ceiling.
        # Live dispatch additionally requires explicit model-specific approval of this bound.
        serialized = json.dumps(
            payload(self.provider.model, context, self.limits.max_output_tokens),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        framing = self.pricing.framing_token_bound if self.pricing else 4096
        token_bound = len(serialized.encode()) + framing
        digest = hashlib.sha256(
            json.dumps(
                {
                    "input": request.model_dump(mode="json"),
                    "limits": self.limits.model_dump(mode="json"),
                    "prompt": PROMPT_VERSION,
                    "instructions": SYSTEM_PROMPT,
                    "schema": ModelOutput.model_json_schema(),
                    "provider": self.provider.name,
                    "model": self.provider.model,
                    "analyzer": self.analyzer.version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if not dry_run and (cached := self.store.cached(request, digest)) is not None:
            return cached.model_copy(
                update={"cache_hit": True, "latency_ms": int((time.monotonic() - start) * 1000)}
            )
        candidates = [
            (candidate, "ruff") for file in files for candidate in self.analyzer.analyze(file)
        ]
        reason: str | None = None
        retry_at = None
        estimated: int | None = 0 if self.provider.name == "mock" else None
        actual: int | None = None
        input_tokens = output_tokens = None
        warning = False
        try:
            if not files or not count:
                raise ReviewError("no_eligible_context")
            if (
                token_bound > self.limits.max_input_tokens
                or len(serialized.encode()) > self.limits.max_context_bytes
            ):
                raise ReviewError("context_token_limit")
            if self.provider.name != "mock":
                if self.pricing is None:
                    raise ReviewError("pricing_unavailable")
                self.pricing.check(self.provider.model, live=not dry_run)
                estimated = self.pricing.micro_usd(token_bound, self.limits.max_output_tokens)
                if not dry_run:
                    if not self.live_enabled or self.provider.model not in self.model_allowlist:
                        raise ReviewError("live_not_enabled")
                    if request.private and not self.allow_private:
                        raise ReviewError("private_egress_denied")
                    if self.ledger is None:
                        raise ReviewError("ledger_unavailable")
                    self.store.authorize(request)
            if not dry_run and self.admission is not None:
                self.admission.acquire()
            if self.provider.name != "mock" and not dry_run:
                assert (
                    self.ledger is not None and self.pricing is not None and estimated is not None
                )
                warning = self.ledger.reserve(
                    digest,
                    estimated,
                    self.pricing,
                    token_bound,
                    self.limits.max_output_tokens,
                    hashlib.sha256(
                        f"{request.installation_id}:{request.repository_id}:"
                        f"{request.base_sha}:{request.head_sha}".encode()
                    ).hexdigest(),
                )
            if not dry_run and files and count:
                try:
                    reply = self.provider.review(context, self.limits.max_output_tokens)
                except ReviewError:
                    if self.provider.name != "mock" and self.ledger is not None:
                        self.ledger.settle(digest, None, None)
                    raise
                input_tokens, output_tokens = reply.input_tokens, reply.output_tokens
                if self.provider.name != "mock" and self.ledger is not None:
                    actual = self.ledger.settle(digest, input_tokens, output_tokens)
                if reply.model != self.provider.model or len(reply.text.encode()) > 131072:
                    raise ReviewError("model_output_invalid")
                output = ModelOutput.model_validate_json(reply.text, strict=True)
                candidates.extend((candidate, self.provider.name) for candidate in output.findings)
        except ValidationError:
            reason = "model_output_invalid"
        except ReviewError as exc:
            reason = exc.code
            retry_at = exc.retry_at
        selected = {file.path: file for file in files}
        # Only evidence actually shown to the model can support its findings.
        shown = {
            (f["path"], line["line"]): line["text"]
            for f in json.loads(context)["files"]
            for line in f["lines"]
            if line["changed"]
        }
        normalized: dict[str, Finding] = {}
        rejected = 0
        for candidate, analyzer in candidates:
            file = selected.get(candidate.path)
            line = (
                file.content.splitlines()[candidate.line - 1]
                if (file is not None and candidate.line in file.changed_lines)
                else None
            )
            text = candidate.problem + candidate.suggestion
            if (
                line is None
                or not candidate.evidence.strip()
                or candidate.evidence not in line
                or (analyzer != "ruff" and shown.get((candidate.path, candidate.line)) != line)
                or candidate.confidence < 0.7
                or re.search(r"<[^>]+>|https?://|javascript:|data:", text, re.I)
            ):
                rejected += 1
                continue
            if candidate.category == "security":
                if candidate.rule != "unsafe-eval-input" or not eval_input(line):
                    rejected += 1
                    continue
                candidate = candidate.model_copy(
                    update={
                        "problem": "Evaluating input executes arbitrary Python expressions",
                        "suggestion": "Parse input with an explicit data parser instead of eval",
                        "severity": "high",
                        "confidence": min(candidate.confidence, 0.95),
                    }
                )
            # Explicit rule identity merges equivalent static/model observations; free-form rules
            # additionally include normalized explanation to avoid merging unrelated claims.
            issue = (
                candidate.rule
                if candidate.rule
                in {
                    "F821",
                    "F823",
                    "F601",
                    "F602",
                    "F631",
                    "B006",
                    "B012",
                    "division-by-zero",
                    "unsafe-eval-input",
                }
                else (candidate.rule + re.sub(r"\W+", " ", candidate.problem.lower()).strip())
            )
            fingerprint = hashlib.sha256(
                f"{candidate.path}:{candidate.line}:{issue}".encode()
            ).hexdigest()
            old = normalized.get(fingerprint)
            severity = candidate.severity
            if analyzer != "ruff" and severity == "critical":
                severity = "high"
            finding = Finding(
                **candidate.model_dump(exclude={"severity"}),
                severity=severity,
                analyzers=(analyzer,),
                fingerprint=fingerprint,
            )
            if old:
                finding = old.model_copy(
                    update={
                        "analyzers": tuple(sorted(set(old.analyzers + (analyzer,)))),
                        "confidence": max(old.confidence, candidate.confidence),
                    }
                )
            normalized[fingerprint] = finding
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings = sorted(
            normalized.values(), key=lambda f: (severity_order[f.severity], f.path, f.line, f.rule)
        )
        truncated = len(findings) > self.limits.max_findings
        status = (
            "dry_run"
            if dry_run
            else (
                "static_only"
                if reason
                else (
                    "partial"
                    if coverage.skipped or omitted or truncated or rejected
                    else "completed"
                )
            )
        )
        report = Report(
            retry_at=retry_at,
            analysis_hash=digest,
            pricing_verified_at=None
            if self.pricing is None
            else self.pricing.verified_at.isoformat(),
            status=status,
            summary=f"{min(len(findings), self.limits.max_findings)} validated findings; "
            f"{len(files)} Python files selected; AI provider {self.provider.name}",
            findings=tuple(findings[: self.limits.max_findings]),
            coverage=coverage,
            provider=self.provider.name,
            model=self.provider.model,
            prompt_version=PROMPT_VERSION,
            analyzer_version=self.analyzer.version,
            input_token_estimate=token_bound,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=None if estimated is None else dollars(estimated),
            reported_usage_cost_usd=None if actual is None else dollars(actual),
            latency_ms=int((time.monotonic() - start) * 1000),
            reason=reason or ("budget_warning" if warning else None),
            rejected_findings=rejected,
        )
        # Degraded results are not cached. Paid-call identities still prevent accidental replay.
        if not dry_run and reason is None:
            self.store.save(request, digest, report)
        return report
