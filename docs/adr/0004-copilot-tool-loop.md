# ADR-0004: The copilot is a tool-loop agent with a confirm gate on writes

**Status:** Accepted (2026-08-13)

## Context

ADR-0003 rejected a tool-calling loop for the workout generator. The copilot is a
different surface. Its work is open question-answering over the member context graph
(KG2). No safety floor sits in its path. The question set is open: the coach can ask
follow-up questions that no closed router can list in advance. The PRD grades this
surface on grounded answers, charts, the morning brief, and churn risk. The coach can
also act from this surface: send the member a message, or update a brief task.

## Decision

The copilot is a LangGraph tool-calling agent. The agent has typed read tools over KG2.
Each read tool is one documented graph traversal. Each read tool returns typed JSON plus
the node ids it read. The loop stops after five tool rounds per turn.

Grounding is structural. Every rendered number comes from a tool data part. The LLM
writes prose around the data. It never emits the numbers that render. Each answer
carries a sources part with the tools called and the nodes read.

Charts come from one tool with a closed set of chart kinds. The server builds the
series from KG2. The frontend renders each kind. The LLM selects the kind and the
window. It never supplies data points.

Writes pass a confirm gate. A write tool call pauses on a LangGraph interrupt. The
panel shows an action card with the exact change. Only a coach click executes the
write. A confirmed write goes to the member file with an atomic write.

## Consequences

- The two surfaces have two runtime shapes. The generator is a pipeline because safety
  and latency demand it (ADR-0003). The copilot is a loop because open Q&A demands it.
  The reason for each shape is on record here.
- A wrong tool choice by the model degrades to a wrong or empty answer. It cannot
  degrade to an unsafe plan or a silent data change.
- The LLM cannot change member data. Only a coach click can. No undo story is needed.
- Rejected: whole-context stuffing (no retrieval; the graph does no visible work; dies
  when KG2 grows). Rejected: a closed router with fetch-and-summarize (open follow-up
  questions fall off any closed intent set). Rejected: direct execution of writes (an
  LLM write to member data with no human check conflicts with the audit ethos).
- Ceiling: the chart kinds are a closed set of four. A new chart is a new enum value, a
  server assembler, and a renderer.
