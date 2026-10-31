// Shapes returned by the backend (backend/app/api/content_schemas.py).

export type TaskLevel = "I" | "II" | "III" | "IV";
export type LevelStatus = "unrated" | "suggested" | "confirmed";
export type TaskStatus = "draft" | "approved";
export type GenAiMode = "forbidden" | "hints_only" | "open";
export type CoursePart = "part1" | "part2" | "other";

export const FEATURE_CODES = [
  "knowledge_actions",
  "algorithm_freedom",
  "edge_cases",
  "justification",
] as const;
export type FeatureCode = (typeof FEATURE_CODES)[number];
export type FeatureScores = Record<FeatureCode, number>;

export interface Lesson {
  id: number;
  stepik_lesson_id: number | null;
  title: string;
  url: string;
  kind: string;
}

export interface KnowledgeComponent {
  id: number;
  code: string;
  name: string;
}

export interface Topic {
  id: number;
  code: string;
  title: string;
  position: number;
  learning_outcomes: string;
  lessons: Lesson[];
  knowledge_components: KnowledgeComponent[];
}

export interface CourseSummary {
  id: number;
  title: string;
  part: CoursePart;
  source_url: string | null;
}

export interface Course extends CourseSummary {
  description: string;
  topics: Topic[];
  can_edit: boolean;
}

export interface TaskSummary {
  id: number;
  course_id: number;
  topic_id: number | null;
  external_key: string | null;
  title: string;
  level: TaskLevel | null;
  level_status: LevelStatus;
  status: TaskStatus;
}

export interface TestCase {
  id?: number;
  position?: number;
  input: string;
  expected_output: string;
  is_hidden: boolean;
}

export interface Task extends TaskSummary {
  statement_md: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_kb: number;
  reference_solution: string;
  reference_language: string;
  source_url: string | null;
  source_note: string;
  features: Record<FeatureCode, number | null>;
  level_rationale: string;
  tests: TestCase[];
  knowledge_component_ids: number[];
}

export interface LevelSuggestion {
  features: FeatureScores;
  level: TaskLevel;
  rationale: string;
  saved: boolean;
}

export interface Assessment {
  id: number;
  course_id: number;
  title: string;
  starts_at: string;
  ends_at: string;
  genai_mode: GenAiMode;
  task_ids: number[];
}

export interface LevelRule {
  sum_to_level: { min: number; max: number; level: TaskLevel }[];
}

// Stage 2: workspace (backend/app/api/workspace.py).

export type Verdict = "OK" | "WA" | "TLE" | "MLE" | "RE" | "CE";
export type RunStatus =
  | "finished"
  | "compile_error"
  | "runtime_error"
  | "time_limit"
  | "memory_limit"
  | "internal_error";

export interface Example {
  position: number;
  input: string;
  expected_output: string;
}

export interface StudentTask {
  id: number;
  title: string;
  level: TaskLevel | null;
  statement_md: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_kb: number;
  source_url: string | null;
  examples: Example[];
}

export interface StudentAssessment {
  id: number;
  title: string;
  starts_at: string;
  ends_at: string;
  genai_mode: GenAiMode;
  tasks: StudentTask[];
}

export interface WorkSession {
  session_id: string;
  task: StudentTask;
  assessment_id: number | null;
  ends_at: string | null;
  code: string;
}

export interface RunOutput {
  status: RunStatus;
  stdout: string;
  stderr: string;
  compile_output: string;
  time_ms: number | null;
  memory_kb: number | null;
}

export interface TestRun {
  position: number;
  verdict: Verdict;
  input: string;
  expected_output: string;
  actual_output: string;
  time_ms: number | null;
}

export interface TestsOutput {
  compile_output: string;
  results: TestRun[];
}

export interface SubmissionResult {
  id: number;
  task_id: number;
  assessment_id: number | null;
  status: "queued" | "running" | "done" | "error";
  verdict: Verdict | null;
  tests_passed: number;
  tests_total: number;
  max_time_ms: number | null;
  max_memory_kb: number | null;
  compile_output: string;
  results: { position: number; is_hidden: boolean; verdict: Verdict }[];
  created_at: string;
  explanation: string | null;
  questions: { question: string; answer: string | null }[];
}

export interface StudentActivity {
  user_id: number;
  full_name: string;
  sessions: string[];
  large_pastes: number;
  pasted_chars: number;
  focus_lost: number;
  late_events: number;
  last_verdicts: Record<string, Verdict | null>;
}
