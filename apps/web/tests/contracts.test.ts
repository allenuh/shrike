import { describe, expect, it, vi } from "vitest";
import {
  detailSchema,
  metricsSchema,
  operationsSchema,
  pageSchema,
  policySchema,
  repositorySchema,
  reviewSchema,
} from "@/lib/contracts";
import { demoData, demoReviews } from "@/lib/demo";
import { allowedPath, backendOrigin, forwardedCookies } from "@/lib/proxy";
import { ApiError, request } from "@/lib/api";

describe("typed dashboard contract", () => {
  it("validates all seeded endpoint shapes, details, and metrics denominators", () => {
    const query = new URLSearchParams();
    expect(
      pageSchema(repositorySchema).parse(
        demoData("v1/dashboard/repositories", query),
      ).items,
    ).toHaveLength(3);
    expect(
      pageSchema(reviewSchema).parse(demoData("v1/dashboard/reviews", query))
        .items,
    ).toHaveLength(8);
    expect(
      detailSchema.parse(
        demoData(`v1/dashboard/reviews/${demoReviews[0].id}`, query),
      ).findings.items,
    ).toHaveLength(3);
    const metrics = metricsSchema.parse(
      demoData("v1/dashboard/metrics", query),
    );
    expect(metrics.success_rate).toBeCloseTo(
      (100 * metrics.completed) / (metrics.completed + metrics.failed),
    );
    expect(metrics.findings).toBe(
      Object.values(metrics.severity_counts).reduce((a, b) => a + b, 0),
    );
    expect(
      operationsSchema.parse(demoData("v1/dashboard/operations", query))
        .worker_heartbeat,
    ).toBe("unavailable");
    expect(
      policySchema.parse(demoData("v1/dashboard/settings", query)).publishing,
    ).toBe("report_only");
  });
  it("paginates and binds synthetic cursors to filters", () => {
    const first = pageSchema(reviewSchema).parse(
      demoData("v1/dashboard/reviews", new URLSearchParams("limit=1")),
    );
    const second = pageSchema(reviewSchema).parse(
      demoData(
        "v1/dashboard/reviews",
        new URLSearchParams({ limit: "1", cursor: first.next_cursor! }),
      ),
    );
    expect(first.items[0].id).not.toBe(second.items[0].id);
    expect(() =>
      demoData(
        "v1/dashboard/reviews",
        new URLSearchParams({ state: "failed", cursor: first.next_cursor! }),
      ),
    ).toThrow();
    expect(
      pageSchema(reviewSchema)
        .parse(
          demoData("v1/dashboard/reviews", new URLSearchParams("state=failed")),
        )
        .items.every((r) => r.state === "failed"),
    ).toBe(true);
  });
  it("does not let arbitrary URLs, mutations, or browser bearer tokens through the proxy", () => {
    expect(allowedPath("v1/dashboard/reviews")).toBe(true);
    for (const value of [
      "https://evil.test",
      "../secrets",
      "v1/dashboard/../settings",
      "webhooks/github",
      "v1/review-jobs/retry",
    ])
      expect(allowedPath(value)).toBe(false);
    for (const value of [
      "http://external.test",
      "https://user:secret@api.test",
      "https://api.test/path",
    ])
      expect(() => backendOrigin(value)).toThrow();
    expect(
      forwardedCookies(
        "other=private; shrike_session=opaque; provider_token=secret",
      ),
    ).toBe("shrike_session=opaque");
  });
  it("rejects non-GitHub source links and never echoes raw API errors", async () => {
    const data = detailSchema.parse(
      demoData(
        `v1/dashboard/reviews/${demoReviews[0].id}`,
        new URLSearchParams(),
      ),
    );
    expect(() =>
      detailSchema.parse({
        ...data,
        findings: {
          ...data.findings,
          items: [
            { ...data.findings.items[0], github_url: "javascript:alert(1)" },
          ],
        },
      }),
    ).toThrow();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("SYNTHETIC_PRIVATE_TOKEN", { status: 500 }),
        ),
    );
    await expect(
      request("v1/dashboard/metrics", metricsSchema),
    ).rejects.toBeInstanceOf(ApiError);
    await expect(
      request("v1/dashboard/metrics", metricsSchema),
    ).rejects.not.toThrow("SYNTHETIC_PRIVATE_TOKEN");
    vi.unstubAllGlobals();
  });
});
