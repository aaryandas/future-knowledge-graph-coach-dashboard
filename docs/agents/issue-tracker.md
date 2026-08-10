# Issue tracker: Linear

Issues and specs (you may know a spec as a PRD) for this repo live in Linear, team
**Gauntlet** (key `GNT`). All operations go through the Linear MCP tools (`mcp__linear__*`);
load their schemas with `ToolSearch` before calling them.

If the Linear MCP server isn't connected in the current session, say so rather than falling
back to markdown — a second copy of the tracker is how the two drift apart.

The Gauntlet team spans several repos, so every issue for this repo also sets project
**future-knowledge-graph-coach-dashboard**
(https://linear.app/aaryan-das/project/future-knowledge-graph-coach-dashboard-52c67a52cc8a) —
set `project` on every `save_issue` alongside `team`.

## Conventions

- **Create an issue**: `save_issue` with `team`, `project`, `title`, and `description`
  (Markdown, literal newlines — do not escape them).
- **Read an issue**: `get_issue` with the identifier (e.g. `GNT-12`); pass
  `includeRelations: true` when blocking/related edges matter. Comments come from
  `list_comments`.
- **List issues**: `list_issues` — filter by `team`, `project`, `state`, `label`, `assignee`,
  `parentId`, or `query`. Use `fields` to keep responses small.
- **Comment**: `save_comment` with `issueId` and `body`.
- **Labels**: `labels` on `save_issue` replaces the whole label set — read the current set first
  if you mean to add rather than replace. `list_issue_labels` shows what exists.
- **Close**: `save_issue` with `state: "Done"` (or `"Canceled"` for work ruled out).

Statuses on this team: Backlog, Todo, In Progress, In Review, Done, Canceled, Duplicate.

## When a skill says "publish to the issue tracker"

Create a Linear issue on team **Gauntlet**, project **future-knowledge-graph-coach-dashboard**.

## When a skill says "fetch the relevant ticket"

`get_issue` on the identifier, plus `list_comments` for the conversation.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: an issue labelled `wayfinder:map`, holding the Destination / Notes /
  Decisions-so-far / Fog body. Keep it `In Progress` while the effort is live.
- **Child ticket**: an issue with `parentId` set to the map's identifier — Linear renders these
  as sub-issues on the map, which is the map's live ticket list. Each carries exactly one
  `wayfinder:<type>` label: `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`,
  or `wayfinder:task`. The question goes in the description under `## Question`.
- **Blocking**: Linear's native issue relations — `blockedBy` on `save_issue`, taking a list of
  identifiers. It is append-only; `removeBlockedBy` drops an edge. This renders the frontier
  visually in Linear, so the human sees what's takeable without opening the map. Wire edges in a
  **second pass**, after the issues exist and have identifiers.
- **Frontier query**: `list_issues` with `parentId: "<map>"` and an unstarted state, then drop
  anything with an assignee (claimed) or with an open blocker. Linear flags blocked issues in
  the UI; confirm with `get_issue` `includeRelations: true`. First in map order wins.
- **Claim**: `save_issue` with `assignee: "me"` — the session's first write, before any work.
- **Resolve**: `save_comment` with the answer under a `## Resolution (<date>)` heading, then
  `save_issue` with `state: "Done"`, then append a context pointer (gist + link) to the map's
  Decisions-so-far with a `patch` op.
- **Out of scope**: `state: "Canceled"` plus a line in the map's Out-of-scope section — a
  canceled issue is unambiguously off the frontier and stays out of Decisions-so-far.

**Editing the map body**: use `save_issue`'s `patch` array rather than resending the whole
description. Anchors must match exactly once, and the whole patch is atomic.

**Markdown caveat**: Linear reformats descriptions on save (`-` bullets become `*`) and will
mangle bold that spans a line break. Keep `**…**` inside a single line.

## Assets

Long documents produced while resolving a ticket (research write-ups, domain models, stack
specs) stay as markdown in the repo and are referenced by path from the issue that produced
them. Linear holds the questions, the decisions, and the structure; the repo holds the prose.

## Setup

Already done for team Gauntlet: the labels `wayfinder:map`, `wayfinder:research`,
`wayfinder:prototype`, `wayfinder:grilling`, and `wayfinder:task` all exist.
