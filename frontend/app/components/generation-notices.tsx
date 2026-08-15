"use client";

import { useState } from "react";
import type {
  DataConstraintsPart,
  ResolutionCandidate,
  SessionInjuryPersistenceSuggestion,
} from "@/lib/parts";
import { ShieldIcon } from "./icons";

export function GenerationNotices({
  part,
}: {
  part: DataConstraintsPart | null;
}) {
  const [confirmedSuggestions, setConfirmedSuggestions] = useState<Set<string>>(
    () => new Set(),
  );

  if (part === null) {
    return null;
  }

  const {
    omissions,
    not_enforced: notEnforced,
    session_injury_persistence_suggestions: persistenceSuggestions,
  } = part.data;
  if (
    omissions.length === 0 &&
    notEnforced.length === 0 &&
    persistenceSuggestions.length === 0
  ) {
    return null;
  }

  function confirmSuggestion(suggestion: SessionInjuryPersistenceSuggestion) {
    const key = suggestionKey(suggestion);
    setConfirmedSuggestions((current) => new Set(current).add(key));
  }

  return (
    <aside className="generation-notices" aria-label="Generation notices">
      {notEnforced.map((notice, index) => (
        <section
          key={`${notice.raw_text}-${index}`}
          className="safety-not-enforced"
          role="alert"
        >
          <span className="safety-not-enforced-icon">
            <ShieldIcon className="size-6" />
          </span>
          <div>
            <div className="generation-notice-title-row">
              <h2>Safety not enforced</h2>
              <span>{notice.purpose}</span>
            </div>
            <strong>{notice.raw_text}</strong>
            <p>{notice.message}</p>
            <CandidateList candidates={notice.candidates} />
          </div>
        </section>
      ))}

      {omissions.length === 0 ? null : (
        <section
          className="generation-omissions"
          aria-labelledby="generation-omissions-title"
        >
          <h2 id="generation-omissions-title">Omitted terms</h2>
          <ul>
            {omissions.map((omission, index) => (
              <li key={`${omission.purpose}-${omission.raw_text}-${index}`}>
                <div className="omission-chip">
                  <strong>{omission.raw_text}</strong>
                  <span>{omission.purpose}</span>
                </div>
                <div className="omission-detail">
                  <p>{omission.message}</p>
                  <CandidateList candidates={omission.candidates} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {persistenceSuggestions.map((suggestion, index) => {
        const key = suggestionKey(suggestion);
        const confirmed = confirmedSuggestions.has(key);
        return (
          <section
            key={`${key}-${index}`}
            className="persistence-suggestion"
            data-requires-confirmation={suggestion.requires_confirmation}
            aria-labelledby={`persistence-suggestion-${index}`}
          >
            <div>
              <span className="generation-notice-eyebrow">
                Member record suggestion
              </span>
              <h2 id={`persistence-suggestion-${index}`}>
                Add “{suggestion.raw_text}” to the member record?
              </h2>
              <p>{suggestion.message}</p>
            </div>
            <button
              type="button"
              disabled={confirmed}
              onClick={() => confirmSuggestion(suggestion)}
            >
              {confirmed ? "Suggestion confirmed" : "Confirm suggestion"}
            </button>
          </section>
        );
      })}
    </aside>
  );
}

function CandidateList({
  candidates,
}: {
  candidates: ResolutionCandidate[];
}) {
  if (candidates.length === 0) {
    return null;
  }

  return (
    <div className="generation-candidates" aria-label="Did you mean">
      <span>Did you mean</span>
      <ul>
        {candidates.map((candidate) => (
          <li key={candidate.concept_id}>{candidate.preferred_term}</li>
        ))}
      </ul>
    </div>
  );
}

function suggestionKey(
  suggestion: SessionInjuryPersistenceSuggestion,
): string {
  return `${suggestion.concept_id}:${suggestion.raw_text}`;
}
