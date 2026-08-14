"use client";

import { useEffect, useState } from "react";
import type { GraphNeighborhoodPart } from "@/lib/parts";

interface GraphNeighborhoodState {
  part: GraphNeighborhoodPart | null;
  error: string | null;
  isLoading: boolean;
}

const initialState: GraphNeighborhoodState = {
  part: null,
  error: null,
  isLoading: true,
};

export function useGraphNeighborhood(memberId: string): GraphNeighborhoodState {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    const controller = new AbortController();

    async function loadGraphNeighborhood() {
      setState(initialState);
      try {
        const response = await fetch(
          `/api/members/${encodeURIComponent(memberId)}/graph-neighborhood`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(`Graph neighborhood request failed: ${response.status}`);
        }
        const part = (await response.json()) as GraphNeighborhoodPart;
        if (part.type !== "data-graph-neighborhood") {
          throw new Error("Graph neighborhood response has an invalid part type");
        }
        setState({ part, error: null, isLoading: false });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({
          part: null,
          error: "Graph neighborhood is unavailable.",
          isLoading: false,
        });
      }
    }

    void loadGraphNeighborhood();
    return () => controller.abort();
  }, [memberId]);

  return state;
}
