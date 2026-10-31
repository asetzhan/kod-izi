"""Tunable settings. Stage 1: the task level rule (ФТ-19, spec 5.2, Q-06)."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.api.content_schemas import LevelRuleIn
from app.api.deps import AdminUser, AppSettings, CurrentUser, DbSession, client_ip
from app.services import audit
from app.services.access import is_staff
from app.services.audit import AuditAction
from app.services.levels import RULE_KEY, RuleError, get_rule, set_rule

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _rule_view(rule_json: dict[str, Any], settings: AppSettings) -> dict[str, Any]:
    seed = json.loads((settings.seed_dir / "task_levels.json").read_text(encoding="utf-8"))
    return {**rule_json, "features": seed["features"], "levels": seed["levels"]}


@router.get("/task-level-rule")
def read_level_rule(user: CurrentUser, db: DbSession, settings: AppSettings) -> dict[str, Any]:
    if not is_staff(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _rule_view(get_rule(db).to_json(), settings)


@router.put("/task-level-rule")
def update_level_rule(
    body: LevelRuleIn, request: Request, admin: AdminUser, db: DbSession, settings: AppSettings
) -> dict[str, Any]:
    before = get_rule(db).to_json()
    try:
        rule = set_rule(db, body.model_dump(mode="json"), admin.id)
    except RuleError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "bad_rule", "message": str(exc)}
        ) from None
    audit.record(
        db,
        AuditAction.SETTING_CHANGED,
        actor_id=admin.id,
        object_type="setting",
        object_id=RULE_KEY,
        ip=client_ip(request),
        details={"before": before, "after": rule.to_json()},
    )
    db.commit()
    return _rule_view(rule.to_json(), settings)
