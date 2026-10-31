"""The four roles from spec section 2."""

from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    COACH = "coach"
    ADMIN = "admin"
