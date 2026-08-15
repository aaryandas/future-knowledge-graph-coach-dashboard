import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DataConstraintsPart,
  DataPlanPart,
  DataTracePart,
  ResolvedMention,
} from "@/lib/parts";
import { CopilotSidebarProvider } from "./copilot-sidebar-context";
import { GenerationNotices } from "./generation-notices";
import { MemberDashboard } from "./member-dashboard";
import { WhyThisPlan } from "./why-this-plan";

const planPart: DataPlanPart = {
  type: "data-plan",
  data: {
    warm_up: { section: "warm-up", entries: [], minutes: 0 },
    main: {
      section: "main",
      minutes: 8,
      entries: [
        {
          exercise_id: "exercise-goblet-squat",
          name: "Goblet Squat",
          sets: 2,
          reps: 8,
          hold_minutes: null,
          rest_minutes: 1,
          per_side: false,
          supports_weight: true,
          verdict: "caution",
          caution_note: "Use a pain-free range of motion.",
          minutes: 8,
        },
      ],
    },
    cool_down: { section: "cool-down", entries: [], minutes: 0 },
    requested_minutes: 20,
    packed_minutes: 8,
  },
};

const unresolvedExclusion: ResolvedMention = {
  purpose: "exclusion",
  vocabulary: "Exercise",
  raw_text: "moon burpees",
  concept_id: null,
  confidence: 0.42,
  pass: "none",
  candidates: [
    {
      concept_id: "exercise-burpee",
      preferred_term: "Burpee",
      confidence: 0.81,
    },
  ],
  modifiers: [],
  enforced: false,
  message: "The exclusion was not enforced.",
};

const enforcedExclusion: ResolvedMention = {
  ...unresolvedExclusion,
  raw_text: "Jump Squat",
  concept_id: "exercise-jump-squat",
  confidence: 1,
  pass: "exact",
  candidates: [],
  enforced: true,
  message: null,
};

const constraintsPart: DataConstraintsPart = {
  type: "data-constraints",
  data: {
    targets: [],
    constraints: {
      exclusions: [enforcedExclusion, unresolvedExclusion],
      session_injuries: [],
      equipment_override: null,
    },
    omissions: [
      {
        raw_text: "moon burpees",
        purpose: "exclusion",
        candidates: unresolvedExclusion.candidates,
        message: "This term was not recognized, so it was not enforced.",
      },
    ],
    not_enforced: [],
    session_injury_persistence_suggestions: [],
    failure: null,
  },
};

const tracePart: DataTracePart = {
  type: "data-trace",
  data: [
    {
      kind: "packing",
      action: "filtered",
      section: null,
      exercise_id: "exercise-box-jump",
      reason: "Safety verdict excluded the exercise.",
      used: ["exercise-box-jump"],
      score: null,
      wasGeneratedBy: "pack",
      wasAttributedTo: "graph",
    },
    {
      kind: "packing",
      action: "selected",
      section: "main",
      exercise_id: "exercise-goblet-squat",
      reason: "Selected for the main section.",
      used: ["exercise-goblet-squat"],
      score: 12,
      wasGeneratedBy: "pack",
      wasAttributedTo: "graph",
    },
    {
      kind: "packing",
      action: "cut",
      section: "main",
      exercise_id: "exercise-goblet-squat",
      reason: "Reduced main sets from 3 to 2.",
      used: ["exercise-goblet-squat"],
      score: 10,
      wasGeneratedBy: "pack",
      wasAttributedTo: "graph",
    },
    {
      kind: "substitution",
      dropped_exercise_id: "exercise-jump-squat",
      replacement_exercise_id: "exercise-goblet-squat",
      basis: "movement pattern",
      shared_movement_pattern_ids: ["movement-pattern-squat"],
      shared_muscle_group_ids: [],
      reason:
        "Replaced Jump Squat with Goblet Squat by shared movement pattern: movement-pattern-squat.",
      used: ["exercise-jump-squat", "exercise-goblet-squat"],
      wasGeneratedBy: "pair_substitutions",
      wasAttributedTo: "graph",
    },
  ],
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("generated session surface", () => {
  it("renders typed doses, verdict icons, and caution notes", () => {
    renderDashboard(vi.fn());

    expect(container.textContent).toContain("Goblet Squat");
    expect(container.textContent).toContain("2 sets · 8 reps · 1 min rest");
    expect(container.textContent).toContain("Caution verdict");
    expect(container.textContent).toContain("Use a pain-free range of motion.");
  });

  it("submits composed edit-dose and swap adjustments", () => {
    const submitAdjustment = vi.fn();
    renderDashboard(submitAdjustment);

    clickButton("Edit dose");
    clickButton("Apply dose");
    expect(submitAdjustment).toHaveBeenCalledWith(
      "Adjust Goblet Squat to 2 sets, 8 reps, with 1 min rest.",
    );

    clickButton("Swap");
    expect(submitAdjustment).toHaveBeenCalledWith(
      "Swap Goblet Squat for a suitable alternative in the Main section.",
    );
  });
});

describe("why this plan", () => {
  it("renders removed, replaced, capped, and unrecognized facts without tool names", () => {
    act(() =>
      root.render(
        <WhyThisPlan
          planPart={planPart}
          tracePart={tracePart}
          constraintsPart={constraintsPart}
        />,
      ),
    );

    expect(container.textContent).toContain("Removed “Jump Squat”");
    expect(container.textContent).toContain(
      "Replaced Jump Squat with Goblet Squat",
    );
    expect(container.textContent).toContain("Capped Goblet Squat at 2 sets");
    expect(container.textContent).toContain("Unrecognized term “moon burpees”");
    expect(container.textContent).not.toMatch(
      /pair_substitutions|wasGeneratedBy|evaluate_safety|\bpack\b|\bresolve\b/,
    );
  });

  it("renders only the current turn trace after an adjustment", () => {
    act(() =>
      root.render(
        <WhyThisPlan
          planPart={planPart}
          tracePart={tracePart}
          constraintsPart={constraintsPart}
        />,
      ),
    );

    expect(container.textContent).toContain(
      "Removed one exercise that did not meet the member’s safety constraints.",
    );
    expect(container.textContent).toContain(
      "Replaced Jump Squat with Goblet Squat",
    );
    expect(container.textContent).toContain("Capped Goblet Squat at 2 sets");

    const adjustedTracePart: DataTracePart = {
      type: "data-trace",
      data: [
        ...tracePart.data,
        {
          kind: "packing",
          action: "filtered",
          section: null,
          exercise_id: "exercise-barbell-squat",
          reason: "Required equipment is unavailable.",
          used: ["exercise-barbell-squat"],
          score: null,
          wasGeneratedBy: "pack",
          wasAttributedTo: "graph",
        },
        {
          kind: "packing",
          action: "selected",
          section: "main",
          exercise_id: "exercise-goblet-squat",
          reason: "Selected for the main section.",
          used: ["exercise-goblet-squat"],
          score: 12,
          wasGeneratedBy: "pack",
          wasAttributedTo: "graph",
        },
      ],
    };

    act(() =>
      root.render(
        <WhyThisPlan
          planPart={planPart}
          tracePart={adjustedTracePart}
          constraintsPart={constraintsPart}
        />,
      ),
    );

    expect(container.textContent).toContain("Removed “Jump Squat”");
    expect(container.textContent).toContain("Unrecognized term “moon burpees”");
    expect(container.textContent).toContain(
      "Removed one exercise that need unavailable equipment.",
    );
    expect(container.textContent).not.toContain(
      "Removed one exercise that did not meet the member’s safety constraints.",
    );
    expect(container.textContent).not.toContain(
      "Replaced Jump Squat with Goblet Squat",
    );
    expect(container.textContent).not.toContain(
      "Capped Goblet Squat at 2 sets",
    );
  });

  it("submits a clicked did-you-mean correction", () => {
    const submitAdjustment = vi.fn();
    act(() =>
      root.render(
        <GenerationNotices
          part={constraintsPart}
          onSubmitAdjustment={submitAdjustment}
        />,
      ),
    );

    clickButton("Burpee");
    expect(submitAdjustment).toHaveBeenCalledWith(
      "Adjust today’s session to exclude Burpee instead of “moon burpees”.",
    );
  });
});

function renderDashboard(submitAdjustment: (message: string) => void) {
  act(() =>
    root.render(
      <CopilotSidebarProvider
        planPart={planPart}
        tracePart={tracePart}
        constraintsPart={constraintsPart}
        adjustmentBusy={false}
        prefillMessage={vi.fn()}
        submitAdjustment={submitAdjustment}
      >
        <MemberDashboard part={null} />
      </CopilotSidebarProvider>,
    ),
  );
}

function clickButton(label: string) {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  if (button === undefined) {
    throw new Error(`Button not found: ${label}`);
  }
  act(() => button.click());
}
