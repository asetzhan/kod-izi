from app.models.analysis import (
    AiGrade,
    AiMessage,
    Chunk,
    LlmUsage,
    Material,
    MaterialBinding,
    MaterialVersion,
    Rubric,
    RubricCriterion,
)
from app.models.assessment import Assessment, AssessmentTask
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.core import (
    Explanation,
    Submission,
    SubmissionTestResult,
    TraceEvent,
    WorkSession,
)
from app.models.course import (
    Course,
    CourseGroup,
    CourseTeacher,
    ExternalLesson,
    KnowledgeComponent,
    Topic,
)
from app.models.group import Group, GroupMember, GroupTeacher
from app.models.olympiad import (
    ContestParticipation,
    SimilarityReport,
    StudentTest,
    TopicResource,
)
from app.models.panel import (
    ComponentEntry,
    ComponentEntryVersion,
    ComponentSetting,
    Observation,
    RubricExample,
    TaskAssignment,
    TeacherGrade,
)
from app.models.setting import AppSetting
from app.models.task import Task, TaskKnowledgeComponent, TestCase
from app.models.user import User, UserRole

__all__ = [
    "AiGrade",
    "AiMessage",
    "AppSetting",
    "Assessment",
    "AssessmentTask",
    "AuditLog",
    "Chunk",
    "ComponentEntry",
    "ComponentEntryVersion",
    "ComponentSetting",
    "ContestParticipation",
    "Course",
    "CourseGroup",
    "CourseTeacher",
    "Explanation",
    "ExternalLesson",
    "Group",
    "GroupMember",
    "GroupTeacher",
    "KnowledgeComponent",
    "LlmUsage",
    "Material",
    "MaterialBinding",
    "MaterialVersion",
    "Observation",
    "RefreshToken",
    "Rubric",
    "RubricCriterion",
    "RubricExample",
    "SimilarityReport",
    "StudentTest",
    "Submission",
    "SubmissionTestResult",
    "Task",
    "TaskAssignment",
    "TaskKnowledgeComponent",
    "TeacherGrade",
    "TestCase",
    "Topic",
    "TopicResource",
    "TraceEvent",
    "User",
    "UserRole",
    "WorkSession",
]
