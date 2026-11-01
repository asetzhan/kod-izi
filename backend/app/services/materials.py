"""Teaching materials (ФТ-06, ФТ-11, ФТ-35): storage, processing, search."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import ColumnElement, and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import MaterialStatus
from app.llm.base import LLMProvider
from app.models import (
    Assessment,
    Chunk,
    Material,
    MaterialBinding,
    MaterialVersion,
    Task,
)
from app.services.antivirus import ScanError, Scanner
from app.services.extract import ExtractError, detect_type, extract, split, tesseract_ocr

EMBED_BATCH = 32


def storage_path(stored_name: str) -> Path:
    return get_settings().material_dir / stored_name


def store_version(db: Session, material: Material, filename: str, data: bytes) -> MaterialVersion:
    """Check the type, save the file outside the web root, queue the processing."""
    mime = detect_type(filename, data)
    stored_name = f"{uuid.uuid4().hex}.bin"
    path = storage_path(stored_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    version = MaterialVersion(
        material_id=material.id,
        version=len(material.versions) + 1,
        filename=Path(filename).name[:255],
        stored_name=stored_name,
        mime=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status=MaterialStatus.PENDING.value,
    )
    material.versions.append(version)
    db.flush()
    return version


def process_version(
    db: Session, version: MaterialVersion, scanner: Scanner, provider: LLMProvider
) -> None:
    """Antivirus, then text with chapters and pages, then embeddings."""
    data = storage_path(version.stored_name).read_bytes()
    try:
        threat = scanner.scan(data)
    except ScanError as exc:
        version.status = MaterialStatus.FAILED.value
        version.error = str(exc)[:500]
        return
    if threat is not None:
        version.status = MaterialStatus.REJECTED.value
        version.error = f"antivirus: {threat}"[:500]
        storage_path(version.stored_name).unlink(missing_ok=True)
        return
    try:
        pages = extract(version.mime, data, tesseract_ocr if get_settings().ocr_enabled else None)
    except ExtractError as exc:
        version.status = MaterialStatus.FAILED.value
        version.error = str(exc)[:500]
        return
    pieces = split(pages)
    db.execute(delete(Chunk).where(Chunk.version_id == version.id))
    for start in range(0, len(pieces), EMBED_BATCH):
        batch = pieces[start : start + EMBED_BATCH]
        vectors = provider.embed([p.text for p in batch])
        for offset, (piece, vector) in enumerate(zip(batch, vectors, strict=True)):
            db.add(
                Chunk(
                    version_id=version.id,
                    position=start + offset,
                    chapter=piece.chapter,
                    page=piece.page,
                    text=piece.text,
                    embedding=vector,
                )
            )
    version.pages = max((p.page or 0 for p in pages), default=0) or None
    version.status = MaterialStatus.READY.value
    version.error = None


def current_version(material: Material) -> MaterialVersion | None:
    ready = [v for v in material.versions if v.status == MaterialStatus.READY.value]
    return ready[-1] if ready else None


@dataclass(frozen=True)
class Fragment:
    chunk_id: int
    material_title: str
    chapter: str
    page: int | None
    text: str

    @property
    def ref(self) -> str:
        page = f", {self.page}-бет" if self.page is not None else ""
        chapter = f", {self.chapter}" if self.chapter else ""
        return f"{self.material_title}{chapter}{page}"

    def as_block(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "book": self.material_title,
            "chapter": self.chapter,
            "page": self.page,
            "text": self.text,
        }


def basis_bindings(db: Session, task: Task, assessment: Assessment | None) -> list[MaterialBinding]:
    """ФТ-11: «бағалау негізі» bindings of the task, its assessment or its topic."""
    targets = [MaterialBinding.task_id == task.id]
    if assessment is not None:
        targets.append(MaterialBinding.assessment_id == assessment.id)
    if task.topic_id is not None:
        targets.append(MaterialBinding.topic_id == task.topic_id)
    return list(
        db.scalars(
            select(MaterialBinding).where(
                MaterialBinding.is_assessment_basis.is_(True), or_(*targets)
            )
        )
    )


def find_fragments(
    db: Session,
    provider: LLMProvider,
    task: Task,
    assessment: Assessment | None,
    query: str,
    limit: int = 5,
) -> list[Fragment]:
    """Closest fragments of the basis chapters and pages (ФТ-35)."""
    bindings = basis_bindings(db, task, assessment)
    if not bindings:
        return []
    conditions: list[ColumnElement[bool]] = []
    titles: dict[int, str] = {}
    for binding in bindings:
        material = db.get(Material, binding.material_id)
        if material is None or material.course_id != task.course_id:
            continue
        version = current_version(material)
        if version is None:
            continue
        titles[version.id] = material.title
        condition = [Chunk.version_id == version.id]
        if binding.chapter:
            condition.append(Chunk.chapter == binding.chapter)
        if binding.page_from is not None:
            condition.append(Chunk.page >= binding.page_from)
        if binding.page_to is not None:
            condition.append(Chunk.page <= binding.page_to)
        conditions.append(and_(*condition))
    if not conditions:
        return []
    [vector] = provider.embed([query[:4000]])
    rows = db.scalars(
        select(Chunk)
        .where(or_(*conditions))
        .order_by(Chunk.embedding.cosine_distance(vector))
        .limit(limit)
    ).all()
    return [
        Fragment(row.id, titles[row.version_id], row.chapter, row.page, row.text) for row in rows
    ]


def fragments_block(fragments: list[Fragment]) -> str:
    return json.dumps([f.as_block() for f in fragments], ensure_ascii=False)
