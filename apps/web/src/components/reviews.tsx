"use client";

import { useApi } from "@/lib/api";
import { pageSchema, repositorySchema, reviewSchema } from "@/lib/contracts";
import { Icon } from "./icons";
import {
  Empty,
  ErrorState,
  Heading,
  Loading,
  Pagination,
  Panel,
  ReviewsTable,
  Select,
  useFilters,
} from "./ui";

export function Reviews() {
  const filters = useFilters();
  const result = useApi(
    `v1/dashboard/reviews?${filters.apiQuery(["repository_id", "state", "pull_request_number", "cursor"])}`,
    pageSchema(reviewSchema),
  );
  const repos = useApi(
    "v1/dashboard/repositories?limit=100",
    pageSchema(repositorySchema),
  );
  return (
    <>
      <Heading
        eyebrow="REVIEW HISTORY"
        title="Every review. A clear trail."
        description="Follow pull requests from queued analysis to actionable findings."
        action={
          <button
            className="button"
            onClick={() => {
              void result.mutate();
              void repos.mutate();
            }}
          >
            <Icon name="refresh" size={15} />
            Refresh
          </button>
        }
      />
      <div className="filter-bar review-filters">
        <div className="filter-controls">
          <Select
            label="Filter by repository"
            value={filters.search.get("repository_id") || ""}
            onChange={(value) => filters.set({ repository_id: value })}
            options={[
              { value: "", label: "All repositories" },
              ...(repos.data?.items.map((r) => ({
                value: r.id,
                label: r.name,
              })) || []),
            ]}
          />
          <Select
            label="Filter by state"
            value={filters.search.get("state") || ""}
            onChange={(value) => filters.set({ state: value })}
            options={[
              { value: "", label: "All states" },
              ...["completed", "running", "pending", "failed", "canceled"].map(
                (value) => ({
                  value,
                  label: value[0].toUpperCase() + value.slice(1),
                }),
              ),
            ]}
          />
        </div>
        <form
          className="search-form compact-search"
          onSubmit={(event) => {
            event.preventDefault();
            filters.set({
              pull_request_number: String(
                new FormData(event.currentTarget).get("pr") || "",
              ),
            });
          }}
        >
          <Icon name="search" size={16} />
          <input
            type="number"
            min="1"
            max="2147483647"
            name="pr"
            aria-label="Pull request number"
            placeholder="PR number…"
            key={filters.search.get("pull_request_number") || ""}
            defaultValue={filters.search.get("pull_request_number") || ""}
          />
          <button className="button button-small" type="submit">
            Find
          </button>
        </form>
      </div>
      {repos.error && (
        <div className="inline-alert" role="alert">
          Repository filters couldn’t load.
          <button className="text-link" onClick={() => void repos.mutate()}>
            Retry filters
          </button>
        </div>
      )}
      {repos.data?.next_cursor && (
        <p className="muted text-small">
          The selector shows the first 100 accessible repositories. Open a
          repository from the Repositories page to filter any other repository.
        </p>
      )}
      {result.error ? (
        <ErrorState error={result.error} retry={() => void result.mutate()} />
      ) : !result.data ? (
        <Loading label="Loading reviews" />
      ) : (
        <Panel
          title="All reviews"
          description="Analysis and publication are tracked independently"
        >
          {result.data.items.length ? (
            <ReviewsTable reviews={result.data.items} />
          ) : (
            <Empty
              title="No reviews in this view"
              description="Try a different repository, state, or pull request number."
              action={
                <button
                  className="button"
                  onClick={() =>
                    filters.set({
                      repository_id: "",
                      state: "",
                      pull_request_number: "",
                    })
                  }
                >
                  Clear filters
                </button>
              }
            />
          )}
          <Pagination
            next={result.data.next_cursor}
            count={result.data.items.length}
          />
        </Panel>
      )}
    </>
  );
}
