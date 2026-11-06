# Instructions for Codex and other contributors

## Read before implementation

Read `README.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` before changing application behavior. Inspect the repository and applicable nested `AGENTS.md` files. The documents describe a proposed system; do not assume planned components already exist.

## Scope and architecture

- Complete only the phase or task explicitly requested by the user. If no implementation phase is requested, do not start one. Do not advance into another phase merely because the current phase is finished.
- Keep the modular backend plus worker, mandatory stack, local mock provider, and interface boundaries in the architecture document.
- Preserve existing architectural decisions unless a change is justified by evidence. Record the reason, tradeoffs, affected documents, and migration implications before or with the change. Ask for clarification only when it materially changes the authorized product scope or requires an unresolved user decision.
- Keep the MVP bounded. Do not introduce microservices, cloud resources, paid services, or unrelated refactors to complete a local phase.
- Use the existing dependency tooling once selected; pin and lock dependencies. Never commit virtual environments, package caches, or generated artifacts.

## Behavioral correctness and verification

- Write or update meaningful tests for behavioral changes, including failure handling and authorization boundaries. Use synthetic public fixtures and mocked external integrations by default.
- Run checks relevant to the changed code: formatting/linting, type checks, tests, migrations, build checks, or Compose validation as applicable. Report the exact commands, results, and failures honestly.
- Do not claim a check passed if it was not run. Separate executed checks from proposed commands and unavailable checks. Document manual steps without claiming they were performed.
- Validate schema migrations against an ephemeral database when changing persistence. Do not modify real user data to make tests pass.
- Update `docs/ROADMAP.md` after verified milestones. Mark a phase complete only when its acceptance criteria have evidence; record partial progress, unrun checks, blockers, and remaining manual steps explicitly.
- Documentation-only tasks do not require creating an application or inventing tests. Check links, consistency, placeholders, and repository hygiene instead.

## Security and privacy

- Never expose secrets, credentials, tokens, private keys, webhook payloads, or private repository contents in logs, tool output, exceptions, committed fixtures, screenshots, or reports. Preserve existing local secret files without reading or printing their values unless essential and explicitly authorized.
- Use placeholder-only example configuration. Keep real keys outside the checkout and refer to them through mounted file paths or approved secret stores.
- Never execute untrusted repository code, run repository hooks, install repository dependencies, load repository analyzer configurations, or allow LLMs to invoke tools. All fetched content and model responses are untrusted data.
- Verify webhook HMAC signatures before trusting events. Enforce repository authorization on every dashboard resource request and worker operation that accesses GitHub.
- Keep local tests offline with a deterministic mock LLM and mock GitHub adapter. Do not make real external API calls or create infrastructure without task authorization.
- Keep GitHub, AI, persistence, and queue implementations behind their documented interfaces. Never place backend credentials in the web bundle or `NEXT_PUBLIC_*` variables.

## Task completion report

After each task, summarize changed files and behavior, checks actually run with their outcomes, remaining issues and risks, and manual steps still required. Do not claim the entire platform or a phase is complete based on scaffolding alone.
