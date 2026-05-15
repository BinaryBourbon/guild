# 5. Action Primitives

## Purpose

Action primitives are the concrete things workers can do in the world. They are typed, tested functions with known inputs, outputs, and failure modes. The [Decision Layer](04-decision-layer.md) calls them; they do not contain any reasoning logic.

Keeping primitives simple and reliable is important. A primitive should do exactly one thing and do it predictably.

## Code Actions

**`create_branch(repo, branch_name, base)`**
Create a new branch from a base ref. Used at the start of implementation work.

**`commit_and_push(repo, branch, files, message)`**
Commit a set of file changes to a branch and push. The primary output of implementation.

**`open_pull_request(repo, branch, base, title, body)`**
Open a PR from a branch. Called when implementation is ready for review.

**`update_pull_request(repo, pr_number, body)`**
Update an existing PR description — typically to add context or respond to review.

**`push_to_branch(repo, branch, files, message)`**
Push additional commits to an existing branch. Used when addressing review feedback.

## Planning Actions

**`create_issue(tracker, project, title, body, labels, assignee)`**
Create a new issue in Linear or GitHub. Used by PM workers to capture work, decompose epics, or surface problems discovered during implementation.

**`create_sub_issue(tracker, parent_id, title, body, labels)`**
Create a child issue linked to a parent. Used when breaking a larger work item into smaller tasks. Each sub-issue becomes its own thread in Guild.

**`update_issue(tracker, issue_id, fields)`**
Edit the title, description, labels, priority, or assignee of an existing issue. Used for triage, re-prioritization, or adding context.

**`close_issue(tracker, issue_id, reason)`**
Close an issue with an explanatory comment. Used when work is complete, a duplicate is found, or the issue is no longer relevant.

**`add_to_project(tracker, issue_id, project_id)`**
Add an issue to a milestone, sprint, or project board. Used by PM workers organizing work into planned cycles.

## Communication Actions

**`comment_on_issue(repo, issue_number, body)`**
Post a comment on a GitHub issue. Used for status updates, questions, and acknowledgments.

**`comment_on_pr(repo, pr_number, body)`**
Post a comment on a GitHub PR. Used for responding to review, explaining changes.

**`reply_in_thread(thread_ts, channel, body)`**
Reply in a Slack thread. Used for real-time communication with humans.

**`post_to_channel(channel, body)`**
Post a new message to a Slack channel. Used sparingly — for announcements or when there's no existing thread.

## Work Management Actions

**`assign_to_self(issue_id, source)`**
Assign a Linear or GitHub issue to the worker's identity. Used when claiming work.

**`update_issue_status(issue_id, source, status)`**
Update the status of an issue (e.g., "In Progress", "In Review").

**`add_label(repo, issue_number, label)`**
Add a label to a GitHub issue or PR.

## Meta Actions

**`write_thread_note(thread_id, note)`**
Write a context note onto the current thread. Not visible externally — internal memory only.

**`update_thread_state(thread_id, state)`**
Advance the thread's position in the [State Machine](06-state-machine.md).

**`log_decision(thread_id, decision, reasoning, context_snapshot)`**
Write a decision record to the audit log.

## Error Handling

Primitives throw typed errors. The action executor catches these and either:
- Retries (transient failures: rate limits, network timeouts)
- Records failure and moves thread to `blocked` state (permanent failures: permission denied, resource not found)
- Escalates to a human (unexpected failures)

Primitives do not silently swallow errors. A failed action that isn't surfaced leads the worker to incorrectly believe it completed work it didn't.
