# Status

Snapshot of where Guild is as of 2026-05-18. For the gate ladder see [`ROADMAP.md`](ROADMAP.md); for protocol see [`OPERATING_MODEL.md`](OPERATING_MODEL.md).

## Where we are

- **G0** ✓ — Wedge 2 (Thread-First) selected. [`decisions/0002-wedge-2-thread-first.md`](decisions/0002-wedge-2-thread-first.md).
- **G1** ✓ — Engineering plan + ADRs approved. [`plan/wedge-2-plan/engineering-plan.md`](plan/wedge-2-plan/engineering-plan.md), [`decisions/0003-thread-schema.md`](decisions/0003-thread-schema.md), [`decisions/0004-decision-layer-contract.md`](decisions/0004-decision-layer-contract.md), [`decisions/0005-polling-to-webhook-migration.md`](decisions/0005-polling-to-webhook-migration.md).
- **G2** — **In flight.** All five implementation slices merged green; six follow-up fix PRs (A–F) addressed pr-reviewer contract violations and a production deploy blocker. Worker is deployed to Render, migrations ran, first test issue is seeded. Awaiting first end-to-end PR from the worker.
- **G3** — Pending. Self-hosting cutover happens after G2 closes honestly.

## Deployment

- **Hosting:** Render, workspace **Jake Personal** (`tea-d6h5vsc50q8c73adag70`), region `oregon`.
- **Worker service:** `guild-worker` (`srv-d85bau3tqb8s73fso6cg`), background worker, starter plan. [Dashboard](https://dashboard.render.com/worker/srv-d85bau3tqb8s73fso6cg).
- **Database:** `guild-db`, managed Postgres, free plan (90-day expiry — upgrade before then).
- **Auto-deploy:** **does not fire on Git push** because the repo is in the `BinaryBourbon` GitHub namespace, not `jhgaylor`'s. Every code-bearing merge to `main` requires a manual deploy trigger (operator or Render dashboard "Manual Deploy → Deploy latest commit"). Operator can trigger via Render API using `RENDER_API_KEY` in local `.env`.
- **Identity (PAT, not GitHub App yet):** `GUILD_WORKER_GITHUB_TOKEN` is a personal access token. PRs the worker opens are authored under the token's owner. Replace with a GitHub App before G3.
- **Domain:** `guild.inevitable.fyi` not yet pointed at the Render hostname. Background worker has no public URL anyway — DNS is only needed once webhooks land (post-G2, see [`decisions/0005`](decisions/0005-polling-to-webhook-migration.md)).

## Test in flight

[Issue #16](https://github.com/BinaryBourbon/guild/issues/16): "Add CONTRIBUTING.md describing the merge protocol." Labeled `guild-claim`, seeded 2026-05-18 07:36:20 UTC. The worker's claiming loop runs every 300s. Expected sequence:

1. Claiming loop sees the label, upserts a Thread, transitions `unnoticed → noticed`
2. Decision layer returns `claim` → `assign_to_self`, `noticed → claimed → executing`
3. Worker implements with Claude SDK, runs CI gate, calls `open_pull_request` only if green
4. Operator dispatches `pr-reviewer` on the new PR, then approves + merges after both gates land
5. **G2 honestly closes**

## Outstanding known issues (non-blocking)

From pr-reviewer comments on fix PRs that landed but flagged minor issues for future cleanup:

- **`decide()` dead-code branch** (PR #10): the `current_event` merge guard is unreachable when worker calls `assemble_context` first. Vestigial; remove for clarity.
- **Prompt section 5 placement** (PR #10): injection-guard instruction is appended at the end of `_SYSTEM_PROMPT`. Move earlier to strengthen model attention.
- **Test specificity** (PR #10): `test_system_prompt_contains_injection_guard` checks substring `"untrusted"`; assert the specific sentinel phrase instead.
- **Render `PORT: "8000"` env var** (PR #14): removed during Blueprint cleanup, but if any future caller assumes a port exists, the lookup will fail.
- **Asyncio race** (PR #13's ADR): `PollingEventSource` and `ClaimingLoop` can both fire `on_event` for the same thread; second `SELECT FOR UPDATE` raises `IllegalTransition` (caught, rolled back). Wasted Anthropic call but not incorrect. Documented as a known limitation. G3+ fix: per-thread dispatch queue.
- **Free Postgres plan expiry**: 90 days from creation. Upgrade before expiry or migrate data.

None of these block G2 close. Track as G3-cleanup work.

## Next steps — G2 close

1. ⏳ Wait for worker to claim issue #16 (≤5 min from seed) and open its first PR.
2. Operator dispatches `pr-reviewer` on the PR.
3. Operator approves + merges after CI + pr-reviewer APPROVE both land.
4. If the loop completes cleanly → G2 honest close; update ROADMAP.
5. If the worker stalls / errors / opens a broken PR → triage from Render logs, fix forward via the same captain-picard v3 + fix-PR pattern.

## Next steps — G3 cutover

Required before declaring the MVP shipped (success metric: a Guild worker on the Guild platform claims an issue in this repo, opens a verified PR, gets merged — with thread continuity preserved across the cycle):

1. **GitHub App in place of PAT** — create `guild-worker` GitHub App, install on `BinaryBourbon/guild`, drop App ID + private key + webhook secret into Render env vars (operator), update `GitHubClient` to mint installation tokens (engineer slice). The auth seam from operator item #7 was designed for this swap.
2. **Webhook delivery (optional but desirable)** — implement `WebhookEventSource` per [`decisions/0005`](decisions/0005-polling-to-webhook-migration.md). Requires a public endpoint, so this is also when DNS for `guild.inevitable.fyi` becomes load-bearing. Render starter background workers don't expose ports — would need to add a small web service (FastAPI endpoint) alongside, or migrate the worker to a Render web service type.
3. **Real issues** — once #1 lands, label live issues `guild-claim` and let the worker pick them up. Watch for the kinds of bugs that don't show up in a single happy-path test.

## Beyond G3

- **Slack identity** for the worker (out of phase-0 scope by design).
- **Per-worker dispatch queue** to eliminate the asyncio race.
- **Linear integration** if/when the team uses Linear for issue tracking.
- **Multi-worker support** — the platform supports multiple workers with distinct identities ([`docs/07-social-presence.md`](docs/07-social-presence.md)); MVP runs one.
- **Webhook security hardening** — once `WebhookEventSource` lands, verify GitHub signatures, rate-limit, dead-letter unknown event types.
- **Observability** — currently the worker only emits WARN+ logs. Add structured logging + metrics before this is asked to do anything stressful.

## Open questions

- **Free Postgres limit:** when do we upgrade? Once worker is doing real work (post-G3), data volume grows. Set a reminder.
- **PR author identity during PAT phase:** PRs opened during G2 sandbox are authored under `jhgaylor`. Cosmetic, but worth noting before merging worker-authored PRs at scale.
- **Operator merge bottleneck:** every code PR currently waits for human (`jhgaylor`) to approve on GitHub. Acceptable for MVP but becomes a throughput limit as the worker becomes more active. G3+ consideration: allow specific labels or paths to auto-merge after CI + pr-reviewer.
