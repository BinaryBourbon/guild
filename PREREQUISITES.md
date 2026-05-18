# Prerequisites

This template is the *bus repo*. To run the [`captain-picard`](https://github.com/jhgaylor/agent-specs/blob/main/agents/teams/captain-picard/captain-picard.yml) agent against it, you also need the agent itself provisioned in your Fountain workspace, plus the CLIs that talk to Fountain and to your secret store.

You only do this once per machine (or once per Fountain workspace). After that, every new product just clicks "Use this template" and runs `/bootstrap`.

## What you need

- A **Fountain** workspace at [fountain.inevitable.fyi](https://fountain.inevitable.fyi). Sign up at [`/auth/register`](https://fountain.inevitable.fyi/auth/register) — free 14-day trial, no credit card. Grab your API token from the Fountain dashboard.
- An **Infisical** project for resolving the secrets `agent-specs` references. The `agent-specs/.infisical.json` binds the repo to the right project; you just need to be logged in.

## One-time setup

### 1. Install the CLIs

```bash
# GitHub CLI — used to fetch the fountain binary release.
brew install gh && gh auth login

# Infisical CLI — used to resolve secrets at apply-time.
brew install infisical/get-cli/infisical && infisical login
```

### 2. Clone agent-specs and install the fountain CLI

```bash
git clone https://github.com/jhgaylor/agent-specs.git
cd agent-specs
make install        # downloads the fountain binary to ~/.local/bin/fountain
```

Make sure `~/.local/bin` is on your `$PATH`. Verify with `fountain --help`.

### 3. Apply the manifest

`make apply` reconciles every Agent / Environment / Vault in `agent-specs/` against your Fountain workspace. `captain-picard`, the specialist fleet, and the `product-team` env all get provisioned in this step.

```bash
# Set these for your Fountain workspace — make apply uses them.
export FOUNTAIN_BASE_URL=https://fountain.inevitable.fyi
export FOUNTAIN_TOKEN=...                        # from your Fountain dashboard

make apply
```

Verify the agent registered:

```bash
fountain agent list | grep captain-picard
```

If that's empty, re-read the `make apply` output — most likely an Infisical secret didn't resolve (re-`infisical login`) or your `FOUNTAIN_TOKEN` is wrong.

### 4. Seed a project vault (per product owner, not per project)

The `product-team` env's baseline `GITHUB_TOKEN` is from `infisical:///dev/GITHUB_TOKEN` — typically a personal-scope token that can clone public repos but can't push to the org that owns this bus repo. So before `captain-picard` can push to your bus repo, you need a Fountain vault that overrides `GITHUB_TOKEN` with one scoped to the bus-repo's owner.

If a vault already exists for that owner (e.g. you're spinning up your second product under the same GitHub org), skip this step.

Otherwise, in `agent-specs/vaults/` drop a file mirroring [`vaults/binarybourbon.yml`](https://github.com/jhgaylor/agent-specs/blob/main/vaults/binarybourbon.yml):

```yaml
---
apiVersion: fountain/v1
kind: Vault
metadata:
  name: <project-vault>
spec:
  description: <Owner>'s GitHub credentials and git identity
  secrets:
    GITHUB_TOKEN: infisical:///dev/<OWNER>_GITHUB_TOKEN
    GIT_AUTHOR_NAME: <Owner>
    GIT_AUTHOR_EMAIL: <id+owner>@users.noreply.github.com
    GIT_COMMITTER_NAME: <Owner>
    GIT_COMMITTER_EMAIL: <id+owner>@users.noreply.github.com
```

Add the matching `<OWNER>_GITHUB_TOKEN` secret in Infisical (a write-scoped PAT for that owner), then re-run `make apply`. Confirm with `fountain vault list | grep <project-vault>`.

You'll pass `<project-vault>` to both the `--vault` flag and the `vault_name=` line when invoking captain-picard. See [`agent-specs/OPERATIONS.md`](https://github.com/jhgaylor/agent-specs/blob/main/OPERATIONS.md#running-the-project-agnostic-team) for the full operator runbook.

## When something doesn't work

- **`fountain agent list` is empty after `make apply`.** Either Infisical isn't logged in, `FOUNTAIN_TOKEN` is wrong, or `FOUNTAIN_BASE_URL` isn't reachable. Run `fountain agent list` directly (without `make`) to see the raw error.
- **`captain-picard` fails on its first push with `Permission denied`.** The vault wasn't passed (`--vault <project-vault>`), or the vault's `GITHUB_TOKEN` doesn't have write access to the bus repo. Re-check both.
- **Infisical secret resolution errors during `make apply`.** Your `infisical login` session has expired — log in again.

After all of this works once, you don't think about prerequisites again. Bootstrapping each new product is just: click "Use this template" → clone → `claude` → `/bootstrap`.
