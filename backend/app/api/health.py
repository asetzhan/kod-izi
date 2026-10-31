from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession, RedisClient

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: DbSession, redis: RedisClient) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except SQLAlchemyError:
        checks["db"] = "error"
    try:
        redis.ping()
        checks["redis"] = "ok"
    except RedisError:
        checks["redis"] = "error"
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "error", **checks},
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
