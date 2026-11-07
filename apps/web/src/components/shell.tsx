"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useApi } from "@/lib/api";
import { sessionSchema } from "@/lib/contracts";
import { useDensity } from "@/lib/preferences";
import { Icon, ShrikeMark, type IconName } from "./icons";
import { ErrorState, Loading } from "./ui";

const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/repositories", label: "Repositories", icon: "repository" },
  { href: "/reviews", label: "Reviews", icon: "review" },
  { href: "/settings", label: "Settings", icon: "settings" },
  { href: "/status", label: "System status", icon: "status" },
];
export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open)
      sidebar.current?.querySelector<HTMLAnchorElement>("nav a")?.focus();
    else if (wasOpen.current) menuButton.current?.focus();
    wasOpen.current = open;
  }, [open]);
  const density = useDensity();
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  const session = useApi(
    path === "/login" ? null : "auth/session",
    sessionSchema,
  );
  if (path === "/login") return <>{children}</>;
  const selected = navigation.find((n) =>
    n.href === "/" ? path === "/" : path.startsWith(n.href),
  );
  return (
    <div className="workspace">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside
        ref={sidebar}
        id="workspace-navigation"
        role={open ? "dialog" : undefined}
        aria-modal={open || undefined}
        className={`sidebar ${open ? "sidebar-open" : ""}`}
        aria-label="Workspace navigation"
        onKeyDown={(event) => {
          if (!open) return;
          if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          }
          if (event.key === "Tab") {
            const focusable = sidebar.current?.querySelectorAll<HTMLElement>(
              "a[href],button:not([disabled])",
            );
            const first = focusable?.[0];
            const last = focusable?.[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <button
          className="icon-button mobile-nav-close"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        >
          <Icon name="close" />
        </button>
        <Link href="/" className="brand" onClick={() => setOpen(false)}>
          <ShrikeMark />
          <span>
            shrike<span className="brand-period">.</span>
          </span>
        </Link>
        <div className="workspace-selector">
          <span className="workspace-avatar">S</span>
          <div>
            <strong>Shrike workspace</strong>
            <small>Code review intelligence</small>
          </div>
          <Icon name="down" size={13} />
        </div>
        <div className="nav-section-label">WORKSPACE</div>
        <nav>
          {navigation.map((item) => {
            const active = item === selected;
            return (
              <Link
                href={item.href}
                key={item.href}
                className={`nav-item ${active ? "nav-active" : ""}`}
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
                {active && <span className="nav-active-mark" />}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="advisory-note">
            <Icon name="shield" size={19} />
            <strong>Insight, with you in control.</strong>
            <p>Advisory reviews. Your team makes the final call.</p>
          </div>
          <div className="sidebar-user">
            <span className="user-avatar">
              {session.data?.mode === "demo" ? "DM" : "GH"}
            </span>
            <div>
              <strong>{session.data?.login || "Your account"}</strong>
              <small>
                {session.data?.mode === "demo"
                  ? "Demo workspace"
                  : "GitHub connected"}
              </small>
            </div>
            <span className="small-live-dot" />
          </div>
        </div>
      </aside>
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="workspace-main" inert={open || undefined}>
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              ref={menuButton}
              className="icon-button mobile-menu"
              aria-label={open ? "Close navigation" : "Open navigation"}
              aria-expanded={open}
              aria-controls="workspace-navigation"
              onClick={() => setOpen(!open)}
            >
              <Icon name={open ? "close" : "menu"} />
            </button>
            <span className="workspace-breadcrumb">Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>
              {selected?.label || "Review detail"}
              {path.startsWith("/reviews/") ? " / Detail" : ""}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="mode-pill">
              <span className="status-dot" />
              {session.data?.mode === "demo"
                ? "Read-only demo"
                : "Connected workspace"}
            </span>
            <span className="topbar-version mono">v0.1</span>
          </div>
        </header>
        <main id="main" className="main-content" tabIndex={-1}>
          {session.isLoading ? (
            <Loading />
          ) : session.error ? (
            <ErrorState
              error={session.error}
              retry={() => void session.mutate()}
            />
          ) : (
            children
          )}
        </main>
        <footer className="workspace-footer">
          <span>
            <span className="footer-dot" />
            Shrike · Code review, considered.
          </span>
          <span>
            {session.data?.mode === "demo"
              ? "Synthetic data · No repository changes"
              : "Repository access verified server-side"}
          </span>
        </footer>
      </div>
    </div>
  );
}
