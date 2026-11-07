"use client";

import { useState } from "react";
import { useApi } from "@/lib/api";
import { policySchema, sessionSchema } from "@/lib/contracts";
import { saveDensity, useDensity } from "@/lib/preferences";
import { Icon } from "./icons";
import { Badge, ErrorState, Heading, Loading, Panel } from "./ui";

export function Settings() {
  const policy = useApi("v1/dashboard/settings", policySchema);
  const session = useApi("auth/session", sessionSchema);
  const [saved, setSaved] = useState(false);
  const storedDensity = useDensity();
  const [densityDraft, setDensity] = useState<string | null>(null);
  const density = densityDraft ?? storedDensity;
  const [logoutError, setLogoutError] = useState(false);
  if (policy.error)
    return (
      <ErrorState error={policy.error} retry={() => void policy.mutate()} />
    );
  if (!policy.data) return <Loading label="Loading settings" />;
  const data = policy.data;
  async function logout() {
    try {
      const response = await fetch("/api/backend/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error();
      window.location.replace(new URL("/login", window.location.origin).href);
    } catch {
      setLogoutError(true);
    }
  }
  return (
    <>
      <Heading
        eyebrow="WORKSPACE CONFIGURATION"
        title="Settings"
        description="Understand how reviews run. Keep your account and workspace in view."
      />
      <div className="settings-layout">
        <div className="settings-section">
          <h2>GitHub integration</h2>
          <p>
            Repository access follows your GitHub identity and the App’s
            installation.
          </p>
        </div>
        <Panel
          title={
            session.data?.mode === "demo"
              ? "Synthetic demo integration"
              : "GitHub App authorization"
          }
        >
          <div className="integration-card">
            <span className="integration-icon">
              <Icon name="github" size={28} />
            </span>
            <div>
              <strong>{session.data?.login || "Your account"}</strong>
              <p>
                {session.data?.mode === "demo"
                  ? "Read-only fixture data. No GitHub connection or credentials."
                  : "Access is revalidated server-side on every request."}
              </p>
            </div>
            <Badge
              value={session.data?.mode === "demo" ? "demo" : "connected"}
            />
          </div>
          <div className="settings-row">
            <div>
              <strong>Session management</strong>
              <p>
                Opaque HttpOnly cookies; provider tokens stay encrypted on the
                server.
              </p>
            </div>
            {session.data?.mode === "live" ? (
              <button className="button" onClick={() => void logout()}>
                Sign out
              </button>
            ) : (
              <span className="muted">No live session</span>
            )}
          </div>
          {logoutError && (
            <p className="inline-alert" role="alert">
              Sign out couldn’t complete. Try again.
            </p>
          )}
        </Panel>
        <div className="settings-section">
          <h2>Review preferences</h2>
          <p>
            The workspace uses one reviewed analysis policy. Operational changes
            happen outside the dashboard.
          </p>
        </div>
        <Panel
          title="Current review policy"
          action={
            <span className="read-only-label">
              <Icon name="lock" size={12} />
              Read only
            </span>
          }
        >
          <div className="settings-row">
            <div>
              <strong>Language</strong>
              <p>Analysis is limited to eligible changed files.</p>
            </div>
            <span className="value-label">{data.supported_language}</span>
          </div>
          <div className="settings-row">
            <div>
              <strong>AI provider</strong>
              <p>Deterministic mock for automatic review processing.</p>
            </div>
            <Badge value={data.ai_provider} />
          </div>
          <div className="settings-row">
            <div>
              <strong>Publication threshold</strong>
              <p>
                Medium or higher correctness, security, and reliability issues.
              </p>
            </div>
            <span className="value-label">
              ≥ {Math.round(data.minimum_confidence * 100)}% confidence
            </span>
          </div>
          <div className="settings-row">
            <div>
              <strong>Comment limit</strong>
              <p>Invalid inline locations fall back to the review summary.</p>
            </div>
            <span className="value-label">
              {data.maximum_published_findings} findings / review
            </span>
          </div>
          <div className="settings-row">
            <div>
              <strong>GitHub publishing</strong>
              <p>
                No automatic approval, rejection, merge, or code modification.
              </p>
            </div>
            <Badge value={data.publishing} />
          </div>
        </Panel>
        <div className="settings-section">
          <h2>Display preferences</h2>
          <p>
            Personal to this browser. These controls don’t change review
            behavior.
          </p>
        </div>
        <Panel title="Table density">
          <form
            className="preference-form"
            onSubmit={(event) => {
              event.preventDefault();
              try {
                saveDensity(density);
                document.documentElement.dataset.density = density;
                setSaved(true);
              } catch {
                setSaved(false);
              }
            }}
          >
            <fieldset>
              <legend className="sr-only">Choose table density</legend>
              {[
                {
                  value: "comfortable",
                  label: "Comfortable",
                  detail: "A little more room to scan.",
                },
                {
                  value: "compact",
                  label: "Compact",
                  detail: "More reviews in the same space.",
                },
              ].map((option) => (
                <label
                  className={`density-option ${density === option.value ? "density-selected" : ""}`}
                  key={option.value}
                >
                  <input
                    type="radio"
                    name="density"
                    value={option.value}
                    checked={density === option.value}
                    onChange={() => {
                      setDensity(option.value);
                      setSaved(false);
                    }}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.detail}</small>
                  </span>
                </label>
              ))}
            </fieldset>
            <div className="preference-footer">
              <span role="status">
                {saved
                  ? "Saved to this browser."
                  : "Only table spacing is affected."}
              </span>
              <button className="button button-primary" type="submit">
                Save preference
              </button>
            </div>
          </form>
        </Panel>
      </div>
    </>
  );
}
