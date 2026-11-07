"""Deterministic synthetic rule provider; no model intelligence claim."""

import json

from shrike.application.evidence import zero_division
from shrike.domain.review import Candidate, ModelOutput, ModelReply


class MockProvider:
    name = "mock"
    model = "mock-v1"

    def review(self, context: str, max_output_tokens: int) -> ModelReply:
        findings = []
        for file in json.loads(context)["files"]:
            for line in file["lines"]:
                if line["changed"] and zero_division(line["text"]):
                    findings.append(
                        Candidate(
                            category="correctness",
                            severity="high",
                            confidence=0.99,
                            path=file["path"],
                            line=line["line"],
                            problem="Division by literal zero raises ZeroDivisionError",
                            suggestion="Use a nonzero denominator or reject the invalid operation",
                            evidence=line["text"][:500],
                            rule="division-by-zero",
                        )
                    )
        return ModelReply(
            text=ModelOutput(findings=findings[:100]).model_dump_json(), model=self.model
        )
