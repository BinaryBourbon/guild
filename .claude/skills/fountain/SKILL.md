---
name: fountain
description: Spawn and stream Fountain conversations from a workstation — use whenever the user asks you to "spin up an agent on Fountain", "delegate to another agent", "fan out", run captain-picard, or any task large enough to parallelise across coding agents. Fountain provisions an isolated Sprite per conversation, runs the configured runtime in it, and streams output back over SSE. Reads `FOUNTAIN_BASE_URL` and `FOUNTAIN_API_KEY` from the environment (typically a `.env` at the repo root).
---

# Fountain — spawning conversations from a workstation

You are on a developer workstation, not inside a Sprite. The Fountain API is
reachable at `$FOUNTAIN_BASE_URL` (under **`/api`**) with bearer
`$FOUNTAIN_API_KEY`. Every conversation you spawn provisions a fresh Sprite
on Fountain's side.

> **Common mistake**: hitting `$FOUNTAIN_BASE_URL/conversations` returns 302
> (the bare path is the LiveView UI). The right URL is
> `$FOUNTAIN_BASE_URL/api/conversations`.

## Loading credentials

Creds live in `.env` at the repo root. Source them at the top of any shell
snippet:

```bash
set -a; . ./.env; set +a
```

This exports `FOUNTAIN_BASE_URL` and `FOUNTAIN_API_KEY` into the current
shell. `.env` must be gitignored — check before staging anything new.

There is **no** `FOUNTAIN_CONVERSATION_ID` on a workstation. That variable
only exists inside a Sprite, where it marks the parent conversation for
provenance. Workstation spawns are root conversations; just omit the parent
header.

## The two patterns you'll use

### A. Fan out N agents and collect their answers

```bash
set -a; . ./.env; set +a

# 1. Pick the agent (by name).
AGENT_ID=$(curl -s "$FOUNTAIN_BASE_URL/api/agents" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  | jq -r '.data[] | select(.name == "echo-bot") | .id')

# 2. Spawn N conversations IN PARALLEL with xargs. Output is conv ids on stdout.
prompts=("First task" "Second task" "Third task")
ids=$(printf '%s\n' "${prompts[@]}" | xargs -n1 -P8 -I{} sh -c '
  curl -s -X POST "$1/api/conversations" \
    -H "Authorization: Bearer $2" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg a "$3" --arg p "$4" "{agent_id:\$a, prompt:\$p}")" \
  | jq -r .data.id
' _ "$FOUNTAIN_BASE_URL" "$FOUNTAIN_API_KEY" "$AGENT_ID" {})

echo "$ids"   # one conv id per line

# 3. Wait for all of them in parallel.
echo "$ids" | xargs -n1 -P10 -I{} sh -c '
  while :; do
    s=$(curl -s "$1/api/conversations/$3" -H "Authorization: Bearer $2" | jq -r .data.status)
    case "$s" in running|pending) sleep 2 ;; *) break ;; esac
  done
' _ "$FOUNTAIN_BASE_URL" "$FOUNTAIN_API_KEY" {}

# 4. Gather the final text from each (claude runtime).
while IFS= read -r conv; do
  echo "=== $conv ==="
  curl -sN --max-time 5 \
    "$FOUNTAIN_BASE_URL/api/conversations/$conv/stream?streams=stdout&wait=false" \
    -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  | awk '/^data: /{sub(/^data: /,""); print}' \
  | jq -r '.data | fromjson? | select(.type=="result") | .result' \
  | tail -n1
done <<<"$ids"

# 5. Terminate all spawned conversations now that you have what you need.
echo "$ids" | xargs -n1 -P10 -I{} \
  curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/{}/terminate" \
    -H "Authorization: Bearer $FOUNTAIN_API_KEY"
```

### B. Spawn one and block until it answers

```bash
set -a; . ./.env; set +a
AGENT_ID=...
PROMPT=...

CONV=$(curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg a "$AGENT_ID" --arg p "$PROMPT" '{agent_id:$a, prompt:$p}')" \
  | jq -r .data.id)

while :; do
  s=$(curl -s "$FOUNTAIN_BASE_URL/api/conversations/$CONV" \
    -H "Authorization: Bearer $FOUNTAIN_API_KEY" | jq -r .data.status)
  case "$s" in running|pending) sleep 2 ;; *) break ;; esac
done

curl -sN --max-time 5 \
  "$FOUNTAIN_BASE_URL/api/conversations/$CONV/stream?streams=stdout&wait=false" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
| awk '/^data: /{sub(/^data: /,""); print}' \
| jq -r '.data | fromjson? | select(.type=="result") | .result' \
| tail -n1

# Terminate once you have the result — don't leave the sprite running.
curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/$CONV/terminate" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY"
```

## Running captain-picard against this bus repo

This repo is a captain-picard bus repo (see [`OPERATING_MODEL.md`](../../../OPERATING_MODEL.md)). Dispatch a cycle with:

```bash
set -a; . ./.env; set +a

AGENT_ID=$(curl -s "$FOUNTAIN_BASE_URL/api/agents" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  | jq -r '.data[] | select(.name=="captain-picard") | .id')

VAULT_ID=$(curl -s "$FOUNTAIN_BASE_URL/api/vaults" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  | jq -r '.data[] | select(.name=="binarybourbon") | .id')

PROMPT='repo_url=https://github.com/BinaryBourbon/guild
vault_name=binarybourbon
operating_doc_path=OPERATING_MODEL.md

begin phase 0 per ROADMAP.md.'

CONV=$(curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg a "$AGENT_ID" --arg v "$VAULT_ID" --arg p "$PROMPT" \
        '{agent_id:$a, vault_id:$v, prompt:$p}')" \
  | jq -r .data.id)

echo "Conversation: $FOUNTAIN_BASE_URL/conversations/$CONV"
```

The `binarybourbon` vault layers a GitHub PAT scoped to push to
`BinaryBourbon/*` on top of the agent's default env, so captain-picard can
write briefs, ROADMAP edits, and ADRs back to this repo. Subsequent cycles
swap the free-text tail (`begin phase 0 ...`) for whatever the next ask is
(`continue conv <id>`, `dispatch <slice> per ROADMAP.md`, `resolve G0 — picked option B`, etc.).

## SSE wire format (so you don't have to discover it)

A `curl -N` against `/api/conversations/:id/stream` produces lines like:

```
id: 2694
event: output
data: {"data":"{\"type\":\"result\",...}","stream":"stdout","stage":"turn",...}

id: 2695
event: output
data: {"data":"{\"type\":\"assistant\",...}","stream":"stdout",...}
```

Two layers of JSON. The `awk` strips the `data: ` prefix; jq's default parses
the **outer** object; **only the inner `.data` field is a JSON-encoded
string** that needs `fromjson` to peel. Do NOT call `fromjson` on the awk
output itself — jq already parsed it.

## The `wait=false` flag matters

The stream endpoint normally holds open for up to 60s waiting for new
events. **When the conversation is already done and you only want the
replay, pass `wait=false`.** Without it, your `curl --max-time 5` will sit
idle for the full 5 seconds. With it, the stream closes the moment the
replay drains — milliseconds.

Drop `wait=false` only when you actually want to live-tail.

## Per-runtime: where the final text lives

The conversation's `runtime` (`claude` / `codex` / `gemini` / `opencode`)
controls the shape of the inner JSON. Pull the runtime once, then pick the
right filter:

```bash
RT=$(curl -s "$FOUNTAIN_BASE_URL/api/conversations/$CONV" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" | jq -r .data.runtime)
```

| runtime  | filter (the part **after** `.data \| fromjson?`)                       | text path        |
| -------- | ---------------------------------------------------------------------- | ---------------- |
| claude   | `select(.type=="result")`                                              | `.result`        |
| codex    | `select(.type=="item.completed" and .item.type=="agent_message")`      | `.item.text`     |
| gemini   | `select(.type=="message" and .role=="assistant")`                      | `.content` *(use the last one)*  |
| opencode | `select(.type=="text")`                                                | `.part.text` *(concatenate all)* |

## Vaults — running as a different identity

A spawned conversation runs with the agent's default environment unless you
pass a `vault_id` — then the vault's secrets layer on top, overriding on key
collision. Almost every workstation spawn against this repo wants a vault,
because the default env's `GITHUB_TOKEN` can't push to `BinaryBourbon/*`.

```bash
curl -s "$FOUNTAIN_BASE_URL/api/vaults" -H "Authorization: Bearer $FOUNTAIN_API_KEY" \
  | jq -r '.data[] | "\(.name)\t\(.id)"'

# Spawn with a specific vault layered on top of the env's secrets:
curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" -H "Content-Type: application/json" \
  -d "$(jq -n --arg a "$AGENT_ID" --arg v "$VAULT_ID" --arg p "$PROMPT" \
        '{agent_id:$a, vault_id:$v, prompt:$p}')"
```

For this repo, `binarybourbon` is the vault to use when running
captain-picard or any specialist that pushes to GitHub.

## Multi-turn

Send a follow-up prompt to an existing conversation:

```bash
curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/$CONV/prompts" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"prompt":"Now compare that to the worker service."}'
```

Then poll status / read the stream the same way. The runtime session
resumes — the agent remembers turn 1.

## Terminate agents when you're done

Every spawned conversation holds a live Sprite (a real compute sandbox) until
explicitly terminated or until Fountain's idle timeout fires. **Terminate as
soon as you have what you need** — don't leave agents idling.

```bash
# Terminate a single conversation:
curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/$CONV/terminate" \
  -H "Authorization: Bearer $FOUNTAIN_API_KEY"

# Terminate a batch (e.g. after a fan-out gather):
echo "$ids" | xargs -n1 -P10 -I{} \
  curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/{}/terminate" \
    -H "Authorization: Bearer $FOUNTAIN_API_KEY"
```

Terminate is idempotent — calling it on an already-terminated conversation is
harmless. It is **not** the same as deleting: the conversation record and its
stream history are preserved so you (or the operator) can audit what happened.
The Sprite is simply stopped and its resources released.

**Captain-picard is an exception.** It's a long-running orchestrator — you
generally want to *let it keep running* across multiple cycles rather than
terminate after each prompt. Use the `/prompts` endpoint (see Multi-turn)
to send the next ask; only terminate when the slice is genuinely done or
you're abandoning the cycle.

For one-shot fan-outs (Pattern A), terminate every conversation after the
gather. For Pattern B blocking spawns, terminate immediately after reading
the result.

If your script may exit early, install a cleanup trap:

```bash
spawned_ids=()
trap 'echo "${spawned_ids[@]}" | tr " " "\n" | xargs -n1 -P10 -I{} \
  curl -s -X POST "$FOUNTAIN_BASE_URL/api/conversations/{}/terminate" \
    -H "Authorization: Bearer $FOUNTAIN_API_KEY"' EXIT
spawned_ids+=("$CONV")
```

## Important

- **Always terminate one-shot conversations when done.** Sprites are real compute. Orphaned conversations run until Fountain's idle timeout — wasteful and expensive. (Captain-picard is the exception — it's long-running.)
- **Always `wait=false` for gather.** Otherwise you'll burn N × `--max-time` seconds for no reason.
- **Parallelize spawn / poll / gather / terminate** with `xargs -P` — one provisioning takes ~5–15s, and there's no reason to do them sequentially.
- **Costs add up.** Every conversation provisions a real sandbox. Terminate promptly.
- **`FOUNTAIN_API_KEY` is a long-lived workstation credential** — different from the per-conversation `FOUNTAIN_TOKEN` a Sprite gets. Treat it like an SSH key: never commit, never paste into chat, rotate via the Fountain dashboard if exposed. If you see 401 with `"reason": "api_key_revoked"`, the key was rotated — pull the new value into `.env` and re-source.
- **`.env` must be gitignored.** The repo's `.gitignore` covers `.env`, `.env.local`, and `.env.*.local`. If you add a new env file with a different name, gitignore it explicitly before populating it.
- **API path is `/api/...`.** The bare `/conversations` redirects (302 → /login) for non-browser requests.
- **No parent conv header from a workstation.** `X-Fountain-Parent-Conversation-Id` is for in-sprite spawns where there's a real parent to attribute to. Workstation spawns are root conversations; omit the header.
