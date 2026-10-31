"""Model component entries (ФТ-07, spec 6): sources, versions, suggestions.

Rules from spec 6:
- every entry carries its source: auto, teacher or auto_edited;
- what the teacher wrote or changed is never replaced by regeneration: the new automatic
  value becomes a suggestion the teacher accepts or rejects;
- every change is a version (who, when, what); any version can be restored;
- the automatic value and the teacher's value are stored apart;
- automatic filling of a component can be switched off.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EntrySource
from app.models import ComponentEntry, ComponentEntryVersion, ComponentSetting

COMPONENT_NAMES = {
    1: "goal",  # Педагогикалық-мақсаттық
    2: "criteria",  # Критерийлік-бағалау
    3: "tasks",  # Деңгейлік-тапсырма
    4: "analysis",  # Интеллектуалдық-талдау
    5: "interpretation",  # Нәтижелік-интерпретациялық
}


class EntryError(ValueError):
    pass


def auto_enabled(db: Session, course_id: int, component: int) -> bool:
    setting = db.get(ComponentSetting, (course_id, component))
    return setting is None or setting.auto_enabled


def set_auto_enabled(db: Session, course_id: int, component: int, enabled: bool) -> None:
    setting = db.get(ComponentSetting, (course_id, component))
    if setting is None:
        db.add(ComponentSetting(course_id=course_id, component=component, auto_enabled=enabled))
    else:
        setting.auto_enabled = enabled


def _add_version(
    entry: ComponentEntry, value: Any, source: EntrySource, author_id: int | None, note: str
) -> None:
    entry.versions.append(
        ComponentEntryVersion(
            version=len(entry.versions) + 1,
            value=value,
            source=source.value,
            author_id=author_id,
            note=note[:200],
        )
    )


def find_entry(
    db: Session, component: int, subject_type: str, subject_id: int, key: str
) -> ComponentEntry | None:
    return db.scalar(
        select(ComponentEntry).where(
            ComponentEntry.component == component,
            ComponentEntry.subject_type == subject_type,
            ComponentEntry.subject_id == subject_id,
            ComponentEntry.key == key,
        )
    )


def upsert_auto(
    db: Session,
    course_id: int,
    component: int,
    subject_type: str,
    subject_id: int,
    key: str,
    value: Any,
) -> ComponentEntry | None:
    """Store an automatic value; returns None when the teacher switched filling off."""
    if not auto_enabled(db, course_id, component):
        return None
    entry = find_entry(db, component, subject_type, subject_id, key)
    if entry is None:
        entry = ComponentEntry(
            course_id=course_id,
            component=component,
            subject_type=subject_type,
            subject_id=subject_id,
            key=key,
            value=value,
            auto_value=value,
            source=EntrySource.AUTO.value,
        )
        _add_version(entry, value, EntrySource.AUTO, None, "generated")
        db.add(entry)
        db.flush()
        return entry
    entry.auto_value = value
    if entry.source == EntrySource.AUTO.value:
        if entry.value != value:
            entry.value = value
            _add_version(entry, value, EntrySource.AUTO, None, "regenerated")
        entry.suggestion = None
    elif entry.value != value:
        # The teacher's value stays; the new automatic one waits as a suggestion.
        entry.suggestion = value
    return entry


def edit(db: Session, entry: ComponentEntry, value: Any, user_id: int, note: str = "") -> None:
    source = EntrySource.AUTO_EDITED if entry.auto_value is not None else EntrySource.TEACHER
    entry.value = value
    entry.source = source.value
    entry.updated_by = user_id
    _add_version(entry, value, source, user_id, note or "edited")


def create_manual(
    db: Session,
    course_id: int,
    component: int,
    subject_type: str,
    subject_id: int,
    key: str,
    value: Any,
    user_id: int,
) -> ComponentEntry:
    if find_entry(db, component, subject_type, subject_id, key) is not None:
        raise EntryError("entry_exists")
    entry = ComponentEntry(
        course_id=course_id,
        component=component,
        subject_type=subject_type,
        subject_id=subject_id,
        key=key,
        value=value,
        auto_value=None,
        source=EntrySource.TEACHER.value,
        updated_by=user_id,
    )
    _add_version(entry, value, EntrySource.TEACHER, user_id, "created")
    db.add(entry)
    db.flush()
    return entry


def revert(db: Session, entry: ComponentEntry, version: int, user_id: int) -> None:
    """Restore any earlier version; the restore itself becomes a new version."""
    target = next((v for v in entry.versions if v.version == version), None)
    if target is None:
        raise EntryError("unknown_version")
    entry.value = target.value
    entry.source = target.source
    entry.updated_by = user_id
    _add_version(entry, target.value, EntrySource(target.source), user_id, f"restored v{version}")


def accept_suggestion(db: Session, entry: ComponentEntry, user_id: int) -> None:
    if entry.suggestion is None:
        raise EntryError("no_suggestion")
    entry.value = entry.suggestion
    entry.source = EntrySource.AUTO.value
    entry.suggestion = None
    entry.updated_by = user_id
    _add_version(entry, entry.value, EntrySource.AUTO, user_id, "suggestion accepted")


def reject_suggestion(db: Session, entry: ComponentEntry, user_id: int) -> None:
    if entry.suggestion is None:
        raise EntryError("no_suggestion")
    entry.suggestion = None
    entry.updated_by = user_id
