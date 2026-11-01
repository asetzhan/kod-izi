from fastapi import FastAPI

from app.api import (
    admin,
    analysis,
    app_settings,
    assessments,
    auth,
    contests,
    courses,
    health,
    insights,
    learning,
    olympiad,
    panel,
    privacy,
    review,
    tasks,
    users,
    workspace,
)
from app.core.config import get_settings


def create_app() -> FastAPI:
    expose_docs = get_settings().app_env != "prod"
    app = FastAPI(
        title="Kod Izi API",
        docs_url="/api/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if expose_docs else None,
    )
    for module in (
        health,
        auth,
        users,
        admin,
        courses,
        tasks,
        assessments,
        app_settings,
        workspace,
        analysis,
        panel,
        privacy,
        contests,
        olympiad,
        insights,
        learning,
        review,
    ):
        app.include_router(module.router)
    return app


app = create_app()
