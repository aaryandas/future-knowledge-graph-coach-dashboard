"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type RefObject,
} from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { SendIcon } from "./icons";
import type {
  CoachActionResolution,
  CoachTaskSnapshot,
  DashboardMessage,
  DataActionPart,
  DataBriefPart,
  DataConstraintsPart,
  DataPlanPart,
  DataSourcesPart,
  DataTracePart,
} from "@/lib/parts";
import { CoachActionCard } from "./coach-action-card";
import { CopilotChart } from "./copilot-chart";

const quickPrompts = [
  {
    id: "show-brief",
    label: "Brief",
    message: "Show me the brief",
  },
  {
    id: "adherence-trend",
    label: "Adherence",
    message: "How's adherence trending?",
  },
  {
    id: "sleep-week",
    label: "Sleep",
    message: "Sleep this week",
  },
  {
    id: "changes",
    label: "4 weeks",
    message: "What changed since last week?",
  },
] as const;

interface CopilotSidebarProps {
  memberId: string;
  memberName: string;
  initialMessages: DashboardMessage[];
  coachTasks: ReadonlyArray<CoachTaskSnapshot>;
  composerValue: string;
  composerRef: RefObject<HTMLInputElement | null>;
  hasPlan: boolean;
  onComposerChange(value: string): void;
  onConstraints(part: DataConstraintsPart): void;
  onBusyChange(busy: boolean): void;
  onPlan(part: DataPlanPart): void;
  onSubmitterChange(submitter: ((message: string) => void) | null): void;
  onTrace(part: DataTracePart): void;
}

export function CopilotSidebar({
  memberId,
  memberName,
  initialMessages,
  coachTasks,
  composerValue,
  composerRef,
  hasPlan,
  onComposerChange,
  onConstraints,
  onBusyChange,
  onPlan,
  onSubmitterChange,
  onTrace,
}: CopilotSidebarProps) {
  const logEndRef = useRef<HTMLDivElement>(null);
  const transport = useMemo(
    () =>
      new DefaultChatTransport<DashboardMessage>({
        api: `/api/members/${encodeURIComponent(memberId)}/copilot`,
        prepareSendMessagesRequest({ id, messages, body, api }) {
          if (
            body?.surface === "coach-action" &&
            typeof body.actionId === "string" &&
            isCoachActionResolution(body.resolution)
          ) {
            return {
              api: `/api/members/${encodeURIComponent(memberId)}/copilot/actions/${encodeURIComponent(body.actionId)}/confirm`,
              body: body.resolution,
            };
          }
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
  const resolutionMessagesRef = useRef<DashboardMessage[] | null>(null);
  const {
    messages,
    sendMessage,
    regenerate,
    setMessages,
    status,
    error,
    clearError,
  } =
    useChat<DashboardMessage>({
      id: memberId,
      messages: initialMessages,
      transport,
      onData(part) {
        if (part.type === "data-plan") {
          onPlan({ type: "data-plan", data: part.data });
        }
        if (part.type === "data-constraints") {
          onConstraints({ type: "data-constraints", data: part.data });
        }
        if (part.type === "data-trace") {
          onTrace({ type: "data-trace", data: part.data });
        }
      },
      onFinish() {
        resolutionMessagesRef.current = null;
      },
    });
  const isBusy = status === "submitted" || status === "streaming";
  const currentCoachTasks = useMemo(() => {
    const tasks = new Map(
      coachTasks.map((task) => [task.id, task] as const),
    );
    for (const message of messages) {
      for (const part of message.parts) {
        if (part.type !== "data-brief") {
          continue;
        }
        for (const task of part.data.coach_tasks) {
          tasks.set(task.node_id, {
            id: task.node_id,
            text: task.text,
            status: task.status,
          });
        }
      }
    }
    return tasks;
  }, [coachTasks, messages]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, status]);

  useEffect(() => {
    if (status === "error" && resolutionMessagesRef.current !== null) {
      setMessages(resolutionMessagesRef.current);
      resolutionMessagesRef.current = null;
    }
  }, [setMessages, status]);

  const submitMessage = useCallback(
    (text: string) => {
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
    },
    [clearError, hasPlan, isBusy, onComposerChange, sendMessage],
  );

  useEffect(() => {
    onSubmitterChange(submitMessage);
    return () => onSubmitterChange(null);
  }, [onSubmitterChange, submitMessage]);

  useEffect(() => {
    onBusyChange(isBusy);
    return () => onBusyChange(false);
  }, [isBusy, onBusyChange]);

  async function resolveCoachAction(
    messageId: string,
    actionId: string,
    resolution: CoachActionResolution,
  ) {
    if (isBusy) {
      throw new Error("The Copilot stream is busy.");
    }
    clearError();
    resolutionMessagesRef.current = messages;
    await regenerate({
      messageId,
      body: {
        surface: "coach-action",
        actionId,
        resolution,
      },
    });
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
            <CopilotMessage
              key={message.id}
              message={message}
              currentCoachTasks={currentCoachTasks}
              onResolveAction={resolveCoachAction}
            />
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
        <QuickPromptPalette disabled={isBusy} onSelect={submitMessage} />
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

export function CopilotMessage({
  message,
  currentCoachTasks,
  onResolveAction,
}: {
  message: DashboardMessage;
  currentCoachTasks?: ReadonlyMap<string, CoachTaskSnapshot>;
  onResolveAction?(
    messageId: string,
    actionId: string,
    resolution: CoachActionResolution,
  ): Promise<void> | void;
}) {
  const textParts = message.parts.filter((part) => part.type === "text");
  const chartParts = message.parts.filter(
    (part) => part.type === "data-chart",
  );
  const sourceParts = message.parts.filter(
    (part) => part.type === "data-sources",
  );
  const briefParts = message.parts.filter(
    (part) => part.type === "data-brief",
  );
  const actionParts = message.parts.filter(
    (part) => part.type === "data-action",
  );
  if (
    textParts.length === 0 &&
    chartParts.length === 0 &&
    sourceParts.length === 0 &&
    briefParts.length === 0 &&
    actionParts.length === 0
  ) {
    return null;
  }

  return (
    <article
      className="copilot-message"
      data-message-id={message.id}
      data-role={message.role}
    >
      {textParts.length === 0 &&
      chartParts.length === 0 &&
      sourceParts.length === 0 &&
      briefParts.length === 0 ? null : (
        <div
          className="copilot-message-body"
          data-wide={
            chartParts.length > 0 || briefParts.length > 0 ? "" : undefined
          }
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
          {briefParts.map((part, index) => (
            <BriefBarriers
              key={index}
              part={{ type: "data-brief", data: part.data }}
            />
          ))}
          {sourceParts.map((part, index) => (
            <SourceChips
              key={index}
              part={{ type: "data-sources", data: part.data }}
            />
          ))}
        </div>
      )}
      {actionParts.map((part) => {
        const actionPart: DataActionPart = {
          type: "data-action",
          data: part.data,
        };
        const action = actionPart.data.action;
        const currentCoachTask =
          action.kind === "update-brief-task"
            ? (currentCoachTasks?.get(action.coach_task_id) ?? null)
            : null;
        return (
          <CoachActionCard
            key={actionPart.data.action_id}
            part={actionPart}
            currentCoachTask={currentCoachTask}
            onResolve={(resolution) =>
              onResolveAction?.(
                message.id,
                actionPart.data.action_id,
                resolution,
              )
            }
          />
        );
      })}
    </article>
  );
}

export function QuickPromptPalette({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect(message: string): void;
}) {
  return (
    <div className="copilot-quick-actions" aria-label="Copilot quick prompts">
      {quickPrompts.map(({ id, label, message }) => (
        <button
          key={id}
          type="button"
          className="copilot-chip"
          data-quick-prompt={id}
          aria-label={`Ask Copilot: ${message}`}
          disabled={disabled}
          onClick={() => onSelect(message)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function isCoachActionResolution(value: unknown): value is CoachActionResolution {
  if (typeof value !== "object" || value === null || !("decision" in value)) {
    return false;
  }
  return value.decision === "confirm" || value.decision === "discard";
}

function BriefBarriers({ part }: { part: DataBriefPart }) {
  const { barriers, churn_risk_level: churnRiskLevel } = part.data;

  return (
    <section className="copilot-brief" aria-label="Barriers">
      <header>
        <h3>Barriers</h3>
        <span data-risk-level={churnRiskLevel}>
          {formatLabel(churnRiskLevel)} churn risk
        </span>
      </header>
      {barriers.length === 0 ? (
        <p className="copilot-barriers-empty">No evidenced Barriers.</p>
      ) : (
        <ul className="copilot-barriers">
          {barriers.map((barrier) => (
            <li key={barrier.node_id} data-barrier-id={barrier.node_id}>
              <div className="copilot-barrier-heading">
                <strong>{formatLabel(barrier.kind)}</strong>
                <span data-risk-level={barrier.risk_level}>
                  {formatLabel(barrier.risk_level)}
                </span>
              </div>
              <p>{barrier.reason}</p>
              <ul
                className="copilot-evidence"
                aria-label={`Evidence for ${formatLabel(barrier.kind)}`}
              >
                {barrier.evidence_node_ids.map((nodeId) => (
                  <li key={nodeId}>{nodeId}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SourceChips({ part }: { part: DataSourcesPart }) {
  if (part.data.sources.length === 0) {
    return <p className="copilot-sources-empty">No graph sources</p>;
  }
  return (
    <ul className="copilot-sources" aria-label="Sources">
      {part.data.sources.map((source, index) => (
        <li
          key={`${source.tool}-${index}`}
          data-source-tool={source.tool}
          title={source.node_ids.join(", ")}
          aria-label={`${formatToolName(source.tool)} source: ${source.node_ids.length} graph ${source.node_ids.length === 1 ? "record" : "records"}`}
        >
          <span>{formatToolName(source.tool)}</span>
          <span aria-hidden="true">{source.node_ids.length}</span>
        </li>
      ))}
    </ul>
  );
}

function formatToolName(tool: string): string {
  return tool.replace(/^get_/, "").replaceAll("_", " ");
}

function formatLabel(value: string): string {
  const label = value.replaceAll("-", " ").replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
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
