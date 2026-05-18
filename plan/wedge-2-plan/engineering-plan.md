# Engineering Plan — Wedge 2 (Thread-First)

**Slice:** wedge-2-plan  
**Gate:** G1 — approved by pr-reviewer before implementation begins  
**Stack:** Python 3.12, Postgres 16, Anthropic SDK (`anthropic`), GitHub REST via `httpx`  
**Verification note:** This is a plan PR. No code is produced here. Automated verification is required on every implementation PR beginning at G2, per `docs/05`.

---

## 1. Thread Model Schema

See `decisions/0003-thread-schema.md` for rationale.

```sql
-- threads: one row per unit of work
CREATE TABLE threads (
  id               TEXT PRIMARY KEY,          -- ULID
  anchor_type      TEXT NOT NULL,             -- 'github_issue'
  anchor_id        TEXT NOT NULL,             -- '<owner>/<repo>#<number>'
  anchor_url       TEXT NOT NULL,
  anchor_title     TEXT NOT NULL,
  state            TEXT NOT NULL DEFAULT 'unnoticed'
                   CHECK (state IN (
                     'unnoticed','noticed','claimed','executing',
                     'pr_open','blocked','planned','done','abandoned'
                   )),
  owner_type       TEXT CHECK (owner_type IN ('worker','human')),
  owner_id         TEXT,
  parent_thread_id TEXT REFERENCES threads(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX threads_anchor ON threads(anchor_type, anchor_id);

-- thread_events: normalized event log
CREATE TABLE thread_events (
  id         TEXT PRIMARY KEY,               -- globally unique; source event ID or ULID
  thread_id  TEXT NOT NULL REFERENCES threads(id),
  source     TEXT NOT NULL,                  -- 'github', 'internal'
  type       TEXT NOT NULL,                  -- e.g. 'issue.assigned', 'pr.opened'
  actor_id   TEXT,
  actor_name TEXT,
  timestamp  TIMESTAMPTZ NOT NULL,
  payload    JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX thread_events_by_thread ON thread_events(thread_id, timestamp DESC);
-- dedup: INSERT ... ON CONFLICT (id) DO NOTHING

-- thread_artifacts: things the worker created
CREATE TABLE thread_artifacts (
  id          TEXT PRIMARY KEY,              -- ULID
  thread_id   TEXT NOT NULL REFERENCES threads(id),
  type        TEXT NOT NULL,                -- 'branch', 'pull_request', 'commit', 'comment'
  external_id TEXT NOT NULL,               -- PR number, branch name, commit SHA, etc.
  url         TEXT,
  title       TEXT,
  state       TEXT,                         -- 'open', 'merged', 'closed', 'draft'
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX thread_artifacts_by_thread ON thread_artifacts(thread_id, type);

-- thread_notes: structured worker-authored summaries
CREATE TABLE thread_notes (
  id         TEXT PRIMARY KEY,              -- ULID
  thread_id  TEXT NOT NULL REFERENCES threads(id),
  author_id  TEXT NOT NULL,                -- worker identity string
  note_type  TEXT NOT NULL                 -- 'decision', 'status', 'error'
             CHECK (note_type IN ('decision','status','error')),
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX thread_notes_by_thread ON thread_notes(thread_id, created_at DESC);
```

**Migration strategy:** Alembic manages all schema changes. Every schema change ships as a versioned migration file alongside the code that needs it.

---

## 2. State Machine

### Allowed transitions

| From | To | Trigger |
|---|---|---|
| `unnoticed` | `noticed` | relevant event received |
| `noticed` | `claimed` | worker calls `assign_to_self` |
| `noticed` | `unnoticed` | worker returns `ignore` |
| `claimed` | `executing` | work begins (any code action called) |
| `executing` | `pr_open` | worker calls `open_pull_request` |
| `executing` | `blocked` | worker returns `ask_question` |
| `executing` | `planned` | worker calls `create_sub_issue` |
| `executing` | `abandoned` | worker returns `escalate` or explicit stop |
| `pr_open` | `executing` | `pull_request.review_submitted` (changes requested) |
| `pr_open` | `done` | `pull_request.merged` |
| `pr_open` | `abandoned` | `pull_request.closed` (without merge) |
| `blocked` | `executing` | human posts a response in the thread |
| `planned` | `done` | all child threads reach `done` or `abandoned` |
| any active | `abandoned` | explicit human instruction |

`done` and `abandoned` are terminal — no transitions out. `abandoned` is always reachable from any active state.

### Enforcement

```python
TRANSITIONS: dict[str, set[str]] = {
    "unnoticed": {"noticed"},
    "noticed":   {"claimed", "unnoticed"},
    "claimed":   {"executing"},
    "executing": {"pr_open", "blocked", "planned", "abandoned"},
    "pr_open":   {"executing", "done", "abandoned"},
    "blocked":   {"executing"},
    "planned":   {"done"},
}

def transition(thread_id: str, to_state: str, db: Session) -> Thread:
    thread = db.get(Thread, thread_id, with_for_update=True)  # row-level lock
    if thread.state in ("done", "abandoned"):
        raise IllegalTransition(f"thread {thread_id} is terminal")
    allowed = TRANSITIONS.get(thread.state, set())
    if to_state != "abandoned" and to_state not in allowed:
        raise IllegalTransition(f"{thread.state} -> {to_state} not allowed")
    thread.state = to_state
    thread.updated_at = now()
    return thread  # caller commits; transition event written in same transaction
```

Every transition is wrapped in a database transaction with the thread row locked. Transition events are written to `thread_events` in the same transaction.

---

## 3. Action Primitive Runtime

### Primitive signature

All primitives are synchronous Python functions in `guild/primitives/`. The action runner maps action-type strings to functions.

```python
@dataclass
class ActionResult:
    success: bool
    artifact: dict | None = None   # artifact record to write to thread_artifacts
    error: PrimitiveError | None = None

class PrimitiveError(Exception):
    kind: Literal["transient", "permanent", "unexpected"]
```

### Retry policy

```python
def run_primitive(fn: Callable, params: dict, max_retries: int = 3) -> ActionResult:
    for attempt in range(max_retries):
        try:
            return fn(**params)
        except PrimitiveError as e:
            if e.kind == "transient" and attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
                continue
            if e.kind == "permanent":
                return ActionResult(success=False, error=e)
            raise  # unexpected — escalation handler catches at the top level
    return ActionResult(success=False,
                        error=PrimitiveError("transient", "max retries exceeded"))
```

### Error routing
- **transient** (rate limit, network timeout): retry with backoff, max 3 attempts
- **permanent** (403, 404, validation failure): write failure event to thread, transition to `blocked`
- **unexpected**: write failure event, call `comment_on_issue` to flag the issue, transition to `blocked`

### Phase 0 primitive set (GitHub only)

| Category | Primitives |
|---|---|
| Code | `create_branch`, `commit_and_push`, `open_pull_request`, `push_to_branch` |
| Communication | `comment_on_issue`, `comment_on_pr` |
| Work management | `assign_to_self`, `add_label`, `update_issue_status` |
| Meta | `write_thread_note`, `update_thread_state`, `log_decision` |

Not implemented in phase 0: Linear actions, Slack/Discord, `create_sub_issue`, `add_to_project`.

### Verification gate on `open_pull_request`

`open_pull_request` polls GitHub check runs on the branch until all required checks pass (or any check fails). If checks fail, returns `PrimitiveError("permanent", "CI failed: <details>")` — the worker must address the failure before retrying. PR is never opened on a failing branch.

---

## 4. Worker Decision Contract

See `decisions/0004-decision-layer-contract.md` for rationale on model and output method.

### Invocation

```python
from anthropic import Anthropic

DECIDE_TOOL = {
    "name": "decide",
    "description": "Return the single action this worker will take in response to the current event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["implement", "claim", "comment",
                         "ask_question", "ignore", "escalate"]
            },
            "reasoning": {"type": "string", "minLength": 10},
            "params":    {"type": "object"}
        },
        "required": ["action", "reasoning", "params"]
    }
}

def decide(context_packet: dict, system_prompt: str) -> DecisionOutput:
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        tools=[DECIDE_TOOL],
        tool_choice={"type": "tool", "name": "decide"},
        messages=[{"role": "user", "content": json.dumps(context_packet, indent=2)}]
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return validate_decision(tool_use.input)
```

### System prompt structure

Four fixed sections, always in this order:

1. **Role** — who this worker is, what it owns, what it doesn't touch
2. **Judgment criteria** — bar for action vs. ignore; what counts as "clear enough" requirements; conservatism defaults
3. **Voice** — communication style per `docs/07` conventions
4. **Action vocabulary** — what each action type means and its required `params` shape (generated from `DECIDE_TOOL` schema, never hand-written)

Section 4 is always generated from the `DECIDE_TOOL` schema so prompt and code stay in sync.

### Validation and fallback

```python
PARAMS_SCHEMAS: dict[str, dict] = {
    "implement": {"task": str},
    "claim":     {},
    "comment":   {"body": str},
    "ask_question": {"question": str, "target": str},
    "ignore":    {},
    "escalate":  {"reason": str},
}

def validate_decision(raw: dict) -> DecisionOutput:
    action = raw.get("action")
    if action not in PARAMS_SCHEMAS:
        return DecisionOutput(action="escalate",
                              reasoning=f"invalid action in model output: {action!r}",
                              params={})
    validate_params(raw.get("params", {}), PARAMS_SCHEMAS[action])  # raises on missing keys
    return DecisionOutput(**raw)
```

On any validation failure, the worker returns `escalate` and logs the raw model output. It never crashes on a bad model response.

### Audit log

Every call to `decide()` writes a record before the action executes: `thread_id`, serialized context packet, raw model response, validated decision, timestamp. This is append-only in phase 0. No query interface until G3.

---

## 5. Context Assembly

### Assembly function

```python
def assemble_context(thread_id: str, current_event: dict,
                     worker_id: str, db: Session,
                     github: GithubClient) -> dict:
    thread = db.get(Thread, thread_id)

    events = (
        db.query(ThreadEvent)
        .filter_by(thread_id=thread_id)
        .order_by(ThreadEvent.timestamp.desc())
        .limit(20)
        .all()
    )
    open_artifacts = (
        db.query(ThreadArtifact)
        .filter_by(thread_id=thread_id)
        .filter(ThreadArtifact.state == "open")
        .all()
    )
    worker_notes = (
        db.query(ThreadNote)
        .filter_by(thread_id=thread_id, author_id=worker_id)
        .order_by(ThreadNote.created_at.desc())
        .all()
    )

    # Live GitHub data fetched at assembly time (not cached)
    issue_data  = github.get_issue(thread.anchor_id)
    pr_comments = github.get_pr_comments(open_artifacts) if open_artifacts else []
    check_runs  = github.get_failing_checks(open_artifacts) if open_artifacts else []

    return {
        "work_item": {
            "title":       thread.anchor_title,
            "description": issue_data["body"],
            "labels":      [l["name"] for l in issue_data["labels"]],
            "assignee":    issue_data.get("assignee", {}).get("login"),
        },
        "history":      [serialize_event(e) for e in reversed(events)],
        "artifacts":    {
            "open_prs":       [serialize_artifact(a) for a in open_artifacts
                               if a.type == "pull_request"],
            "failing_checks": check_runs,
        },
        "conversations":  pr_comments,   # unresolved PR review comments
        "worker_notes":   [serialize_note(n) for n in worker_notes],
        "current_event":  current_event,
    }
```

### Phase 0 limits

- History capped at 20 events (no summarization — punted to G2). Long-running threads may lose old context; acceptable for phase 0.
- Worker notes are **always** included regardless of count. This is the mechanism that makes context continuity work across restarts.
- Human instructions in issue comments are always fetched from GitHub API at assembly time, so they are never missed regardless of poll timing.
- No staleness detection in phase 0.

---

## 6. Polling-Based Event Delivery Stub

See `decisions/0005-polling-to-webhook-migration.md` for the migration path design.

### EventSource interface

```python
class EventSource(ABC):
    """Delivery-agnostic interface. Polling and webhooks both implement this."""
    @abstractmethod
    def start(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def on_event(self, handler: Callable[[str, dict], None]) -> None:
        """Register handler called with (thread_id, normalized_event) on each new event."""
        ...
```

The decision cycle registers a handler via `on_event`. It never calls the polling loop directly. Swapping `PollingEventSource` for `WebhookEventSource` is a config change, not a code change.

### PollingEventSource

```
Schedule: every GUILD_POLL_INTERVAL_SECONDS (default: 120)

For each thread WHERE state NOT IN ('done', 'abandoned'):
  1. Fetch current issue + PR state from GitHub REST API
  2. Diff against last-seen state (materialized from thread_events)
  3. For each detected change, normalize to NormalizedEvent
  4. INSERT INTO thread_events ... ON CONFLICT (id) DO NOTHING  (dedup)
  5. If new event warrants action: call registered on_event handler
```

### Deduplication

Event IDs for poll-detected changes are deterministic: `sha256(f"{source}:{type}:{anchor_id}:{timestamp.isoformat()}")[:16]`. The UNIQUE constraint on `thread_events.id` handles duplicates — INSERT ON CONFLICT DO NOTHING. No application-level dedup needed.

### Work claiming loop

Separate from the per-thread polling loop. Runs every `GUILD_CLAIM_INTERVAL_SECONDS` (default: 300). Queries GitHub for open, unassigned issues in the target repo with label `guild-claim`. For each:
1. Upsert a thread record (anchor = the GitHub issue)
2. If thread is `unnoticed`: transition to `noticed`, call `on_event` handler
3. Decision cycle decides `claim` or `ignore`

Conflict avoidance (per `docs/08`): skip any issue already assigned to a human or another worker.

### Migration path summary

To replace polling with webhooks: implement `WebhookEventSource(EventSource)` — a FastAPI endpoint that validates the GitHub webhook secret and calls the `on_event` handler. Normalization reuses `normalize_github_event()`. Disable `PollingEventSource` via config. Thread model and decision cycle unchanged. See `decisions/0005` for details.
