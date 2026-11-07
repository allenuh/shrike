# Instructions for Codex and other contributors

## Read before implementation

Read `README.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` before changing application behavior. Inspect the repository and applicable nested `AGENTS.md` files. The documents describe a proposed system; do not assume planned components already exist.

## Scope and architecture

- The project name is Shrike. The canonical repository is `https://github.com/allenuh/shrike.git`; use Shrike in branding, configuration, service names, and deliverables.
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

## AI spending controls

- The approximate total OpenAI API development budget is **$10 USD**, with initial cumulative warning and hard-stop thresholds of **$7.50** and **$9.00**. Minimize spending; do not interpret available budget as permission to spend. Track known development/evaluation spending outside Shrike before allocating the remaining allowance. Do not claim knowledge of the user's account balance or this coding session's billing.
- Read [AI cost controls](docs/AI_COST_CONTROLS.md) before implementing any AI behavior. Keep the deterministic mock as the default. Ordinary development, CI/CD, unit tests, integration tests, and automated evaluations must exclusively use mock AI responses without API keys or model network access.
- Real OpenAI requests require a separately requested hosted-provider task, explicit live opt-in, an allowlisted model configured through environment variables, and private-code egress consent where relevant. Never make live calls to validate a documentation change. Live evaluation also requires a positive, bounded maximum request count; default allowance is zero.
- Keep provider/tokenizer/pricing/ledger implementations behind ports. Before each paid attempt, enforce input/output/context/diff/concurrency limits and atomically reserve a conservative cost estimate in a cumulative PostgreSQL ledger shared across workers and preserved across restarts. Record reported usage separately from estimates. Missing/stale pricing, unknown token bounds, unavailable ledger, or insufficient budget must fail closed; no unbounded override.
- Verify current official provider pricing/model support when implementing or enabling the integration. Record the pricing source, model, tier, currency, verification/expiry times, and billable token categories. Never hardcode guessed rates, assume cache discounts, or silently switch to a more expensive model.
- Disable SDK, HTTP, and queue retries of paid requests by default (one attempt). Any explicitly configured retry must be bounded and independently budgeted. Timeouts, crashes, and missing usage must retain the full reservation until reconciled; worker recovery must not blindly send another paid request.
- Do not reset the ledger on restart, seed, migration, or review-retention cleanup. Raising thresholds, resetting accounting, or authorizing additional spend requires an explicit user decision. Preserve credentials and private data protections above; never log API keys, private source, prompts, or sensitive payloads.
- These are mandatory implementation gates, not a claim that the future provider or ledger exists. Update architecture, roadmap, migration/test evidence, and limitations as controls are implemented.

## Git commit policy

Conventional Commits is mandatory for all new Shrike commits. Follow the [Conventional Commits 1.0.0 specification](https://www.conventionalcommits.org/en/v1.0.0/) and the project rules below.

Use these subject formats; scopes are optional:

```text
<type>: <imperative description>
<type>(<scope>): <imperative description>
```

The colon immediately follows the type, scope, or breaking-change marker, with exactly one space after it. Do not insert a space before the colon.

Allowed types:

| Type | Purpose |
| --- | --- |
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior changes |
| `perf` | Performance improvement |
| `test` | Test additions or corrections |
| `docs` | Documentation changes |
| `style` | Formatting changes without behavior changes |
| `build` | Build system or dependencies |
| `ci` | CI/CD workflows |
| `chore` | General maintenance |

Preferred scopes: `api`, `web`, `github`, `ai`, `worker`, `db`, `infra`, `auth`, `deps`. Omit the scope for repository-wide changes; use the most relevant scope when one applies.

1. Use lowercase types and scopes.
2. Keep subject lines concise, ideally no more than 72 characters, including the type and optional scope.
3. Use the imperative mood, such as `add`, `fix`, or `update`, rather than `added`, `fixed`, or `updated`.
4. Do not end the subject with a period.
5. Each commit must represent one logically cohesive change.
6. Include a commit body for complex changes explaining why the change was made. Separate the body from the subject with a blank line.
7. Mark breaking changes with `!` immediately before the colon and/or an uppercase `BREAKING CHANGE: <explanation>` footer. For example, `feat(api)!: require versioned review requests`. Separate footers from the preceding body or subject with a blank line.
8. Do not combine unrelated features into one commit; split unrelated work into separate commits.
9. Commit only after relevant tests and checks pass. Apply the documentation-only validation guidance above when appropriate. If a required check fails or cannot run, report the blocker and do not claim the change is ready to commit.
10. Before committing, check `git status`, inspect the staged file list and `git diff --cached`, and run `git diff --cached --check`. Confirm that only authorized changes are staged.
11. Never commit secrets, credentials, real environment files (including `.env` and environment-specific variants), or generated build artifacts. A deliberately tracked example such as `.env.example` may contain placeholders only; review it before staging.
12. Do not amend or rewrite existing commits unless explicitly requested.
13. Push only when explicitly requested or when a phase is verified complete under the standing development authorization below.
14. At the end of every implementation task, propose an appropriate Conventional Commit message. If an authorized commit was created, report its actual message and commit ID.
15. Make commits only when the user has requested a commit or explicitly authorized automatic commits for that task. Proposing a message or completing a milestone does not itself authorize a commit.

### Standing development authorization

The user has explicitly authorized automatic commits after each meaningful development task and automatic pushes after each completed phase. This authorization applies to future development sessions unless the user overrides or revokes it.

- After a meaningful, logically cohesive task is complete and its relevant checks pass, review Git status and staged changes, then create a Conventional Commit without requesting confirmation again. Include related tests and documentation; keep incomplete or unrelated work out of that commit.
- Push the phase's commits to the configured remote only after all acceptance criteria for that phase are verified, required checks pass, and `docs/ROADMAP.md` records the evidence. Do not push incomplete phases automatically. An explicit user request may separately authorize an earlier push.
- Report created commit IDs/messages, push results, and any checks, manual steps, or phase criteria that remain incomplete. If checks, authentication, permissions, or remote divergence block a commit/push, preserve the work and report the blocker honestly.
- This standing authorization does not permit amending or rewriting history, force-pushing, committing secrets or generated artifacts, bypassing failed checks, or implementing unrequested phases.

## Task completion report

After each task, summarize changed files and behavior, checks actually run with their outcomes, remaining issues and risks, and manual steps still required. Do not claim the entire platform or a phase is complete based on scaffolding alone.
