"""Load test (spec 13): 100 students write an assessment at the same time.

The target: a test result reaches the student within 10 seconds. Each simulated student
logs in, opens the task, saves code snapshots, runs the public tests and submits; the
time from submission to the final verdict is reported as "submission → verdict".

    locust -f loadtest/locustfile.py --headless -u 100 -r 10 -t 3m --host http://localhost:8000
"""

import itertools
import os
import time
from datetime import UTC, datetime

from locust import HttpUser, between, events, task

PASSWORD = os.environ.get("LOAD_PASSWORD", "")
TASK_ID = int(os.environ.get("LOAD_TASK_ID", "1"))
ASSESSMENT_ID = int(os.environ.get("LOAD_ASSESSMENT_ID", "1"))
CODE = '#include <iostream>\nint main() { long long n; std::cin >> n; std::cout << "EVEN"; }\n'
numbers = itertools.count()


class Student(HttpUser):
    wait_time = between(2, 5)

    def on_start(self) -> None:
        email = f"load.student{next(numbers) % 100}@example.com"
        token = self.client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"
        session = self.client.post(
            "/api/sessions", json={"task_id": TASK_ID, "assessment_id": ASSESSMENT_ID}
        ).json()
        self.session_id = session["session_id"]
        self.seq = 0

    @task(5)
    def type_code(self) -> None:
        self.seq += 1
        event = {
            "seq": self.seq,
            "kind": "snapshot",
            "client_ts": datetime.now(UTC).isoformat(),
            "payload": {"code": CODE},
        }
        self.client.post(
            f"/api/sessions/{self.session_id}/events",
            json={"events": [event]},
            name="/api/sessions/[id]/events",
        )

    @task(2)
    def run_tests(self) -> None:
        self.client.post(
            f"/api/sessions/{self.session_id}/test",
            json={"code": CODE},
            name="/api/sessions/[id]/test",
        )

    @task(1)
    def submit(self) -> None:
        started = time.monotonic()
        response = self.client.post(
            f"/api/sessions/{self.session_id}/submit",
            json={"code": CODE, "explanation": "n % 2"},
            name="/api/sessions/[id]/submit",
        )
        if response.status_code != 201:
            return
        submission_id = response.json()["id"]
        while time.monotonic() - started < 60:
            status = self.client.get(
                f"/api/submissions/{submission_id}", name="/api/submissions/[id]"
            ).json()["status"]
            if status in ("done", "error"):
                break
            time.sleep(0.5)
        events.request.fire(
            request_type="FLOW",
            name="submission → verdict",
            response_time=(time.monotonic() - started) * 1000,
            response_length=0,
            exception=None,
            context={},
        )
