"""Check browser chunks for forbidden backend configuration and synthetic secret canaries."""

import json
from pathlib import Path

MARKERS = (
    "GITHUB_OAUTH_CLIENT_SECRET",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "DASHBOARD_TOKEN_KEY",
    "LLM_API_KEY",
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "DEV_AUTH_TOKEN",
    "SHRIKE_SYNTHETIC_BUILD_SECRET_CANARY",
)


def main() -> int:
    files = list(Path("apps/web/.next/static").rglob("*.js"))
    violations = 0
    for path in files:
        data = path.read_text(encoding="utf-8")
        violations += sum(marker in data for marker in MARKERS)
    print(json.dumps({"browser_chunks": len(files), "forbidden_marker_matches": violations}))
    return 0 if files and not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
