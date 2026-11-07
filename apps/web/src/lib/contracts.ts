import { z } from "zod";

export const stateSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "canceled",
]);
export const severitySchema = z.enum([
  "critical",
  "high",
  "medium",
  "low",
  "info",
]);
export const sourceSchema = z.enum(["ruff", "semgrep", "llm"]);
export const repositorySchema = z.object({
  id: z.string().uuid(),
  owner: z.string(),
  name: z.string(),
  private: z.boolean(),
  installation_github_id: z.number().int().positive(),
  latest_state: stateSchema.nullable(),
  review_count: z.number().int().nonnegative(),
});
export const reviewSchema = z.object({
  id: z.string().uuid(),
  repository_id: z.string().uuid(),
  repository_owner: z.string(),
  repository_name: z.string(),
  pr_number: z.number().int().positive(),
  head_sha: z.string().regex(/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/),
  state: stateSchema,
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  finding_count: z.number().int().nonnegative(),
});
export const findingSchema = z.object({
  id: z.string().uuid(),
  severity: severitySchema,
  source: sourceSchema,
  rule_id: z.string(),
  path: z.string(),
  line: z.number().int().positive(),
  explanation: z.string(),
  suggestion: z.string().nullable(),
  snippet: z.string().nullable(),
  github_url: z
    .string()
    .url()
    .refine((value) => {
      const url = new URL(value);
      return (
        url.protocol === "https:" &&
        url.hostname === "github.com" &&
        !url.username &&
        !url.password
      );
    }),
});
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable() });
export const detailSchema = z.object({
  review: reviewSchema,
  findings: pageSchema(findingSchema),
  attempts: z.array(
    z.object({
      attempt: z.number(),
      state: stateSchema,
      duration_ms: z.number(),
      provider: z.string().nullable(),
      error_code: z.string().nullable(),
    }),
  ),
  coverage: z
    .object({
      selected_files: z.number(),
      skipped_files: z.number(),
      changed_lines: z.number(),
    })
    .nullable(),
  analysis_status: z
    .enum(["completed", "partial", "static_only", "dry_run"])
    .nullable(),
  publication: z
    .object({
      state: z.string(),
      review_id: z.number().nullable(),
      comment_ids: z.array(z.number()),
      reason: z.string().nullable(),
    })
    .nullable(),
});
export const metricsSchema = z.object({
  window_days: z.number(),
  as_of: z.string(),
  repositories: z.number(),
  reviews: z.number(),
  findings: z.number(),
  completed: z.number(),
  failed: z.number(),
  success_rate: z.number().nullable(),
  failure_rate: z.number().nullable(),
  average_processing_seconds: z.number().nullable(),
  severity_counts: z.record(severitySchema, z.number()),
  daily_reviews: z.array(z.object({ date: z.string(), reviews: z.number() })),
});
export const operationsSchema = z.object({
  as_of: z.string(),
  database: z.string(),
  pending: z.number(),
  running: z.number(),
  active_leases: z.number(),
  expired_leases: z.number(),
  retry_wait: z.number(),
  undispatched: z.number(),
  uncertain_publications: z.number(),
  oldest_pending_seconds: z.number().nullable(),
  worker_heartbeat: z.string(),
  broker_reachability: z.string(),
});
export const policySchema = z.object({
  authentication: z.string(),
  ai_provider: z.string(),
  publishing: z.string(),
  minimum_confidence: z.number(),
  maximum_published_findings: z.number(),
  supported_language: z.string(),
});
export const sessionSchema = z.object({
  login: z.string(),
  mode: z.enum(["demo", "live"]),
});

export type Repository = z.infer<typeof repositorySchema>;
export type Review = z.infer<typeof reviewSchema>;
export type Finding = z.infer<typeof findingSchema>;
export type ReviewDetail = z.infer<typeof detailSchema>;
export type Metrics = z.infer<typeof metricsSchema>;
export type Operations = z.infer<typeof operationsSchema>;
export type Policy = z.infer<typeof policySchema>;
export type UserSession = z.infer<typeof sessionSchema>;
export type Page<T> = { items: T[]; next_cursor: string | null };
