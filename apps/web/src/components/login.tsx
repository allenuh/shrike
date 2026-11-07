"use client";
import { useSearchParams } from "next/navigation";
import { Icon, ShrikeMark } from "./icons";

export function Login() {
  const search = useSearchParams();
  return (
    <main className="login-page">
      <div className="login-art">
        <div className="brand">
          <ShrikeMark />
          <span>shrike.</span>
        </div>
        <div>
          <span className="eyebrow">A SECOND SET OF EYES.</span>
          <h1>
            Thoughtful reviews.
            <br />
            Confident decisions.
          </h1>
          <p>
            Bring your pull requests, findings, and review history into one
            considered workspace.
          </p>
          <div className="login-principles">
            <span>
              <Icon name="shield" />
              Advisory by design
            </span>
            <span>
              <Icon name="lock" />
              Repository-scoped access
            </span>
          </div>
        </div>
        <small>Code review, with your team in control.</small>
      </div>
      <div className="login-form">
        <div>
          <span className="eyebrow">WELCOME TO SHRIKE</span>
          <h2>Your workspace awaits.</h2>
          <p>
            Sign in with your GitHub account. You’ll only see repositories that
            both you and the Shrike App can access.
          </p>
          {search.has("error") && (
            <div role="alert" className="inline-alert">
              Authorization couldn’t be completed. Start a new sign-in attempt.
            </div>
          )}
          {/* OAuth must use a full navigation, without route prefetch or client caching. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a
            className="button button-primary login-button"
            href="/api/backend/auth/github/start"
          >
            <Icon name="github" />
            Continue with GitHub
            <Icon name="arrow" />
          </a>
          <div className="login-security">
            <Icon name="lock" size={15} />
            <p>
              Secure, server-managed sessions.
              <br />
              GitHub credentials never enter your browser.
            </p>
          </div>
          <p className="text-small muted">
            In local demo mode, Continue opens the read-only synthetic workspace
            without contacting GitHub.
          </p>
        </div>
      </div>
    </main>
  );
}
