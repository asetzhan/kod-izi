import type { StudentTask, TaskLevel } from "./types";

/** Olympiad part (spec 4, 10): types of /api/olympiad and /api/contests. */

export interface UnlockState {
  unlocked: boolean;
  required: string[];
  missing: string[];
}

export interface Link {
  name: string;
  url: string;
  purpose: string;
}

export interface OlympiadOverview {
  unlock: UnlockState;
  courses: {
    id: number;
    title: string;
    url: string | null;
    topics: {
      id: number;
      code: string;
      title: string;
      lessons: { title: string; url: string; kind: string }[];
      resources: Link[];
    }[];
  }[];
  practice: { rules: string[]; resources: Link[] };
}

export interface ProblemSummary {
  id: number;
  course_id: number;
  topic_id: number | null;
  title: string;
  level: TaskLevel | null;
  cf_rating: number | null;
  tags: string[];
  time_limit_ms: number;
  memory_limit_kb: number;
  solved: boolean;
}

export interface Recommendations {
  rating: number;
  range: [number, number];
  problems: ProblemSummary[];
}

export interface Hint {
  level: number;
  answer: string;
  blocked: boolean;
  created_at: string;
}

export interface Problem {
  task: StudentTask;
  tags: string[];
  cf_rating: number | null;
  solved: boolean;
  minutes_spent: number;
  editorial_available: boolean;
  editorial_opens_at: string | null;
  editorial_md: string | null;
  hints: Hint[];
  next_hint_level: number | null;
  next_hint_at: string | null;
  in_contest: boolean;
}

export interface OwnTest {
  id: number;
  position: number;
  input: string;
  expected_output: string | null;
}

export interface OwnResult {
  test_id: number;
  status: string;
  verdict: string | null;
  output: string;
  time_ms: number | null;
}

export interface StressResult {
  status: "ok" | "mismatch" | "generator_failed" | "brute_failed" | "solution_failed";
  iterations: number;
  input: string;
  expected: string;
  actual: string;
  detail: string;
}

export type ContestFormat = "icpc" | "ioi";

export interface Contest {
  id: number;
  course_id: number;
  title: string;
  format: ContestFormat;
  starts_at: string;
  ends_at: string;
  freeze_minutes: number;
  penalty_minutes: number;
  task_count: number;
  state: "upcoming" | "running" | "finished";
  task_ids: number[];
  my_virtual: { started_at: string; ends_at: string } | null;
}

export interface ContestDetail extends Contest {
  problems: StudentTask[];
  writing: boolean;
}

export interface StandingsCell {
  solved: boolean;
  wrong: number;
  minute: number | null;
  score: number;
  pending: number;
  tried: boolean;
}

export interface Standings {
  format: ContestFormat;
  frozen: boolean;
  virtual: boolean;
  tasks: { id: number; label: string }[];
  rows: {
    rank: number;
    me: boolean;
    virtual: boolean;
    name: string | null;
    solved: number;
    penalty: number;
    score: number;
    cells: StandingsCell[];
  }[];
}

export interface OlympiadSettings {
  unlock_topics: string[];
  recommend_min: number;
  recommend_max: number;
  start_rating: number;
  editorial_after_minutes: number;
  hint_step_minutes: number;
}
