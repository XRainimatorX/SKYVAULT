"use client";

/**
 * The shapes the FastAPI service returns (src/skyvault/views) and a hook to
 * fetch them. The UI is served from the same origin as the API.
 */

import { useEffect, useState } from "react";

export type Loss = {
  entity_id: string;
  name: string;
  tick: number;
  by: string;
  by_name: string;
};

export type Overview = {
  scenario_id: string;
  scenario_version: string;
  result: string;
  verdict: string;
  confidence: number;
  score: number;
  profile_id: string;
  perspective: string;
  event_count: number;
  ticks: number;
  scores: Record<string, number>;
  key_findings: string[];
  failure_causes: string[];
  recommended_next_tests: string[];
  flagged_behaviors: string[];
  losses: { faction: string; units: number; lost: Loss[] }[];
};

export type TimelineTick = {
  tick: number;
  lines: string[];
  destroyed: { entity_id: string; name: string; by: string; by_name: string }[];
};

export type Timeline = { scenario_id: string; ticks: TimelineTick[] };

export type Position = [number, number] | string | null;

export type Unit = {
  entity_id: string;
  name: string;
  faction: string;
  position: Position;
  hp: number | null;
  max_hp: number | null;
  status: string;
};

export type Frame = { tick: number; units: Unit[]; lines: string[] };

export type Space =
  | { type: "grid"; width: number; height: number }
  | {
      type: "graph" | "network";
      nodes: { id: string; x: number; y: number }[];
      edges: (string | number)[][];
    };

export type MapData = { space: Space; frames: Frame[] };

export type Chain = {
  action_id: string;
  tick: number;
  actor: string;
  target: string | null;
  event_types: string[];
  events: string[];
  summary: string;
};

export type FailureRow = {
  variable: string;
  applicable: boolean;
  reason: string;
  assumption: string;
  survival: (number | null)[];
  breaking_level: string | null;
  sensitivity: number;
};

export type Failure = {
  scenario_version: string;
  repeat_count: number;
  survival_threshold: number;
  baseline_survival: number;
  fails_without_stress: boolean;
  levels: string[];
  rows: FailureRow[];
  crushing_variable: string | null;
  crushing_assumption: string | null;
  failure_points: string[];
  failure_causes: string[];
  how_fast: { mean_first_loss_tick?: number | null; mean_elimination_tick?: number | null };
  alternatives: {
    scenario_version: string;
    baseline_survival_rate: number;
    verdict: string;
    holds_longer_on: string[];
    breaks_sooner_on: string[];
  }[];
  best_alternative: string | null;
  conditions: string[];
  recommendations: string | null;
};

export type VariantStats = {
  variant_id: string;
  kind: string;
  runs: number;
  win_rate: number;
  win_rate_ci: [number, number];
  failure_frequency: number;
  mean_hp_lost: number;
  mean_risk_events: number;
  mean_score: number;
};

export type BranchRun = {
  branch_id: string;
  action_set: string[];
  result_summary: string;
  evaluation_delta: Record<string, number>;
};

export type ConflictPackage = {
  conflicting_actions: {
    actor_id: string;
    action_id: string;
    system_id: string;
    intent: string;
    conflict_with: string[];
  }[];
  conflicts: { conflict_id: string; proposals: string[]; conflict_types: string[]; reason: string }[];
  branch_runs: BranchRun[];
  baseline: BranchRun;
  recommendation_to_nexus: { required_decision: boolean; decision_reason: string };
};

export type Comparison = {
  batch_id: string;
  perspective: string;
  repeat_count: number;
  total_runs: number;
  variants: VariantStats[];
  metrics: Record<string, string>;
  best: Record<string, string>;
  ranking: string[];
  conflict_package: ConflictPackage | null;
};

export type PackageView = {
  sections: { key: string; label: string; summary: string; raw: unknown }[];
};

export type Loaded<T> =
  | { state: "loading" }
  | { state: "missing"; message: string }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** GET path once; a 404 is "missing" with the server's explanation. */
export function useApi<T>(path: string): Loaded<T> {
  const [loaded, setLoaded] = useState<Loaded<T>>({ state: "loading" });
  useEffect(() => {
    let alive = true;
    fetch(path)
      .then(async (response) => {
        if (response.status === 404) {
          const body = await response.json().catch(() => ({}));
          return { state: "missing", message: body.detail ?? "Not available" } as const;
        }
        if (!response.ok) {
          return { state: "error", message: `${response.status} ${response.statusText}` } as const;
        }
        return { state: "ready", data: (await response.json()) as T } as const;
      })
      .catch((error: Error) => ({ state: "error", message: error.message }) as const)
      .then((next) => {
        if (alive) setLoaded(next);
      });
    return () => {
      alive = false;
    };
  }, [path]);
  return loaded;
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
