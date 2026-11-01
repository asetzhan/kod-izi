"""External platforms (ОТ-08): Codeforces through its public API, other sites marked by
hand with a link (Stepik, CSES, AtCoder, ACMP).

Q-18: the API is used only after the student links their own handle and consents; only
the handle leaves the system. The requests are made by the separate `connector` worker,
the only one with internet access, at most one every two seconds (Codeforces' limit). A
failed request is written on the account and never stops the system.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExternalAccount, ExternalSolve, RatingPoint

CODEFORCES_API = "https://codeforces.com/api"
HANDLE = re.compile(r"^[A-Za-z0-9_.\-]{3,24}$")
MIN_INTERVAL_S = 2.0  # Codeforces allows about one request per two seconds
TIMEOUT_S = 15.0
MAX_SUBMISSIONS = 2000
SYNC_COOLDOWN_S = 15 * 60


class ExternalError(Exception):
    pass


class CodeforcesApi(Protocol):
    def call(self, method: str, params: dict[str, str]) -> Any: ...


class RateLimiter(Protocol):
    def wait(self) -> None: ...


class RedisRateLimiter:
    """One request every MIN_INTERVAL_S across all connector workers."""

    def __init__(
        self, redis: Any, key: str = "codeforces:next", sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.redis = redis
        self.key = key
        self.sleep = sleep

    def wait(self) -> None:
        for _ in range(60):
            if self.redis.set(self.key, "1", nx=True, px=int(MIN_INTERVAL_S * 1000)):
                return
            self.sleep(0.25)
        raise ExternalError("rate limit wait timed out")


class HttpCodeforces:
    def __init__(self, limiter: RateLimiter, client: httpx.Client | None = None) -> None:
        self.limiter = limiter
        self.client = client or httpx.Client(timeout=TIMEOUT_S)

    def call(self, method: str, params: dict[str, str]) -> Any:
        self.limiter.wait()
        try:
            response = self.client.get(f"{CODEFORCES_API}/{method}", params=params)
        except httpx.HTTPError as exc:
            raise ExternalError(f"network: {type(exc).__name__}") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise ExternalError(f"codeforces answered {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise ExternalError("codeforces answered with no JSON") from None
        if data.get("status") != "OK":
            raise ExternalError(str(data.get("comment", "codeforces refused"))[:300])
        return data["result"]


def valid_handle(handle: str) -> bool:
    return bool(HANDLE.match(handle))


def _problem_url(problem: dict[str, Any]) -> str:
    contest = problem.get("contestId")
    index = problem.get("index", "")
    if contest is None:
        return "https://codeforces.com/problemset"
    kind = "gym" if int(contest) >= 100000 else "contest"
    return f"https://codeforces.com/{kind}/{contest}/problem/{index}"


def sync_codeforces(db: Session, account: ExternalAccount, api: CodeforcesApi) -> None:
    """Rating, accepted problems and rating history. Errors are kept on the account."""
    now = datetime.now(UTC)
    try:
        [info] = api.call("user.info", {"handles": account.handle})
        submissions = api.call(
            "user.status", {"handle": account.handle, "from": "1", "count": str(MAX_SUBMISSIONS)}
        )
        history = api.call("user.rating", {"handle": account.handle})
    except (ExternalError, ValueError, KeyError, TypeError) as exc:
        account.sync_status = "error"
        account.sync_error = str(exc)[:500]
        account.last_sync_at = now
        return

    account.rating = info.get("rating")
    account.max_rating = info.get("maxRating")
    known = set(
        db.scalars(
            select(ExternalSolve.problem_key).where(
                ExternalSolve.user_id == account.user_id, ExternalSolve.platform == "codeforces"
            )
        )
    )
    for item in submissions if isinstance(submissions, list) else []:
        if item.get("verdict") != "OK":
            continue
        problem = item.get("problem") or {}
        key = f"{problem.get('contestId', '')}{problem.get('index', '')}"[:100]
        if not key or key in known:
            continue
        known.add(key)
        db.add(
            ExternalSolve(
                user_id=account.user_id,
                platform="codeforces",
                problem_key=key,
                title=str(problem.get("name", ""))[:300],
                url=_problem_url(problem),
                rating=problem.get("rating"),
                tags=[str(t)[:40] for t in problem.get("tags", [])][:20],
                solved_at=datetime.fromtimestamp(int(item.get("creationTimeSeconds", 0)), UTC),
                source="api",
            )
        )
    seen = set(
        db.scalars(
            select(RatingPoint.at).where(
                RatingPoint.user_id == account.user_id, RatingPoint.platform == "codeforces"
            )
        )
    )
    for change in history if isinstance(history, list) else []:
        at = datetime.fromtimestamp(int(change.get("ratingUpdateTimeSeconds", 0)), UTC)
        if at in seen:
            continue
        seen.add(at)
        db.add(
            RatingPoint(
                user_id=account.user_id,
                platform="codeforces",
                contest=str(change.get("contestName", ""))[:300],
                rating=int(change.get("newRating", 0)),
                at=at,
            )
        )
    account.sync_status = "ok"
    account.sync_error = None
    account.last_sync_at = now


# Manual marks ------------------------------------------------------------------------------

PLATFORM_URLS = {
    "codeforces": re.compile(
        r"^https://codeforces\.com/(?:contest|gym|problemset/problem)/(?P<contest>\d+)/"
        r"(?:problem/)?(?P<index>[A-Za-z0-9]{1,4})/?$"
    ),
    "stepik": re.compile(r"^https://stepik\.org/lesson/(?P<lesson>\d+)(?:/step/(?P<step>\d+))?/?$"),
    "cses": re.compile(r"^https://cses\.fi/problemset/task/(?P<task>\d+)/?$"),
    "atcoder": re.compile(
        r"^https://atcoder\.jp/contests/(?P<contest>[a-z0-9_-]{1,40})/tasks/(?P<task>[a-z0-9_]{1,40})/?$"
    ),
    "acmp": re.compile(
        r"^https://acmp\.ru/(?:asp/do/)?index\.asp\?main=task&id_task=(?P<task>\d+)$"
    ),
}


def problem_key(platform: str, url: str) -> str | None:
    """The problem's key from its link; None when the link is not a problem of that site.
    Codeforces keys match the API's (contest id + index), so a mark and a sync agree."""
    pattern = PLATFORM_URLS.get(platform)
    match = pattern.match(url) if pattern else None
    if match is None:
        return None
    g = match.groupdict()
    if platform == "codeforces":
        return f"{g['contest']}{g['index'].upper()}"
    if platform == "stepik":
        return g["lesson"] + (f"-{g['step']}" if g.get("step") else "")
    if platform == "atcoder":
        return f"{g['contest']}-{g['task']}"
    return str(g["task"])
