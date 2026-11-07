"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { pageSchema, repositorySchema } from "@/lib/contracts";
import { Icon } from "./icons";
import {
  Badge,
  Empty,
  ErrorState,
  GitHubLink,
  Heading,
  Loading,
  Pagination,
  useFilters,
} from "./ui";

export function Repositories() {
  const filters = useFilters();
  const result = useApi(
    `v1/dashboard/repositories?${filters.apiQuery(["search", "cursor"], 6)}`,
    pageSchema(repositorySchema),
  );
  return (
    <>
      <Heading
        eyebrow="CONNECTED CODEBASES"
        title="Repositories"
        description="Your installed repositories. Only the code you’re authorized to access."
        action={
          <Link href="/settings" className="button">
            <Icon name="github" />
            Integration settings
          </Link>
        }
      />
      <div className="filter-bar">
        <form
          className="search-form"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            filters.set({ search: String(form.get("search") || "") });
          }}
        >
          <Icon name="search" size={17} />
          <input
            type="search"
            name="search"
            aria-label="Search repositories"
            placeholder="Search repositories…"
            defaultValue={filters.search.get("search") || ""}
            key={filters.search.get("search") || ""}
          />
          <button className="button button-small" type="submit">
            Search
          </button>
        </form>
        <span className="filter-hint">
          <span className="small-live-dot" />
          Repository access enforced
        </span>
      </div>
      {result.error ? (
        <ErrorState error={result.error} retry={() => void result.mutate()} />
      ) : !result.data ? (
        <Loading label="Loading repositories" />
      ) : (
        <>
          {result.data.items.length ? (
            <div className="repository-grid">
              {result.data.items.map((repo) => (
                <article className="repository-card" key={repo.id}>
                  <div className="repository-card-top">
                    <span className="repo-icon">
                      <Icon name="repository" size={23} />
                    </span>
                    <span className="visibility">
                      <Icon name={repo.private ? "lock" : "github"} size={12} />
                      {repo.private ? "Private" : "Public"}
                    </span>
                  </div>
                  <span className="repo-owner">{repo.owner}</span>
                  <h2>
                    <Link href={`/reviews?repository_id=${repo.id}`}>
                      {repo.name}
                    </Link>
                  </h2>
                  <p>
                    GitHub App installation{" "}
                    <span className="mono">{repo.installation_github_id}</span>
                  </p>
                  <div className="repository-card-status">
                    {repo.latest_state ? (
                      <Badge value={repo.latest_state} />
                    ) : (
                      <span className="muted">No reviews yet</span>
                    )}
                    <span className="muted">{repo.review_count} reviews</span>
                  </div>
                  <div className="repository-card-footer">
                    <Link
                      className="text-link"
                      href={`/reviews?repository_id=${repo.id}`}
                    >
                      Browse reviews
                      <Icon name="arrow" size={14} />
                    </Link>
                    <GitHubLink
                      href={`https://github.com/${encodeURIComponent(repo.owner)}/${encodeURIComponent(repo.name)}`}
                    >
                      GitHub
                    </GitHubLink>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              title={
                filters.search.has("search")
                  ? "No repositories match"
                  : "No accessible repositories"
              }
              description={
                filters.search.has("search")
                  ? "Try another repository name or clear your search."
                  : "Ask an administrator to install the App on a repository you can access, then sign in again."
              }
              action={
                filters.search.has("search") ? (
                  <button
                    className="button"
                    onClick={() => filters.set({ search: "" })}
                  >
                    Clear search
                  </button>
                ) : undefined
              }
            />
          )}
          <Pagination
            next={result.data.next_cursor}
            count={result.data.items.length}
          />
        </>
      )}
      <div className="scope-note">
        <Icon name="lock" size={15} />
        <span>
          GitHub user access and App installation selection must both permit a
          repository. Installation alone never grants access.
        </span>
      </div>
    </>
  );
}
