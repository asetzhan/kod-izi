"""Request and response models for courses, tasks and assessments (stage 1)."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.enums import CoursePart, GenAiMode, LevelStatus, TaskLevel, TaskStatus
from app.models import Assessment, Course, Task, Topic


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stepik_lesson_id: int | None
    title: str
    url: str
    kind: str


class KnowledgeComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    position: int
    learning_outcomes: str
    lessons: list[LessonOut]
    knowledge_components: list[KnowledgeComponentOut]


class CourseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    part: CoursePart
    source_url: str | None


class CourseOut(CourseSummary):
    description: str
    topics: list[TopicOut]
    can_edit: bool = False

    @classmethod
    def build(cls, course: Course, can_edit: bool) -> "CourseOut":
        out = cls.model_validate(course)
        out.can_edit = can_edit
        return out


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    part: CoursePart = CoursePart.OTHER


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class LessonIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    stepik_lesson_id: int | None = None


class KnowledgeComponentIn(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[\w.\-]+$")
    name: str = Field(min_length=1, max_length=300)


class TopicIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=200)
    position: int = 0
    learning_outcomes: str = Field(default="", max_length=5000)
    lessons: list[LessonIn] = Field(default_factory=list, max_length=50)
    knowledge_components: list[KnowledgeComponentIn] = Field(default_factory=list, max_length=50)


class IdIn(BaseModel):
    id: int


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


Score = Field(ge=0, le=2)


class FeatureScores(BaseModel):
    knowledge_actions: int = Score
    algorithm_freedom: int = Score
    edge_cases: int = Score
    justification: int = Score


class TestCaseIn(BaseModel):
    __test__ = False

    input: str = Field(max_length=8 * 1024 * 1024)
    expected_output: str = Field(max_length=8 * 1024 * 1024)
    is_hidden: bool = True


class TestCaseOut(TestCaseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int


class PublicTestOut(BaseModel):
    """What a student may see of a test: only the public ones, as examples."""

    model_config = ConfigDict(from_attributes=True)

    position: int
    input: str
    expected_output: str


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic_id: int | None = None
    statement_md: str = Field(min_length=1, max_length=100_000)
    input_format: str = Field(default="", max_length=10_000)
    output_format: str = Field(default="", max_length=10_000)
    time_limit_ms: int = Field(default=1000, ge=100, le=20000)
    memory_limit_kb: int = Field(default=262144, ge=16384, le=1048576)
    reference_solution: str = Field(default="", max_length=200_000)
    reference_language: str = Field(default="cpp17", pattern="^cpp(17|20)$")
    source_url: HttpUrl | None = None
    source_note: str = Field(default="", max_length=5000)
    tests: list[TestCaseIn] = Field(default_factory=list, max_length=500)
    knowledge_component_ids: list[int] = Field(default_factory=list, max_length=50)


class TaskCreate(TaskIn):
    course_id: int


class LevelConfirm(BaseModel):
    features: FeatureScores
    # Set only to override the level that the rule derives from the features.
    level: TaskLevel | None = None
    rationale: str = Field(default="", max_length=5000)


class TaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    topic_id: int | None
    external_key: str | None
    title: str
    level: TaskLevel | None
    level_status: LevelStatus
    status: TaskStatus


class TaskOut(TaskSummary):
    """Full task for staff, including hidden tests and the reference solution."""

    statement_md: str
    input_format: str
    output_format: str
    time_limit_ms: int
    memory_limit_kb: int
    reference_solution: str
    reference_language: str
    source_url: str | None
    source_note: str
    features: dict[str, int | None]
    level_rationale: str
    tests: list[TestCaseOut]
    knowledge_component_ids: list[int]

    @classmethod
    def build(cls, task: Task) -> "TaskOut":
        return cls.model_validate(
            {
                **TaskSummary.model_validate(task).model_dump(),
                **{
                    name: getattr(task, name)
                    for name in (
                        "statement_md",
                        "input_format",
                        "output_format",
                        "time_limit_ms",
                        "memory_limit_kb",
                        "reference_solution",
                        "reference_language",
                        "source_url",
                        "source_note",
                        "level_rationale",
                    )
                },
                "features": task.features(),
                "tests": [TestCaseOut.model_validate(t) for t in task.tests],
                "knowledge_component_ids": [k.knowledge_component_id for k in task.kc_links],
            }
        )


class StudentTaskOut(BaseModel):
    """Task as a student sees it: no hidden tests, no reference solution (spec 14.1)."""

    id: int
    title: str
    level: TaskLevel | None
    statement_md: str
    input_format: str
    output_format: str
    time_limit_ms: int
    memory_limit_kb: int
    source_url: str | None
    examples: list[PublicTestOut]

    @classmethod
    def build(cls, task: Task) -> "StudentTaskOut":
        return cls(
            id=task.id,
            title=task.title,
            level=TaskLevel(task.level) if task.level else None,
            statement_md=task.statement_md,
            input_format=task.input_format,
            output_format=task.output_format,
            time_limit_ms=task.time_limit_ms,
            memory_limit_kb=task.memory_limit_kb,
            source_url=task.source_url,
            examples=[PublicTestOut.model_validate(t) for t in task.tests if not t.is_hidden],
        )


class ImportResult(BaseModel):
    task: TaskSummary


class AssessmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    genai_mode: GenAiMode = GenAiMode.FORBIDDEN
    task_ids: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("times must include a time zone")
        return self


class AssessmentCreate(AssessmentIn):
    course_id: int


class AssessmentOut(BaseModel):
    id: int
    course_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    genai_mode: GenAiMode
    task_ids: list[int]

    @classmethod
    def build(cls, a: Assessment) -> "AssessmentOut":
        return cls(
            id=a.id,
            course_id=a.course_id,
            title=a.title,
            starts_at=a.starts_at,
            ends_at=a.ends_at,
            genai_mode=GenAiMode(a.genai_mode),
            task_ids=[link.task_id for link in a.task_links],
        )


class StudentAssessmentOut(BaseModel):
    id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    genai_mode: GenAiMode
    tasks: list[StudentTaskOut]


class LevelRangeIn(BaseModel):
    min: int = Field(ge=0, le=8)
    max: int = Field(ge=0, le=8)
    level: TaskLevel


class LevelRuleIn(BaseModel):
    sum_to_level: list[LevelRangeIn] = Field(min_length=1, max_length=8)


def topic_out(topic: Topic) -> TopicOut:
    return TopicOut.model_validate(topic)
