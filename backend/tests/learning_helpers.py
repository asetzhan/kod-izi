"""Shared stage 6b/7b setup: the workspace course with knowledge components."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import KnowledgeComponent, TaskKnowledgeComponent, Topic
from tests.workspace_helpers import SOLUTION


@pytest.fixture
def modelled(client: TestClient, ws: dict[str, Any], db: Session) -> dict[str, Any]:
    """The workspace course with a topic, two knowledge components and a second task."""
    topic = Topic(course_id=ws["course"]["id"], code="1.4", title="Шарттар", position=1)
    db.add(topic)
    db.flush()
    parity = KnowledgeComponent(topic_id=topic.id, code="cond.parity", name="Жұптылық", position=1)
    loops = KnowledgeComponent(topic_id=topic.id, code="loop.for", name="for циклі", position=2)
    db.add_all([parity, loops])
    db.flush()
    db.add(TaskKnowledgeComponent(task_id=ws["task"]["id"], knowledge_component_id=parity.id))
    extra = client.post(
        "/api/tasks",
        headers=ws["teacher"],
        json={
            "course_id": ws["course"]["id"],
            "title": "Тағы бір тапсырма",
            "statement_md": "Print EVEN or ODD.",
            "reference_solution": SOLUTION,
            "tests": [{"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False}],
        },
    ).json()
    features = {"knowledge_actions": 0, "algorithm_freedom": 0, "edge_cases": 1, "justification": 0}
    client.put(
        f"/api/tasks/{extra['id']}/level", headers=ws["teacher"], json={"features": features}
    )
    client.post(f"/api/tasks/{extra['id']}/approve", headers=ws["teacher"])
    db.add(TaskKnowledgeComponent(task_id=extra["id"], knowledge_component_id=parity.id))
    db.flush()
    return {**ws, "topic": topic, "parity": parity, "loops": loops, "extra": extra["id"]}
