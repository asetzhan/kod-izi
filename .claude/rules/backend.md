---
paths:
  - "backend/**"
---

# Backend ережелері

- Құрылым: `app/api` — тек HTTP (роутер, схема); `app/services` — бизнес-логика; `app/models` — SQLAlchemy модельдері; `app/llm` — LLM шлюзі; `app/judge` — Judge0 клиенті.
- Нысанға рұқсат тексерісі тек `app/services/access.py` арқылы жасалады. id қабылдайтын жаңа endpoint алдымен рұқсатты, содан кейін нысанның бар-жоғын тексереді.
- Аудитке жазу үшін `app.services.audit.record` қолданылады. Жазба шақырушының `commit`-імен бірге сақталады.
- Модель өзгерсе: `alembic revision --autogenerate`, содан кейін миграцияны қолмен қарап шығу. `test_sec15_models_match_migrations` тесті модель мен миграцияның айырмашылығын табады.
- Тек толығатын кестеге (`audit_log`, кейін `trace_events`) `forbid_modification()` триггері қойылады.
- Тесттерге `tests/conftest.py` фикстуралары қолданылады: `client`, `db`, `make_user`, `school`, `login()`. Әр тест транзакция ішінде жүреді және соңында кері қайтарылады.
- Типтер: `mypy --strict`. Стиль: `ruff format`, `ruff check`.
