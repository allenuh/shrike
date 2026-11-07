"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import {
  metricsSchema,
  pageSchema,
  reviewSchema,
  type Metrics,
} from "@/lib/contracts";
import { Icon } from "./icons";
import {
  Empty,
  ErrorState,
  Heading,
  Loading,
  Panel,
  ReviewsTable,
  Select,
  Stat,
  useFilters,
} from "./ui";

export function ActivityChart({ metrics }: { metrics: Metrics }) {
  const count = new Map(
    metrics.daily_reviews.map((day) => [day.date, day.reviews]),
  );
  const end = new Date(metrics.as_of.slice(0, 10));
  const length = Math.min(14, metrics.window_days);
  const days = Array.from({ length }, (_, i) => {
    const date = new Date(end);
    date.setUTCDate(end.getUTCDate() - length + i + 1);
    const key = date.toISOString().slice(0, 10);
    return { date: key, reviews: count.get(key) || 0 };
  });
  const max = Math.max(1, ...days.map((d) => d.reviews));
  return (
    <div
      className="activity-chart"
      role="img"
      aria-label={`Daily review activity for the last ${days.length} days ending ${metrics.as_of.slice(0, 10)}`}
    >
      <div className="chart-y">
        <span>{max}</span>
        <span>{Math.round(max / 2)}</span>
        <span>0</span>
      </div>
      <div className="chart-area">
        <div className="chart-grid">
          <span />
          <span />
          <span />
        </div>
        <div className="chart-bars">
          {days.map((day) => (
            <div
              className="bar-track"
              key={day.date}
              title={`${day.date}: ${day.reviews} reviews`}
            >
              <div
                className="chart-bar"
                style={{ height: `${(day.reviews / max) * 100}%` }}
              />
            </div>
          ))}
        </div>
        <div className="chart-labels">
          <span>{days[0]?.date.slice(5)}</span>
          <span>{days[Math.floor(days.length / 2)]?.date.slice(5)}</span>
          <span>{days.at(-1)?.date.slice(5)}</span>
        </div>
      </div>
      <table className="sr-only">
        <caption>Daily review activity</caption>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th>{day.date}</th>
              <td>{day.reviews}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Overview() {
  const filters = useFilters();
  const window = filters.search.get("window_days") || "30";
  const metrics = useApi(
    `v1/dashboard/metrics?window_days=${encodeURIComponent(window)}`,
    metricsSchema,
  );
  const recent = useApi(
    "v1/dashboard/reviews?limit=5",
    pageSchema(reviewSchema),
  );
  const retry = () => {
    void metrics.mutate();
    void recent.mutate();
  };
  if (metrics.error || recent.error)
    return <ErrorState error={metrics.error || recent.error!} retry={retry} />;
  if (!metrics.data || !recent.data)
    return <Loading label="Loading overview" />;
  const data = metrics.data;
  const severities = ["critical", "high", "medium", "low", "info"] as const;
  return (
    <>
      <Heading
        eyebrow="YOUR REVIEW WORKSPACE"
        title="A clearer view of your code."
        description="Track review activity, surface meaningful issues, and keep your team moving."
        action={
          <Select
            label="Metrics time window"
            value={window}
            onChange={(value) => filters.set({ window_days: value })}
            options={[
              { value: "7", label: "Last 7 days" },
              { value: "30", label: "Last 30 days" },
              { value: "90", label: "Last 90 days" },
            ]}
          />
        }
      />
      <div className="stats-grid">
        <Stat
          label="Review runs"
          value={String(data.reviews)}
          detail={`${data.repositories} accessible repositories`}
          icon="review"
        />
        <Stat
          label="Total findings"
          value={String(data.findings)}
          detail="Across reviews in this window"
          icon="shield"
        />
        <Stat
          label="Success rate"
          value={
            data.success_rate === null
              ? "—"
              : `${data.success_rate.toFixed(1)}%`
          }
          detail={
            data.failure_rate === null
              ? "No completed or failed reviews"
              : `${data.failure_rate.toFixed(1)}% failure rate`
          }
          icon="check"
          tone="text-green"
        />
        <Stat
          label="Avg. processing time"
          value={
            data.average_processing_seconds === null
              ? "—"
              : `${data.average_processing_seconds.toFixed(1)}s`
          }
          detail="Completed reviews only"
          icon="clock"
        />
      </div>
      <div className="overview-middle">
        <Panel
          title="Review activity"
          description="Reviews created per day, in UTC"
          action={
            <span className="chart-legend">
              <span />
              Reviews
            </span>
          }
        >
          <ActivityChart metrics={data} />
        </Panel>
        <Panel
          title="Finding breakdown"
          description="A little context for the bigger picture"
        >
          <div className="severity-total">
            <strong>{data.findings}</strong>
            <span>total findings</span>
          </div>
          <div className="severity-meter" aria-hidden="true">
            {severities.map((severity) => (
              <span
                key={severity}
                className={`severity-${severity}`}
                style={{ flex: data.severity_counts[severity] || 0 }}
              />
            ))}
          </div>
          <div className="severity-list">
            {severities.map((severity) => (
              <div key={severity}>
                <span>
                  <span className={`severity-dot severity-${severity}`} />
                  {severity}
                </span>
                <strong className="mono">
                  {data.severity_counts[severity]}
                </strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Panel
        title="Recent reviews"
        description="The latest activity across your accessible repositories"
        action={
          <Link href="/reviews" className="text-link">
            View all reviews
            <Icon name="arrow" size={15} />
          </Link>
        }
      >
        {recent.data.items.length ? (
          <ReviewsTable reviews={recent.data.items} />
        ) : (
          <Empty
            title="Your first review starts here"
            description="Install the GitHub App on a selected repository and open a pull request to begin."
          />
        )}
      </Panel>
      <div className="scope-note">
        <Icon name="shield" size={15} />
        <span>
          Metrics respect your repository access. Rates include completed and
          failed reviews; pending, running, and canceled reviews are excluded.
        </span>
      </div>
    </>
  );
}
