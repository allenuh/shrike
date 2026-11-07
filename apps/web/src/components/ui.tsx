"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import type { Review } from "@/lib/contracts";
import { Icon, type IconName } from "./icons";

export function Heading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}
export function Badge({
  value,
  small = false,
}: {
  value: string;
  small?: boolean;
}) {
  return (
    <span className={`badge badge-${value} ${small ? "badge-small" : ""}`}>
      <span className="status-dot" />
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Stat({
  label,
  value,
  detail,
  icon,
  tone = "",
}: {
  label: string;
  value: string;
  detail: string;
  icon: IconName;
  tone?: string;
}) {
  return (
    <article className="stat">
      <div className="stat-label">
        {label}
        <Icon name={icon} size={17} />
      </div>
      <div className={`stat-value ${tone}`}>{value}</div>
      <div className="stat-detail">{detail}</div>
    </article>
  );
}
export function Loading({ label = "Loading workspace" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="loading-block">
      <span className="loading-label">{label}…</span>
      <div className="skeleton-grid">
        {[0, 1, 2, 3].map((i) => (
          <span className="skeleton" key={i} />
        ))}
      </div>
      <div className="skeleton skeleton-wide" />
      <div className="skeleton skeleton-wide" />
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: ApiError | Error;
  retry: () => void;
}) {
  return (
    <div className="state-card" role="alert">
      <span className="state-icon">
        <Icon name="alert" size={26} />
      </span>
      <h2>
        {error instanceof ApiError && error.status === 401
          ? "Your session has ended"
          : "Something interrupted the request"}
      </h2>
      <p>
        {error instanceof ApiError
          ? error.message
          : "The service is unavailable. Your data has not been changed."}
      </p>
      {error instanceof ApiError && error.status === 401 ? (
        <Link href="/login" className="button button-primary">
          Sign in again
          <Icon name="arrow" />
        </Link>
      ) : (
        <button className="button" onClick={retry}>
          <Icon name="refresh" />
          Try again
        </button>
      )}
    </div>
  );
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="state-icon">
        <Icon name="review" size={25} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function useFilters() {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  function set(values: Record<string, string>, resetCursor = true) {
    const params = new URLSearchParams(search.toString());
    if (resetCursor) params.delete("cursor");
    for (const [key, value] of Object.entries(values)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    router.replace(`${pathname}${params.size ? `?${params}` : ""}`, {
      scroll: false,
    });
  }
  function apiQuery(keys: string[], limit = 8) {
    const params = new URLSearchParams({ limit: String(limit) });
    keys.forEach((key) => {
      const value = search.get(key);
      if (value) params.set(key, value);
    });
    return params.toString();
  }
  return { search, set, apiQuery };
}
export function Pagination({
  next,
  count,
}: {
  next: string | null;
  count: number;
}) {
  const filters = useFilters();
  const hasPrevious = filters.search.has("cursor");
  return (
    <div className="pagination">
      <span>
        {count} {count === 1 ? "result" : "results"} on this page
      </span>
      <div>
        <button
          className="button button-small"
          disabled={!hasPrevious}
          onClick={() => filters.set({ cursor: "" }, false)}
        >
          First page
        </button>
        <button
          className="button button-small"
          disabled={!next}
          onClick={() => filters.set({ cursor: next || "" }, false)}
        >
          Next page
          <Icon name="chevron" size={14} />
        </button>
      </div>
    </div>
  );
}
export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="select-label">
      <span className="sr-only">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((option) => (
          <option value={option.value} key={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <Icon name="down" size={13} />
    </label>
  );
}
export function shortDate(value: string) {
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  });
}
export function duration(review: Review): string {
  if (!review.started_at || !review.finished_at) return "—";
  const seconds = Math.max(
    0,
    (Date.parse(review.finished_at) - Date.parse(review.started_at)) / 1000,
  );
  return `${seconds.toFixed(1)}s`;
}
export function ReviewsTable({ reviews }: { reviews: Review[] }) {
  return (
    <div className="table-scroll">
      <table className="reviews-table">
        <thead>
          <tr>
            <th>Pull request</th>
            <th>Repository</th>
            <th>Status</th>
            <th>Findings</th>
            <th>Duration</th>
            <th>Created · UTC</th>
            <th>
              <span className="sr-only">Open review</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((review) => (
            <tr key={review.id}>
              <td>
                <Link href={`/reviews/${review.id}`} className="primary-link">
                  Pull request #{review.pr_number}
                </Link>
                <span className="table-secondary mono">
                  <Icon name="branch" size={12} />
                  {review.head_sha.slice(0, 7)}
                </span>
              </td>
              <td>
                <span className="repository-cell">
                  <Icon name="repository" size={15} />
                  {review.repository_name}
                </span>
                <span className="table-secondary">
                  {review.repository_owner}
                </span>
              </td>
              <td>
                <Badge value={review.state} />
              </td>
              <td>
                <span
                  className={`finding-count ${review.finding_count ? "has-findings" : ""}`}
                >
                  {review.finding_count ? (
                    <>
                      <span className="tiny-diamond" />
                      {review.finding_count}
                    </>
                  ) : (
                    "—"
                  )}
                </span>
              </td>
              <td className="mono muted">{duration(review)}</td>
              <td className="muted text-nowrap">
                {shortDate(review.created_at)}
              </td>
              <td>
                <Link
                  href={`/reviews/${review.id}`}
                  className="icon-button"
                  aria-label={`Open review for pull request ${review.pr_number}`}
                >
                  <Icon name="chevron" size={16} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function GitHubLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      className="button button-small"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <Icon name="external" size={13} />
    </a>
  );
}
