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
  teacher_requirements: string;
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
  genai_mode: GenAiMode;
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
  last_submissions: Record<string, number | null>;
}

// Stage 3 (backend/app/api/analysis.py).

export type CriterionCode =
  | "understanding"
  | "algorithm"
  | "correctness"
  | "code_quality"
  | "debugging"
  | "explanation";

export interface RubricCriterion {
  code: CriterionCode;
  name: string;
  indicators: string;
  data_sources: string;
  descriptor_low: string;
  descriptor_mid: string;
  descriptor_high: string;
}

export interface Rubric {
  weight_f: number;
  weight_e: number;
  weight_a: number;
  component_scales: Record<"F" | "E" | "A", string>;
  criteria: RubricCriterion[];
}

export type MaterialKind = "book" | "lecture" | "problems";

export interface MaterialVersion {
  id: number;
  version: number;
  filename: string;
  mime: string;
  size_bytes: number;
  status: "pending" | "ready" | "rejected" | "failed";
  error: string | null;
  pages: number | null;
  created_at: string;
}

export interface Material {
  id: number;
  course_id: number;
  title: string;
  author: string;
  kind: MaterialKind;
  versions: MaterialVersion[];
}

export interface Binding {
  id?: number;
  material_id?: number;
  topic_id: number | null;
  task_id: number | null;
  assessment_id: number | null;
  chapter: string;
  page_from: number | null;
  page_to: number | null;
  is_assessment_basis: boolean;
  requirements: string;
}

export interface Evidence {
  type: "test" | "code_line" | "explanation" | "genai_log" | "book";
  ref: string;
  quote: string;
}

export interface AiGrade {
  id: number;
  submission_id: number;
  status: "ready" | "needs_review" | "failed";
  criteria: { code: CriterionCode; level: "low" | "mid" | "high"; evidence: Evidence[]; confidence: number }[];
  components: { F: number | null; E: number | null; A: number | null };
  score: number | null;
  interpretation: string;
  feedback: string;
  next_step: string;
  flags: string[];
  review_reasons: string[];
  model: string;
  prompt_version: string;
  weights: Record<string, number>;
  fragment_ids: number[];
  attempts: number;
  created_at: string;
}

export interface ChunkView {
  id: number;
  material_id: number;
  material_title: string;
  version: number;
  chapter: string;
  page: number | null;
  text: string;
}

export interface AssistantMessage {
  id: number;
  question: string;
  answer: string;
  blocked: boolean;
  created_at: string;
}

export interface StaffSubmission extends SubmissionResult {
  static_analysis?: unknown;
}

// Stage 4 (backend/app/api/panel.py).

export type EntrySource = "auto" | "teacher" | "auto_edited";

export interface ComponentSummary {
  component: number;
  name: string;
  auto_enabled: boolean;
  entries: number;
  by_source: Record<string, number>;
  suggestions: number;
}

export interface ComponentEntry {
  id: number;
  component: number;
  subject_type: string;
  subject_id: number;
  key: string;
  value: unknown;
  auto_value: unknown;
  source: EntrySource;
  suggestion: unknown;
  updated_by: number | null;
  updated_at: string;
  versions: number;
}

export interface EntryVersion {
  version: number;
  value: unknown;
  source: EntrySource;
  author_id: number | null;
  note: string;
  created_at: string;
}

export interface TeacherGrade {
  id: number;
  submission_id: number;
  criteria: { code: CriterionCode; level: "low" | "mid" | "high" }[];
  components: Record<"F" | "E" | "A", number>;
  score: number;
  feedback: string;
  feedback_source: "ai" | "ai_edited" | "teacher";
  book_refs: string[];
  next_step: string;
  reason: string;
  agrees_with_ai: boolean;
  confirmed_at: string;
}

export interface Observation {
  id: number;
  kind: "oral_defense" | "signal_comment" | "note";
  text: string;
  signal: string | null;
  criterion: CriterionCode | null;
  level: "low" | "mid" | "high" | null;
  created_at: string;
}

export interface StudentResult {
  submission_id: number;
  task_id: number;
  criteria: { code: CriterionCode; name: string; level: "low" | "mid" | "high"; interpretation: string }[];
  score: number;
  feedback: string;
  feedback_source: "ai" | "ai_edited" | "teacher";
  book_refs: string[];
  next_step: string;
  confirmed_at: string;
}

export interface MasteryRow {
  topic_id: number | null;
  level: TaskLevel | null;
  a: number;
  p: number;
  k: number | null;
  mastered: boolean;
}
