---
name: Future Coach
description: A compact daily-signal workspace for member context, session programming, and grounded coaching support.
colors:
  ink: "#0b0f14"
  ink-muted: "#2a2f36"
  ink-subtle: "#6b7280"
  canvas: "#fafaf9"
  surface: "#ffffff"
  surface-raised: "#f4f3f0"
  border: "#e7e6e3"
  border-strong: "#cecec8"
  accent: "#3428c7"
  accent-muted: "#eeeaf7"
  attention: "#8a6500"
  attention-muted: "#fff4c7"
  success: "#1b7a4b"
  success-muted: "#e2f2e8"
  brief-action: "#df4f17"
  peach: "#f8d7c3"
  cream: "#f4ebda"
  lilac: "#ddd5ee"
typography:
  display:
    fontFamily: "var(--font-season-mix), Georgia, serif"
    fontSize: "clamp(2.1rem, 2.8vw, 2.55rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.025em"
  body:
    fontFamily: "var(--font-season-sans), Helvetica Neue, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: "normal"
  navigation:
    fontFamily: "var(--font-season-sans), Helvetica Neue, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.015em"
rounded:
  control: "7px"
  surface: "10px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "28px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0 30px"
    height: "64px"
  chip-action:
    backgroundColor: "{colors.accent-muted}"
    textColor: "{colors.accent}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "54px"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "0 21px"
    height: "104px"
  bounded-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "28px"
---

# Design System: Future Coach

## Overview

**Creative North Star: "The Daily Signal Desk"**

Future Coach is a calm programming desk built around one member and one useful next
decision. Context is compressed into a shared strip, the morning signal is isolated
from the work, and the editable session owns the visual center. Copilot is a permanent
working partner on desktop, not another destination or a stack of AI cards.

The world comes from Future's own identity: Season Mix gives names and section titles
an editorial human voice; Season Sans keeps tables, controls, and health context quick
to scan. Warm off-white and fine gray rules create the field. Peach, lilac, yellow,
green, and Future violet appear only where a role earns them. The result should feel
premium and athletic without becoming glossy, medical, or gamified.

**Key Characteristics:**

- One member context strip above a workout-first split workspace
- Season Mix display type paired with compact Season Sans interface text
- Fine rules and lightly bounded white surfaces instead of a generic card grid
- Semantic color used sparingly for attention, recovery, goals, and active controls
- A single dark confirmation action; supporting actions stay quiet
- Iconoir line icons with current-color strokes and explicit text labels

## Colors

The palette is restrained: neutral ink and warm paper carry most of the product.
Future violet identifies navigation and Copilot actions. Orange belongs to the morning
signal, yellow to attention and constraints, and green to progress or goals. Pastel
brand fields may tint a bounded surface, but they do not become decorative confetti.

**The Earned Color Rule.** Every non-neutral color names a state or action. Violet is
interactive, orange is the brief, yellow is attention, and green is progress or goal.

**The Quiet Field Rule.** Canvas and surfaces stay close in value. Separation comes
from a one-pixel rule before it comes from color, shadow, or a new container.

## Typography

- **Display** (Season Mix, 400, 34–41px, 1.0): wordmark, workspace titles, and major
  section titles. Keep tracking tight and never use it for dense values.
- **Body** (Season Sans, 400, 14px, 1.35): workout data, member context, copy, and
  controls. Use 500 only for short operational labels and exercise names.
- **Navigation** (Season Sans, 400, 18px): centered top-level destinations. The active
  state is color plus a four-pixel underline, not added weight.
- **Support text** (Season Sans, 400, 10–13px): mobile field labels, graph metadata,
  and quiet status. Keep contrast sufficient and copy brief.

**The Season Pair Rule.** Season Mix provides identity and hierarchy; Season Sans
does the work. Do not introduce a third expressive face or use the display face in a
table.

## Layout

The desktop shell uses two full-width header bands: a 92px navigation row and a 68px
member strip. Below them, the application divides into a flexible dashboard and a
minimum 29rem Copilot rail at roughly 69/31. The dashboard uses 31–32px gutters, a
brief separated from the session by 28px, and dense 88px table rows. Copilot preserves
calm working room above controls, but the main workspace does not add empty sections.

At 980px and below, Copilot becomes a right-side drawer with a scrim, focus containment,
Escape dismissal, and focus return. The member strip scrolls horizontally. At 720px,
navigation wraps below the wordmark, the session table becomes a compact three-column
field grid, and the confirmation action becomes full width.

**The Workout Leads Rule.** The session is the largest bounded object in the first
viewport. Brief, context, and Copilot support the session; none competes with it.

**The Compact Operate Rule.** Vertical space must help scanning or manipulation.
Avoid placeholder sections, repeated explanations, and ornamental gaps.

## Elevation & Depth

The working application is flat by default. One-pixel borders, tonal shifts, and the
fixed split divider establish depth. Shadows are reserved for true overlays such as
the mobile Copilot drawer and for the separate sign-in scene. Focus uses a violet
outline or a restrained three-pixel violet wash.

**The Bounded-Not-Floating Rule.** Dashboard surfaces sit on the canvas; they do not
hover over it. Use a shadow only when an element actually moves above the page.

## Shapes

The product uses gently bounded rectangles: 10px for cards, composer, and graph
surfaces; 7–8px for controls; full pills for quick actions. Borders are one pixel.
Icon buttons use small circular or 6px hover targets without adding permanent chrome.
Avoid mixing many radii or turning every datum into a pill.

## Components

### Navigation

The wordmark anchors the left edge while destinations remain optically centered in the
viewport. Active state uses Future violet and a bottom rule. Copilot never appears as
a desktop navigation item.

### Member Context Strip

Five aligned cells summarize identity, recovery, equipment constraint, adherence, and
goal. Identity stays white; attention cells receive a very light yellow tint; the goal
receives a very light green tint. Every cell pairs an Iconoir glyph with one line of
plain text.

### Morning Brief

A single 10px-radius notification surface with a restrained peach-to-lilac wash. The
orange star starts the scan, the brief label and message remain on one line at desktop,
and the orange text action sits at the far right.

### Session Table

The session is one bounded surface, not a collection of exercise cards. Column labels
and rows share fine horizontal rules. Each row begins with a dotted Iconoir grabber and
ends with pencil and trash actions. Add exercise is gray and quiet. The footer contains
only the dark confirmation action.

### Copilot

The desktop pane is persistent and full height. A muted invitation centers in its
working area; rounded violet action chips sit immediately above the composer. On mobile
the same content becomes a modal drawer with a visible close action.

### Buttons and Fields

The confirmation button is ink on white in reverse and is the only dark workspace
action. Quick actions use a subtle violet fill and outline. Fields stay white with a
strong neutral rule; focus changes the rule to violet and adds a low-opacity ring.

## Do's and Don'ts

### Do:

- **Do** make the member, morning signal, and editable session understandable in one scan.
- **Do** use Season Mix for identity and Season Sans for operations.
- **Do** keep Copilot present without letting it displace the workout hierarchy.
- **Do** use the yellow and green member-strip tints only for their semantic roles.
- **Do** use Iconoir line icons and preserve explicit labels or accessible names.
- **Do** keep edit, reorder, add, remove, and confirm interactions keyboard operable.

### Don't:

- **Don't** add generic metric cards, AI-policy narration, or helper copy that repeats the UI.
- **Don't** add Programs, Evidence, or Copilot to the top navigation without new product authority.
- **Don't** use synthetic-draft labels, confirmation disclaimers, or a Back action in the session footer.
- **Don't** color every member fact; neutral identity keeps the semantic tints meaningful.
- **Don't** introduce glass, glow, heavy shadows, or a new icon family into the working shell.
- **Don't** expand mobile exercise rows into six full-width stacked form lines.
