"""Bounded process-only fixture cache; never usable for hosted requests."""

from collections import OrderedDict

from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.review import Report, ReviewError, ReviewInput


class MemoryAnalysisStore:
    def __init__(self, scope: ReadScope) -> None:
        self.scope = scope
        self.reports: OrderedDict[tuple[int, int, str], Report] = OrderedDict()

    def authorize(self, request: ReviewInput) -> None:
        if RepositoryGrant(request.installation_id, request.repository_id) not in self.scope.grants:
            raise ReviewError("repository_denied")

    def cached(self, request: ReviewInput, digest: str) -> Report | None:
        self.authorize(request)
        return self.reports.get((request.installation_id, request.repository_id, digest))

    def save(self, request: ReviewInput, digest: str, report: Report) -> None:
        self.authorize(request)
        self.reports[(request.installation_id, request.repository_id, digest)] = report
        if len(self.reports) > 128:
            self.reports.popitem(last=False)
