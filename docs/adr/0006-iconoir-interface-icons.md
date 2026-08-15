# ADR-0006: Iconoir for interface icons

**Status:** Accepted (2026-08-14)

## Context

GNT-222 selected Base UI for interaction primitives, Recharts for charts, Sonner for
toasts, clsx for conditional classes, and cva for component variants. Base UI does not
provide the interface icon set required by the Future Coach design. That design uses one
consistent family of light line icons for navigation, member context, session editing,
and Copilot controls. Recreating those glyphs locally would add an owned icon surface
without improving product behavior.

## Decision

Use `iconoir-react` for interface icons. Its scope is presentational glyphs in the
frontend. Icons are re-exported through `frontend/app/components/icons.tsx`, use
`currentColor`, and keep an explicit text label or accessible name at the control that
contains them.

Iconoir does not replace the GNT-222 UI kit. Base UI remains the interaction primitive
for dialogs, popovers, and menus. Recharts remains the chart library, Sonner remains the
toast library, and new UI dependencies still require a separate decision.

## Consequences

- The Future Coach surfaces use one icon family instead of hand-drawn one-off SVGs.
- Components depend on the local icon compatibility module, which keeps library imports
  and accessibility defaults in one place.
- The dependency adds client bundle weight for imported glyphs; imports stay limited to
  icons that the interface renders.
- A different icon family or use outside frontend interface glyphs requires a new ADR.
