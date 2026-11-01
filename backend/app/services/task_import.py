"""Task import (ФТ-22): our ZIP format and Polygon packages.

The ZIP format is described in docs/formats/task-package.md. Archives are untrusted:
size, file count and paths are checked, XML is parsed with defusedxml.
"""

import io
import json
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.core.enums import TaskLevel
from app.models.task import FEATURE_CODES

if TYPE_CHECKING:  # type only; parsing always goes through defusedxml
    from xml.etree.ElementTree import Element  # nosec B405

MAX_FILES = 1000
MAX_UNCOMPRESSED = 64 * 1024 * 1024
MAX_TEST_BYTES = 8 * 1024 * 1024
TEST_NAME = re.compile(r"^tests/(\d{1,3})\.(in|out)$")
# Polygon path patterns hold exactly one %d with an optional small width.
POLYGON_PATTERN = re.compile(r"^[\w./-]*%0?[1-9]?d[\w./-]*$")


class TaskImportError(ValueError):
    """`code` is stable for the UI; `message` explains the problem in English."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ImportedTest:
    input: str
    expected_output: str
    is_hidden: bool
    subtask: int = 1  # IOI subtask (ОТ-02)


@dataclass
class TaskDraftData:
    title: str
    statement_md: str
    input_format: str = ""
    output_format: str = ""
    time_limit_ms: int = 1000
    memory_limit_kb: int = 262144
    tests: list[ImportedTest] = field(default_factory=list)
    reference_solution: str = ""
    reference_language: str = "cpp17"
    external_key: str | None = None
    level: TaskLevel | None = None
    features: dict[str, int] | None = None
    level_rationale: str = ""
    topic_code: str | None = None
    knowledge_components: list[str] = field(default_factory=list)
    source_url: str | None = None
    source_note: str = ""
    # Olympiad bank (ОТ-01, ОТ-02, ОТ-05).
    tags: list[str] = field(default_factory=list)
    cf_rating: int | None = None
    editorial_md: str = ""
    subtask_points: dict[str, int] = field(default_factory=dict)


def read_zip(data: bytes) -> dict[str, bytes]:
    """Unpack an archive into {path: bytes} with safety checks."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise TaskImportError("not_zip", "the file is not a ZIP archive") from None
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise TaskImportError("too_many_files", f"more than {MAX_FILES} files")
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise TaskImportError("too_large", "the unpacked archive is too large")
    files: dict[str, bytes] = {}
    for info in infos:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
            raise TaskImportError("unsafe_path", f"unsafe path in archive: {info.filename}")
        try:
            files[str(path)] = archive.read(info)
        except (RuntimeError, NotImplementedError, zipfile.BadZipFile, zlib.error, EOFError):
            raise TaskImportError("bad_archive", f"{info.filename} cannot be unpacked") from None
    return _strip_common_root(files)


def _strip_common_root(files: dict[str, bytes]) -> dict[str, bytes]:
    """Accept archives that wrap everything in one top-level folder."""
    roots = {PurePosixPath(p).parts[0] for p in files}
    if len(roots) == 1 and all(len(PurePosixPath(p).parts) > 1 for p in files):
        return {str(PurePosixPath(*PurePosixPath(p).parts[1:])): v for p, v in files.items()}
    return files


def _text(files: dict[str, bytes], path: str) -> str:
    try:
        return files[path].decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise TaskImportError("bad_encoding", f"{path} is not UTF-8 text") from None


def parse_package(files: dict[str, bytes]) -> TaskDraftData:
    if "problem.xml" in files:
        return parse_polygon(files)
    return parse_native(files)


def parse_native(files: dict[str, bytes]) -> TaskDraftData:
    if "statement.md" not in files:
        raise TaskImportError("missing_statement", "statement.md is missing")
    config: dict[str, Any] = {}
    if "config.json" in files:
        try:
            config = json.loads(_text(files, "config.json"))
        except json.JSONDecodeError as exc:
            raise TaskImportError("bad_config", f"config.json is not valid JSON: {exc}") from None
        if not isinstance(config, dict):
            raise TaskImportError("bad_config", "config.json must be an object")

    statement = _text(files, "statement.md").strip()
    title = config.get("title") or _first_heading(statement)
    if not title:
        raise TaskImportError("missing_title", "no title in config.json or statement.md")

    public = {str(name) for name in config.get("public_tests", ["01"])}
    subtasks = config.get("subtasks", {})
    if not isinstance(subtasks, dict):
        raise TaskImportError("bad_config", "subtasks must map test numbers to subtasks")
    tests = []
    for number in _test_numbers(files):
        tests.append(
            ImportedTest(
                input=_test_text(files, f"tests/{number}.in"),
                expected_output=_test_text(files, f"tests/{number}.out"),
                is_hidden=number not in public,
                subtask=_subtask(subtasks.get(number, 1)),
            )
        )
    if not tests:
        raise TaskImportError("no_tests", "the package has no tests (tests/NN.in, tests/NN.out)")

    try:
        draft = TaskDraftData(
            title=str(title)[:200],
            statement_md=statement,
            input_format=_text(files, "input.md").strip() if "input.md" in files else "",
            output_format=_text(files, "output.md").strip() if "output.md" in files else "",
            time_limit_ms=int(config.get("time_limit_ms", 1000)),
            memory_limit_kb=int(config.get("memory_limit_kb", 262144)),
            tests=tests,
            reference_solution=_text(files, "solution.cpp") if "solution.cpp" in files else "",
            reference_language=str(config.get("reference_language", "cpp17")),
            external_key=_optional_str(config, "key", 64),
            level=TaskLevel(config["level"]) if config.get("level") else None,
            features=_features(config.get("features")),
            level_rationale=str(config.get("level_rationale", "")),
            topic_code=_optional_str(config, "topic", 16),
            knowledge_components=[str(c) for c in config.get("knowledge_components", [])],
            source_url=_http_url(config.get("source_url")),
            source_note=str(config.get("source_note", "")),
            tags=_tags(config.get("tags", [])),
            cf_rating=int(config["cf_rating"]) if config.get("cf_rating") is not None else None,
            editorial_md=_text(files, "editorial.md").strip() if "editorial.md" in files else "",
            subtask_points=_subtask_points(config.get("subtask_points", {})),
        )
    except (TypeError, ValueError) as exc:
        raise TaskImportError("bad_config", f"invalid value in config.json: {exc}") from None
    _check_limits(draft)
    return draft


def _optional_str(config: dict[str, Any], name: str, max_length: int) -> str | None:
    value = config.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise TaskImportError(
            "bad_config", f"{name} must be a string of 1..{max_length} characters"
        )
    return value


def _http_url(value: object) -> str | None:
    """Only http(s) links: the value is later shown to students as a link."""
    if value is None:
        return None
    if not isinstance(value, str) or not re.match(r"^https?://[^\s]{1,490}$", value):
        raise TaskImportError("bad_config", "source_url must be an http(s) URL")
    return value


def _features(raw: object) -> dict[str, int] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != set(FEATURE_CODES):
        raise TaskImportError("bad_config", f"features must have keys {', '.join(FEATURE_CODES)}")
    scores = {code: int(raw[code]) for code in FEATURE_CODES}
    if any(not 0 <= v <= 2 for v in scores.values()):
        raise TaskImportError("bad_config", "feature scores must be 0, 1 or 2")
    return scores


def _subtask(value: object) -> int:
    if not isinstance(value, int) or not 1 <= value <= 50:
        raise TaskImportError("bad_config", "a subtask must be a number from 1 to 50")
    return value


def _tags(raw: object) -> list[str]:
    if not isinstance(raw, list) or len(raw) > 20:
        raise TaskImportError("bad_config", "tags must be a list of at most 20 strings")
    tags = [str(t) for t in raw]
    if any(not re.match(r"^[\w.+ -]{1,40}$", t) for t in tags):
        raise TaskImportError("bad_config", "a tag is 1..40 letters, digits, spaces or .+-_")
    return list(dict.fromkeys(tags))


def _subtask_points(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise TaskImportError("bad_config", "subtask_points must map subtasks to points")
    points = {str(k): int(v) for k, v in raw.items()}
    if points and (
        sum(points.values()) != 100
        or any(not k.isdigit() or not 1 <= int(k) <= 50 for k in points)
        or any(not 0 <= v <= 100 for v in points.values())
    ):
        raise TaskImportError("bad_config", "subtask_points must be 0..100 and add up to 100")
    return points


def _check_limits(draft: TaskDraftData) -> None:
    # Bounds follow Judge0's MAX_CPU_TIME_LIMIT and MAX_MEMORY_LIMIT (judge0.conf).
    if not 100 <= draft.time_limit_ms <= 10000:
        raise TaskImportError("bad_config", "time_limit_ms must be between 100 and 10000")
    if not 16384 <= draft.memory_limit_kb <= 1048576:
        raise TaskImportError("bad_config", "memory_limit_kb must be between 16384 and 1048576")
    if draft.cf_rating is not None and not 800 <= draft.cf_rating <= 3500:
        raise TaskImportError("bad_config", "cf_rating must be between 800 and 3500")
    if draft.reference_language not in ("cpp17", "cpp20"):
        raise TaskImportError("bad_config", "reference_language must be cpp17 or cpp20")


def _first_heading(statement: str) -> str | None:
    for line in statement.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _test_numbers(files: dict[str, bytes]) -> list[str]:
    found: dict[str, set[str]] = {}
    for path in files:
        match = TEST_NAME.match(path)
        if match:
            found.setdefault(match.group(1), set()).add(match.group(2))
    for number, kinds in found.items():
        if kinds != {"in", "out"}:
            missing = ({"in", "out"} - kinds).pop()
            raise TaskImportError("unpaired_test", f"tests/{number}.{missing} is missing")
    return sorted(found, key=int)


def _test_text(files: dict[str, bytes], path: str) -> str:
    if len(files[path]) > MAX_TEST_BYTES:
        raise TaskImportError("test_too_large", f"{path} is larger than {MAX_TEST_BYTES} bytes")
    return _text(files, path)


# Polygon -------------------------------------------------------------------------------

POLYGON_LANGUAGES = ("russian", "english", "kazakh")


def parse_polygon(files: dict[str, bytes]) -> TaskDraftData:
    try:
        root = ElementTree.fromstring(files["problem.xml"])
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise TaskImportError("bad_problem_xml", f"problem.xml cannot be parsed: {exc}") from None

    testset = root.find("judging/testset[@name='tests']")
    if testset is None:
        testset = root.find("judging/testset")
    if testset is None:
        raise TaskImportError("bad_problem_xml", "problem.xml has no testset")
    try:
        time_limit = int(_child_text(testset, "time-limit", "1000"))
        memory_limit_kb = int(_child_text(testset, "memory-limit", str(256 * 1024 * 1024))) // 1024
    except ValueError:
        raise TaskImportError(
            "bad_problem_xml", "time-limit or memory-limit is not a number"
        ) from None
    input_pattern = _child_text(testset, "input-path-pattern", "tests/%02d")
    answer_pattern = _child_text(testset, "answer-path-pattern", "tests/%02d.a")
    for pattern in (input_pattern, answer_pattern):
        if not POLYGON_PATTERN.match(pattern):
            raise TaskImportError(
                "bad_problem_xml", f"unsupported test path pattern: {pattern[:50]}"
            )

    tests = []
    for index, test in enumerate(testset.findall("tests/test"), start=1):
        input_path, answer_path = input_pattern % index, answer_pattern % index
        if input_path not in files or answer_path not in files:
            raise TaskImportError(
                "polygon_tests_missing",
                f"{input_path} or {answer_path} is missing: build a full package in Polygon",
            )
        tests.append(
            ImportedTest(
                input=_test_text(files, input_path),
                expected_output=_test_text(files, answer_path),
                is_hidden=test.get("sample") != "true",
            )
        )
    if not tests:
        raise TaskImportError("no_tests", "problem.xml lists no tests")

    title = _polygon_title(root)
    legend, input_format, output_format = _polygon_statement(files)
    solution = next(
        (
            s.find("source")
            for s in root.findall("assets/solutions/solution")
            if s.get("tag") == "main" and s.find("source") is not None
        ),
        None,
    )
    reference = ""
    if solution is not None and solution.get("path") in files:
        reference = _text(files, str(solution.get("path")))

    draft = TaskDraftData(
        title=title[:200],
        statement_md=f"# {title}\n\n{legend}".strip(),
        input_format=input_format,
        output_format=output_format,
        time_limit_ms=time_limit,
        memory_limit_kb=memory_limit_kb,
        tests=tests,
        reference_solution=reference,
        source_note=f"Polygon: {root.get('short-name', '')}".strip(),
    )
    _check_limits(draft)
    return draft


def _child_text(node: "Element", tag: str, default: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else default


def _polygon_title(root: "Element") -> str:
    names = {n.get("language"): n.get("value") for n in root.findall("names/name")}
    for language in POLYGON_LANGUAGES:
        if names.get(language):
            return str(names[language])
    return root.get("short-name") or "Polygon task"


def _polygon_statement(files: dict[str, bytes]) -> tuple[str, str, str]:
    for language in POLYGON_LANGUAGES:
        base = f"statement-sections/{language}"
        if f"{base}/legend.tex" in files:
            parts = []
            for name in ("legend", "input", "output"):
                path = f"{base}/{name}.tex"
                parts.append(_text(files, path).strip() if path in files else "")
            return parts[0], parts[1], parts[2]
    raise TaskImportError(
        "polygon_statement_missing", "statement-sections/<language>/legend.tex is missing"
    )
