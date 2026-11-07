"use client";

import { useApi } from "@/lib/api";
import { operationsSchema } from "@/lib/contracts";
import { Icon } from "./icons";
import {
  Badge,
  ErrorState,
  Heading,
  Loading,
  Panel,
  shortDate,
  Stat,
} from "./ui";

export function SystemStatus() {
  const result = useApi("v1/dashboard/operations", operationsSchema);
  if (result.error)
    return (
      <ErrorState error={result.error} retry={() => void result.mutate()} />
    );
  if (!result.data) return <Loading label="Loading system status" />;
  const data = result.data;
  return (
    <>
      <Heading
        eyebrow="OPERATIONS"
        title="System status"
        description="A scoped view of review processing. Evidence over assumptions."
        action={
          <button className="button" onClick={() => void result.mutate()}>
            <Icon name="refresh" size={15} />
            Refresh snapshot
          </button>
        }
      />
      <div className="system-banner">
        <span className="system-banner-icon">
          <Icon name="status" size={27} />
        </span>
        <div>
          <h2>
            {data.database === "synthetic"
              ? "Demo operational snapshot"
              : "Database snapshot available"}
          </h2>
          <p>
            As of {shortDate(data.as_of)} UTC · Accessible repositories only
          </p>
        </div>
        <Badge
          value={
            data.expired_leases || data.uncertain_publications
              ? "attention"
              : "snapshot"
          }
        />
      </div>
      <div className="stats-grid">
        <Stat
          label="Pending reviews"
          value={String(data.pending)}
          detail={`${data.undispatched} undispatched messages`}
          icon="review"
        />
        <Stat
          label="Running reviews"
          value={String(data.running)}
          detail={`${data.active_leases} active execution leases`}
          icon="status"
        />
        <Stat
          label="Waiting to retry"
          value={String(data.retry_wait)}
          detail="Database-scheduled retry wait"
          icon="refresh"
        />
        <Stat
          label="Publication uncertainty"
          value={String(data.uncertain_publications)}
          detail="Inflight, uncertain, or partial"
          icon="alert"
        />
      </div>
      <div className="overview-middle">
        <Panel
          title="Processing signals"
          description="Reported from durable PostgreSQL state"
        >
          <div className="signal-row">
            <div>
              <span className="signal-icon">
                <Icon name="repository" />
              </span>
              <div>
                <strong>Database</strong>
                <p>
                  {data.database === "synthetic"
                    ? "Synthetic fixture; no database was contacted"
                    : "Read succeeded for this snapshot"}
                </p>
              </div>
            </div>
            <Badge
              value={data.database === "synthetic" ? "demo" : "reachable"}
            />
          </div>
          <div className="signal-row">
            <div>
              <span className="signal-icon">
                <Icon name="clock" />
              </span>
              <div>
                <strong>Oldest pending review</strong>
                <p>Time since creation; not a broker latency measurement</p>
              </div>
            </div>
            <strong className="mono">
              {data.oldest_pending_seconds === null
                ? "—"
                : `${Math.round(data.oldest_pending_seconds)}s`}
            </strong>
          </div>
          <div className="signal-row">
            <div>
              <span className="signal-icon">
                <Icon name="shield" />
              </span>
              <div>
                <strong>Expired execution leases</strong>
                <p>Running reviews with missing or expired ownership</p>
              </div>
            </div>
            <Badge value={data.expired_leases ? "attention" : "none"} />{" "}
            <span className="mono">{data.expired_leases}</span>
          </div>
        </Panel>
        <Panel
          title="Telemetry availability"
          description="Unavailable is different from healthy"
        >
          <div className="telemetry">
            <div>
              <Icon name="status" />
              <strong>Worker heartbeat</strong>
              <span>Not instrumented</span>
            </div>
            <p>
              An active lease is evidence of ownership, not proof that a worker
              is currently alive.
            </p>
            <div>
              <Icon name="branch" />
              <strong>Redis reachability</strong>
              <span>Not measured</span>
            </div>
            <p>
              This page reads scoped outbox state. It does not probe the broker
              or disclose global queues.
            </p>
          </div>
        </Panel>
      </div>
      <div className="scope-note">
        <Icon name="lock" size={15} />
        <span>
          These metrics cover your accessible repositories. Infrastructure-wide
          health, alerts, and process controls are outside this dashboard.
        </span>
      </div>
    </>
  );
}
