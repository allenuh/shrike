"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { detailSchema, type Finding } from "@/lib/contracts";
import { Icon } from "./icons";
import {
  Badge,
  duration,
  Empty,
  ErrorState,
  GitHubLink,
  Heading,
  Loading,
  Pagination,
  Panel,
  Select,
  shortDate,
  useFilters,
} from "./ui";

export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className="finding-card" id={`finding-${finding.id}`}>
      <div className="finding-card-top">
        <div>
          <Badge value={finding.severity} />
          <span className="source-label">
            {finding.source === "llm" ? "Mock / LLM" : finding.source}
          </span>
          <span className="mono rule-label">{finding.rule_id}</span>
        </div>
        <a
          className="finding-anchor"
          href={`#finding-${finding.id}`}
          aria-label={`Link to finding at line ${finding.line}`}
        >
          L{finding.line}
        </a>
      </div>
      <h3>{finding.explanation}</h3>
      {finding.snippet ? (
        <div className="source-snippet">
          <div className="snippet-caption">
            <Icon name="file" size={13} />
            Evidence excerpt · line {finding.line}
            <span>Python</span>
          </div>
          <pre
            tabIndex={0}
            aria-label={`Source evidence at ${finding.path} line ${finding.line}`}
          >
            <code>
              <span className="line-number" aria-hidden="true">
                {finding.line}
              </span>
              {finding.snippet}
            </code>
          </pre>
        </div>
      ) : (
        <div className="snippet-unavailable">
          No source excerpt was retained for this finding.
        </div>
      )}
      {finding.suggestion && (
        <div className="suggestion">
          <span>
            <Icon name="arrow" size={14} />
            Suggested action
          </span>
          <p>{finding.suggestion}</p>
        </div>
      )}
      <div className="finding-card-footer">
        <span className="muted">Advisory finding · verify in context</span>
        <GitHubLink href={finding.github_url}>View source</GitHubLink>
      </div>
    </article>
  );
}
export function ReviewDetail({ id }: { id: string }) {
  const filters = useFilters();
  const result = useApi(
    `v1/dashboard/reviews/${encodeURIComponent(id)}?${filters.apiQuery(["severity", "source", "cursor"], 20)}`,
    detailSchema,
  );
  if (result.error)
    return (
      <ErrorState error={result.error} retry={() => void result.mutate()} />
    );
  if (!result.data) return <Loading label="Loading review findings" />;
  const data = result.data;
  const review = data.review;
  const files = Object.groupBy(data.findings.items, (f) => f.path);
  return (
    <>
      <Link href="/reviews" className="back-link">
        <Icon name="arrow" size={14} />
        Back to reviews
      </Link>
      <Heading
        eyebrow={`${review.repository_owner} / ${review.repository_name}`}
        title={`Pull request #${review.pr_number}`}
        description={`Reviewed commit ${review.head_sha.slice(0, 7)} · ${shortDate(review.created_at)} UTC`}
        action={
          <GitHubLink
            href={`https://github.com/${encodeURIComponent(review.repository_owner)}/${encodeURIComponent(review.repository_name)}/pull/${review.pr_number}`}
          >
            Open pull request
          </GitHubLink>
        }
      />
      <div className="review-summary-strip">
        <div>
          <span className="meta-label">Analysis</span>
          <Badge value={review.state} />
        </div>
        <div>
          <span className="meta-label">Findings</span>
          <strong>{review.finding_count}</strong>
        </div>
        <div>
          <span className="meta-label">Processing</span>
          <strong className="mono">{duration(review)}</strong>
        </div>
        <div>
          <span className="meta-label">Coverage</span>
          <strong>
            {data.coverage
              ? `${data.coverage.selected_files} files · ${data.coverage.changed_lines} changed lines`
              : "Not available"}
          </strong>
        </div>
        <div>
          <span className="meta-label">Publication</span>
          <Badge value={data.publication?.state || "not_requested"} />
        </div>
      </div>
      {((data.analysis_status && data.analysis_status !== "completed") ||
        (data.coverage?.skipped_files || 0) > 0) && (
        <div className="coverage-notice">
          <Icon name="alert" size={17} />
          <div>
            <strong>
              Partial coverage · {data.analysis_status?.replaceAll("_", " ")}
            </strong>
            <p>
              {data.coverage?.skipped_files || 0} files skipped. Findings cover
              the analyzed scope and do not guarantee the rest of the change is
              safe.
            </p>
          </div>
        </div>
      )}
      {data.attempts.some((a) => a.provider === "mock") && (
        <div className="demo-analysis-note">
          <Icon name="shield" size={15} />
          Deterministic mock-assisted analysis. This is a pipeline result, not a
          real model quality assessment.
        </div>
      )}
      <div className="detail-layout">
        <div>
          <div className="findings-heading">
            <h2>
              Findings <span>{review.finding_count}</span>
            </h2>
            <div className="filter-controls">
              <Select
                label="Filter findings by severity"
                value={filters.search.get("severity") || ""}
                onChange={(value) => filters.set({ severity: value })}
                options={[
                  { value: "", label: "All severities" },
                  ...["critical", "high", "medium", "low", "info"].map(
                    (value) => ({
                      value,
                      label: value[0].toUpperCase() + value.slice(1),
                    }),
                  ),
                ]}
              />
              <Select
                label="Filter findings by source"
                value={filters.search.get("source") || ""}
                onChange={(value) => filters.set({ source: value })}
                options={[
                  { value: "", label: "All sources" },
                  { value: "ruff", label: "Ruff" },
                  { value: "semgrep", label: "Semgrep" },
                  { value: "llm", label: "LLM / mock" },
                ]}
              />
            </div>
          </div>
          {data.findings.items.length ? (
            Object.entries(files).map(([path, findings]) => (
              <section className="file-group" key={path}>
                <div className="file-heading">
                  <Icon name="file" size={16} />
                  <h3 className="mono">{path}</h3>
                  <span>{findings?.length}</span>
                </div>
                {findings?.map((finding) => (
                  <FindingCard finding={finding} key={finding.id} />
                ))}
              </section>
            ))
          ) : (
            <Empty
              title={
                review.state === "completed"
                  ? "No findings in this view"
                  : "Analysis has no published results yet"
              }
              description={
                review.state === "failed"
                  ? "This review failed. An absent finding is not a clean result; check the execution details."
                  : review.state !== "completed"
                    ? "Findings become available after analysis completes."
                    : "No stored findings match your filters. This is not a guarantee of correctness."
              }
            />
          )}
          <Pagination
            next={data.findings.next_cursor}
            count={data.findings.items.length}
          />
        </div>
        <aside className="detail-aside">
          <Panel title="Execution trail">
            <div className="attempts">
              {data.attempts.length ? (
                data.attempts.map((attempt) => (
                  <div className="attempt" key={attempt.attempt}>
                    <span className={`attempt-dot attempt-${attempt.state}`} />
                    <div>
                      <strong>Attempt {attempt.attempt}</strong>
                      <Badge value={attempt.state} small />
                      <p>
                        {attempt.provider || "Provider unavailable"} ·{" "}
                        {(attempt.duration_ms / 1000).toFixed(1)}s
                      </p>
                      {attempt.error_code && (
                        <code className="safe-reason">
                          {attempt.error_code}
                        </code>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted">No execution attempt yet.</p>
              )}
            </div>
          </Panel>
          <Panel title="GitHub publication">
            <div className="publication-details">
              <p>
                Publication is independent from analysis and requires explicit
                operator opt-in.
              </p>
              {data.publication?.review_id && (
                <GitHubLink
                  href={`https://github.com/${encodeURIComponent(review.repository_owner)}/${encodeURIComponent(review.repository_name)}/pull/${review.pr_number}#pullrequestreview-${data.publication.review_id}`}
                >
                  Review #{data.publication.review_id}
                </GitHubLink>
              )}
              {data.publication?.reason && (
                <code className="safe-reason">{data.publication.reason}</code>
              )}
              <span className="meta-label">
                No automatic approval or code changes.
              </span>
            </div>
          </Panel>
        </aside>
      </div>
    </>
  );
}
