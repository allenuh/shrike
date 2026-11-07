/** Synthetic read-only seed. Imported only by server routes and offline tests. */
import { createHash } from "node:crypto";
import type {
  Finding,
  Metrics,
  Operations,
  Policy,
  Repository,
  Review,
  ReviewDetail,
} from "./contracts";

export const DEMO_AS_OF = "2026-11-07T15:00:00.000Z";
const id = (number: number) =>
  `00000000-0000-4000-8000-${number.toString().padStart(12, "0")}`;
const sha = (number: number) =>
  createHash("sha1").update(`shrike-public-synthetic-${number}`).digest("hex");
const states: Review["state"][] = [
  "completed",
  "running",
  "completed",
  "completed",
  "failed",
  "completed",
  "pending",
  "completed",
  "completed",
  "canceled",
  "completed",
  "completed",
  "failed",
  "completed",
  "completed",
  "completed",
  "completed",
  "completed",
];
export const demoRepositories: Repository[] = [
  {
    id: id(1),
    owner: "shrike-demo",
    name: "payments-api",
    private: true,
    installation_github_id: 710001,
    latest_state: "completed",
    review_count: 6,
  },
  {
    id: id(2),
    owner: "shrike-demo",
    name: "developer-cli",
    private: false,
    installation_github_id: 710001,
    latest_state: "running",
    review_count: 6,
  },
  {
    id: id(3),
    owner: "shrike-demo",
    name: "web-platform",
    private: true,
    installation_github_id: 710001,
    latest_state: "completed",
    review_count: 6,
  },
];
export const demoReviews: Review[] = states.map((state, index) => {
  const repository = demoRepositories[index % 3];
  const time = new Date(
    Date.parse(DEMO_AS_OF) - index * 19 * 60 * 60_000 - 12 * 60_000,
  );
  return {
    id: id(100 + index),
    repository_id: repository.id,
    repository_owner: repository.owner,
    repository_name: repository.name,
    pr_number: 248 - index,
    head_sha: sha(index),
    state,
    created_at: time.toISOString(),
    started_at:
      state === "pending"
        ? null
        : new Date(time.getTime() + 2000).toISOString(),
    finished_at: ["completed", "failed", "canceled"].includes(state)
      ? new Date(time.getTime() + 18_000 + index * 1000).toISOString()
      : null,
    finding_count: state === "completed" ? [3, 1, 0, 2][index % 4] : 0,
  };
});
const examples = [
  {
    severity: "high" as const,
    source: "semgrep" as const,
    rule_id: "demo.parameterized-query",
    path: "src/storage.py",
    line: 18,
    explanation:
      "User input is interpolated into a database query. A crafted account identifier can change the query’s meaning.",
    suggestion:
      "Pass the account identifier as a bound query parameter instead of formatting it into SQL.",
    snippet: 'query = f"SELECT * FROM accounts WHERE id = {account_id}"',
  },
  {
    severity: "medium" as const,
    source: "llm" as const,
    rule_id: "demo.mock-review",
    path: "src/payments.py",
    line: 31,
    explanation:
      "A zero denominator reaches the fee calculation and raises ZeroDivisionError before the payment can be processed.",
    suggestion:
      "Validate the denominator before calculating the fee and return a clear validation error.",
    snippet: "fee = amount / transaction_count",
  },
  {
    severity: "low" as const,
    source: "ruff" as const,
    rule_id: "F401",
    path: "src/payments.py",
    line: 3,
    explanation: "The imported module is never used in this file.",
    suggestion:
      "Remove the unused import to keep the module’s dependencies clear.",
    snippet: "import decimal",
  },
];
function findingsFor(review: Review): Finding[] {
  return examples.slice(0, review.finding_count).map((finding, index) => ({
    ...finding,
    id: id(1000 + Number(review.id.slice(-12)) * 10 + index),
    github_url: `https://github.com/${review.repository_owner}/${review.repository_name}/blob/${review.head_sha}/${finding.path}#L${finding.line}`,
  }));
}
function page<T>(items: T[], query: URLSearchParams, context: string) {
  const limit = Math.min(100, Math.max(1, Number(query.get("limit") || 8)));
  const cursor = query.get("cursor");
  let offset = 0;
  if (cursor) {
    const [bound, raw] = Buffer.from(cursor, "base64url").toString().split(":");
    if (bound !== context || !/^\d+$/.test(raw || ""))
      throw new Error("invalid_cursor");
    offset = Number(raw);
  }
  return {
    items: items.slice(offset, offset + limit),
    next_cursor:
      offset + limit < items.length
        ? Buffer.from(`${context}:${offset + limit}`).toString("base64url")
        : null,
  };
}
function metrics(query: URLSearchParams): Metrics {
  const window = Math.min(
    90,
    Math.max(1, Number(query.get("window_days") || 30)),
  );
  const reviews = demoReviews.filter(
    (r) =>
      Date.parse(r.created_at) >= Date.parse(DEMO_AS_OF) - window * 86400_000,
  );
  const completed = reviews.filter((r) => r.state === "completed");
  const failed = reviews.filter((r) => r.state === "failed");
  const findings = reviews.flatMap(findingsFor);
  const severity_counts: Metrics["severity_counts"] = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  };
  findings.forEach((f) => severity_counts[f.severity]++);
  const days = new Map<string, number>();
  reviews.forEach((r) => {
    const day = r.created_at.slice(0, 10);
    days.set(day, (days.get(day) || 0) + 1);
  });
  return {
    window_days: window,
    as_of: DEMO_AS_OF,
    repositories: demoRepositories.length,
    reviews: reviews.length,
    findings: findings.length,
    completed: completed.length,
    failed: failed.length,
    success_rate: (completed.length / (completed.length + failed.length)) * 100,
    failure_rate: (failed.length / (completed.length + failed.length)) * 100,
    average_processing_seconds:
      completed.reduce(
        (sum, r) =>
          sum + (Date.parse(r.finished_at!) - Date.parse(r.started_at!)) / 1000,
        0,
      ) / completed.length,
    severity_counts,
    daily_reviews: [...days].map(([date, count]) => ({ date, reviews: count })),
  };
}
export function demoData(path: string, query: URLSearchParams): unknown {
  if (path === "auth/session")
    return { login: "demo-maintainer", mode: "demo" };
  if (path === "v1/dashboard/metrics") return metrics(query);
  if (path === "v1/dashboard/repositories") {
    const items = demoRepositories.filter((r) =>
      `${r.owner}/${r.name}`.includes(query.get("search") || ""),
    );
    return page(items, query, `repositories-${query.get("search") || ""}`);
  }
  if (path === "v1/dashboard/reviews") {
    const items = demoReviews.filter(
      (r) =>
        (!query.get("state") || r.state === query.get("state")) &&
        (!query.get("repository_id") ||
          r.repository_id === query.get("repository_id")) &&
        (!query.get("pull_request_number") ||
          String(r.pr_number) === query.get("pull_request_number")),
    );
    return page(
      items,
      query,
      `reviews-${query.get("state") || ""}-${query.get("repository_id") || ""}-${query.get("pull_request_number") || ""}`,
    );
  }
  if (path.startsWith("v1/dashboard/reviews/")) {
    const review = demoReviews.find((r) => r.id === path.split("/").at(-1));
    if (!review) return null;
    const findings = findingsFor(review).filter(
      (f) =>
        (!query.get("severity") || f.severity === query.get("severity")) &&
        (!query.get("source") || f.source === query.get("source")),
    );
    const result: ReviewDetail = {
      review,
      findings: page(
        findings,
        query,
        `findings-${review.id}-${query.get("severity") || ""}-${query.get("source") || ""}`,
      ),
      attempts: review.started_at
        ? [
            {
              attempt: 1,
              state: review.state,
              duration_ms: review.finished_at
                ? Date.parse(review.finished_at) - Date.parse(review.started_at)
                : 0,
              provider: "mock",
              error_code: review.state === "failed" ? "scanner_timeout" : null,
            },
          ]
        : [],
      coverage:
        review.state === "completed"
          ? { selected_files: 4, skipped_files: 1, changed_lines: 82 }
          : null,
      analysis_status: review.state === "completed" ? "partial" : null,
      publication: {
        state: "not_requested",
        review_id: null,
        comment_ids: [],
        reason: null,
      },
    };
    return result;
  }
  if (path === "v1/dashboard/operations") {
    const data: Operations = {
      as_of: DEMO_AS_OF,
      database: "synthetic",
      pending: 1,
      running: 1,
      active_leases: 1,
      expired_leases: 0,
      retry_wait: 0,
      undispatched: 1,
      uncertain_publications: 0,
      oldest_pending_seconds: 42,
      worker_heartbeat: "unavailable",
      broker_reachability: "unavailable",
    };
    return data;
  }
  if (path === "v1/dashboard/settings") {
    const policy: Policy = {
      authentication: "synthetic_demo",
      ai_provider: "mock",
      publishing: "report_only",
      minimum_confidence: 0.85,
      maximum_published_findings: 10,
      supported_language: "Python",
    };
    return policy;
  }
  return null;
}
