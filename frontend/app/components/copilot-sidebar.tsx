"use client";

import { useEffect, useMemo, useRef, type RefObject } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import {
  AdjustIcon,
  ExplainIcon,
  SendIcon,
  ShieldIcon,
} from "./icons";
import type {
  DashboardMessage,
  DataConstraintsPart,
  DataPlanPart,
  DataSourcesPart,
} from "@/lib/parts";
import { CopilotChart } from "./copilot-chart";

const quickPrompts = [
  {
    label: "Adjust",
    message: "Adjust today’s session",
    Icon: AdjustIcon,
  },
  {
    label: "Explain",
    message: "Explain the choices in today’s session",
    Icon: ExplainIcon,
  },
  {
    label: "Constraints",
    message: "Check today’s session against the member’s constraints",
    Icon: ShieldIcon,
  },
] as const;

interface CopilotSidebarProps {
  memberId: string;
  memberName: string;
  composerValue: string;
  composerRef: RefObject<HTMLInputElement | null>;
  hasPlan: boolean;
  onComposerChange(value: string): void;
  onConstraints(part: DataConstraintsPart): void;
  onPlan(part: DataPlanPart): void;
}

export function CopilotSidebar({
  memberId,
  memberName,
  composerValue,
  composerRef,
  hasPlan,
  onComposerChange,
  onConstraints,
  onPlan,
}: CopilotSidebarProps) {
  const logEndRef = useRef<HTMLDivElement>(null);
  const transport = useMemo(
    () =>
      new DefaultChatTransport<DashboardMessage>({
        api: `/api/members/${encodeURIComponent(memberId)}/copilot`,
        prepareSendMessagesRequest({ id, messages, body, api }) {
          const isGeneration = body?.surface === "generation";
          return {
            api: isGeneration
              ? `/api/members/${encodeURIComponent(memberId)}/generate`
              : api,
            body: {
              id,
              messages,
              ...(isGeneration ? { window: body?.window } : {}),
            },
          };
        },
      }),
    [memberId],
  );
  const { messages, sendMessage, status, error, clearError } =
    useChat<DashboardMessage>({
      id: memberId,
      transport,
      onData(part) {
        if (part.type === "data-plan") {
          onPlan({ type: "data-plan", data: part.data });
        }
        if (part.type === "data-constraints") {
          onConstraints({ type: "data-constraints", data: part.data });
        }
      },
    });
  const isBusy = status === "submitted" || status === "streaming";

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, status]);

  function submitMessage(text: string) {
    const prompt = text.trim();
    if (!prompt || isBusy) {
      return;
    }
    const isGeneration = isGenerationRequest(prompt, hasPlan);
    clearError();
    onComposerChange("");
    void sendMessage(
      { text: prompt },
      {
        body: isGeneration
          ? {
              surface: "generation",
              window: requestedWindow(prompt) ?? 30,
            }
          : { surface: "copilot" },
      },
    );
  }

  return (
    <div className="copilot-workspace">
      <div
        className="copilot-log"
        role="log"
        aria-live="polite"
        aria-label="Copilot conversation"
      >
        {messages.length === 0 ? (
          <div className="copilot-empty">
            <p>What can I help with today?</p>
          </div>
        ) : (
          messages.map((message) => (
            <CopilotMessage key={message.id} message={message} />
          ))
        )}
        {isBusy ? (
          <div className="copilot-stream-status" role="status">
            <i aria-hidden="true" />
            <span>{status === "submitted" ? "Thinking" : "Writing"}</span>
          </div>
        ) : null}
        {error === undefined ? null : (
          <p className="copilot-error" role="alert">
            Copilot is unavailable. Try again.
          </p>
        )}
        <div ref={logEndRef} />
      </div>

      <div className="copilot-controls">
        <div className="copilot-quick-actions" aria-label="Copilot quick actions">
          {quickPrompts.map(({ label, message, Icon }) => (
            <button
              key={label}
              type="button"
              className="copilot-chip"
              disabled={isBusy}
              onClick={() => submitMessage(message)}
            >
              <Icon className="size-[18px]" />
              {label}
            </button>
          ))}
        </div>
        <form
          className="copilot-composer"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage(composerValue);
          }}
        >
          <label htmlFor="copilot-composer" className="sr-only">
            Ask Copilot about this session
          </label>
          <input
            ref={composerRef}
            id="copilot-composer"
            placeholder={`Ask about ${memberName}…`}
            autoComplete="off"
            value={composerValue}
            onChange={(event) => onComposerChange(event.target.value)}
          />
          <button
            type="submit"
            aria-label="Send message"
            disabled={isBusy || composerValue.trim().length === 0}
          >
            <SendIcon className="size-5" />
          </button>
        </form>
      </div>
    </div>
  );
}

export function CopilotMessage({ message }: { message: DashboardMessage }) {
  const textParts = message.parts.filter((part) => part.type === "text");
  const chartParts = message.parts.filter(
    (part) => part.type === "data-chart",
  );
  const sourceParts = message.parts.filter(
    (part) => part.type === "data-sources",
  );
  if (
    textParts.length === 0 &&
    chartParts.length === 0 &&
    sourceParts.length === 0
  ) {
    return null;
  }

  return (
    <article className="copilot-message" data-role={message.role}>
      <div
        className="copilot-message-body"
        data-has-chart={chartParts.length > 0 ? "" : undefined}
      >
        {textParts.map((part, index) => (
          <p key={index}>{part.text}</p>
        ))}
        {chartParts.map((part, index) => (
          <CopilotChart
            key={index}
            part={{ type: "data-chart", data: part.data }}
          />
        ))}
        {sourceParts.map((part, index) => (
          <SourceChips
            key={index}
            part={{ type: "data-sources", data: part.data }}
          />
        ))}
      </div>
    </article>
  );
}

function SourceChips({ part }: { part: DataSourcesPart }) {
  if (part.data.sources.length === 0) {
    return null;
  }
  return (
    <ul className="copilot-sources" aria-label="Sources">
      {part.data.sources.map((source, index) => (
        <li key={`${source.tool}-${index}`}>{formatToolName(source.tool)}</li>
      ))}
    </ul>
  );
}

function formatToolName(tool: string): string {
  return tool.replace(/^get_/, "").replaceAll("_", " ");
}

function requestedWindow(prompt: string): number | null {
  const match = prompt.match(/\b(\d{1,3})\s*(?:-| )?(?:minutes?|mins?)\b/i);
  return match === null ? null : Number(match[1]);
}

function isGenerationRequest(prompt: string, hasPlan: boolean): boolean {
  const normalized = prompt.toLowerCase();
  const hasGenerationVerb =
    /\b(?:build|create|generate|plan|design|adjust|revise|update|change)\b/.test(
      normalized,
    );
  const hasGenerationNoun =
    /\b(?:workout|session|exercise|warm-up|cool-down|plan)\b/.test(normalized);
  const isTimedRequest =
    requestedWindow(prompt) !== null && !normalized.includes("?");
  const isPlanAdjustment =
    hasPlan &&
    !normalized.includes("?") &&
    /\b(?:add|avoid|exclude|no|only|remove|replace|swap|without|sets?|reps?|rest)\b/.test(
      normalized,
    );
  return (
    (hasGenerationVerb && hasGenerationNoun) ||
    isTimedRequest ||
    isPlanAdjustment
  );
}
