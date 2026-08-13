# Coding Standards

The loom gate's standards axis reviews every branch against this file. A rule
that is not written here is a proposal, not a rejection. Vocabulary lives in
`CONTEXT.md`. Decisions live in `docs/adr/`. This file does not restate them.

## Backend layout

Six packages under `backend/app/`. Each is a deep module: one documented
interface, implementation hidden behind it.

| Package | Hides | Interface |
|---|---|---|
| `graph/` | JSON ingest, KG1 boot build, SNOMED snapshot, bridging | KG1 builder, `get_member_context(member_id)`, typed accessors |
| `resolver/` | the three passes, aliases, embeddings | `resolve(text, vocab) -> Resolution` |
| `safety/` | the three knowledge layers, escalation matrix | one pure function → verdicts with traces |
| `generation/` | LangGraph pipeline, packer, ConstraintSet | run/adjust a generation session |
| `copilot/` | tool-loop agent, retrieval tools, coach actions | run a copilot turn |
| `api/` | FastAPI routers, AI SDK stream encoding | HTTP surface |

Import rules. Reject a branch that breaks one:

- `graph`, `resolver`, `safety` do not import LangChain, LangGraph, or FastAPI.
- Only `api` imports FastAPI. Only `generation` and `copilot` import LangGraph.
- Only `api` imports pydantic. Domain values are frozen dataclasses.

## Typing

- Every seam function carries full type annotations. Internal helpers may omit
  them.
- Domain values (Resolution, Verdict, TraceEvent, ConstraintSet, Intent, nodes,
  edges) are frozen dataclasses.
- `ty` checks the backend as part of `pnpm lint`. Suppress a false positive
  with a targeted `# ty: ignore[rule]` plus a reason. Reject blanket ignores.

## Errors

- Expected outcomes are values, never exceptions. If a caller must branch on
  it, it is a return type.
- Exceptions mean broken invariants: bad committed data, impossible state.
  Raise at boot or fail the request.
- Reject `except Exception` and bare `except` in domain modules.
- Only `api/` maps exceptions to HTTP responses.
- The two LLM edges catch provider errors and degrade (vector pass offline,
  annotation absent). A provider error never aborts a plan the deterministic
  pipeline already produced.

## Naming

- Use `CONTEXT.md` terms exactly, everywhere. Reject synonyms.
- Node and edge kinds keep the glossary spelling verbatim as `Literal` strings
  (`"exactMatch"`, `"findingSite"`). One spelling across JSON, Python, and
  TypeScript. No translation tables.
- Python identifiers follow PEP 8; ruff enforces.
- Test names state the behavior in glossary terms.
- Frontend: PascalCase components, `use*` hooks, decided `data-*` part names
  verbatim.

## Tests

- Test at the seam. A test that reaches past a module's interface is rejected;
  fix the module shape instead.
- Replace, don't patch: vary behavior by passing a different adapter (fake
  LLM, fixture graph). `monkeypatch` only for env vars.
- Table-driven `parametrize` for resolver and safety cases, including the real
  member strings from `data/member-context.json`.
- CI is offline. No network, no keys, in any test. LLM edges get fakes; the
  vector pass reads committed embedding fixtures.
- Layout: `backend/tests/test_<module>.py`, one file per seam.
- Reject a behavior change without a test at its seam.

## Frontend

- TypeScript strict mode stays on.
- `frontend/lib/parts.ts` types every `data-*` part payload and is the only
  contract with the API. Components take these types as props.
- Data reaches components only through `useChat` and typed parts. No ad-hoc
  `fetch` in components.
- Rendered numbers come from part data, never parsed from streamed prose.
- UI kit: base-ui for interaction primitives (dialogs, popovers, menus),
  recharts for the chart kinds, Sonner for toasts. clsx for conditional
  classes; cva for variant-driven components. One Tailwind token theme in
  `globals.css`; components read tokens, not hard-coded palette values.
  Reject any other UI dependency without an ADR.

## Documentation

- A docstring appears only where the signature and names fail to say it. One
  line; a second only for a real invariant or error mode. No Args/Returns
  boilerplate.
- Two load-bearing exceptions: retrieval tool docstrings (the LLM reads them,
  they name the traversal in glossary edge terms) and safety or packing
  constraints a reader cannot infer.
- Comments state constraints, one line each. Reject narration comments as
  slop.
- Human-facing prose follows ASD-STE100 Simplified Technical English.
