"use client";

import { useEffect, useMemo, useRef, type RefObject } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { SendIcon } from "./icons";
import { buttonVariants } from "@/lib/theme";
import type {
  DashboardMessage,
  DataPlanPart,
  DataSourcesPart,
} from "@/lib/parts";

const quickPrompts = [
  { label: "Adherence", message: "How's adherence trending?" },
  { label: "Sleep", message: "Sleep this week" },
  { label: "Messages", message: "Summarize recent messages" },
  { label: "4 weeks", message: "What changed in the last 4 weeks?" },
] as const;

interface CopilotSidebarProps {
  memberId: string;
  memberName: string;
  composerValue: string;
  composerRef: RefObject<HTMLInputElement | null>;
  hasPlan: boolean;
  onComposerChange(value: string): void;
  onPlan(part: DataPlanPart): void;
}

export function CopilotSidebar({
  memberId,
  memberName,
  composerValue,
  composerRef,
  hasPlan,
  onComposerChange,
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
    <div className="copilot-panel flex flex-col px-[18px] pt-[18px] pb-6">
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="text-[15px] font-semibold">Copilot</h2>
        <span className="text-xs text-foreground-subtle">{memberName}</span>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5" aria-label="Quick prompts">
        {quickPrompts.map((prompt) => (
          <button
            key={prompt.label}
            type="button"
            className="press rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground-muted transition-colors hover:border-border-strong hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            disabled={isBusy}
            onClick={() => submitMessage(prompt.message)}
          >
            {prompt.label}
          </button>
        ))}
      </div>

      <div
        className="copilot-log"
        role="log"
        aria-live="polite"
        aria-label="Copilot conversation"
      >
        {messages.length === 0 ? (
          <div className="copilot-empty">
            <p>Ask about {memberName.split(" ")[0]}</p>
            <span>Plan a session or read member context.</span>
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

      <form
        className="flex gap-2 pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          submitMessage(composerValue);
        }}
      >
        <label htmlFor="copilot-composer" className="sr-only">
          Message copilot
        </label>
        <input
          ref={composerRef}
          id="copilot-composer"
          className="min-w-0 flex-1 rounded-[14px] border border-border-strong bg-surface-input px-3.5 py-2.5 text-foreground outline-none placeholder:text-foreground-subtle"
          placeholder="Plan a session · ask about Jordan"
          autoComplete="off"
          value={composerValue}
          onChange={(event) => onComposerChange(event.target.value)}
        />
        <button
          type="submit"
          className={buttonVariants({ size: "icon" })}
          aria-label="Send message"
          disabled={isBusy || composerValue.trim().length === 0}
        >
          <SendIcon className="size-4" />
        </button>
      </form>
    </div>
  );
}

function CopilotMessage({ message }: { message: DashboardMessage }) {
  const textParts = message.parts.filter((part) => part.type === "text");
  const sourceParts = message.parts.filter(
    (part) => part.type === "data-sources",
  );
  if (textParts.length === 0 && sourceParts.length === 0) {
    return null;
  }

  return (
    <article className="copilot-message" data-role={message.role}>
      <div className="copilot-message-body">
        {textParts.map((part, index) => (
          <p key={index}>{part.text}</p>
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
