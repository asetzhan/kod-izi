# 16-бөлімдегі тексерулер және оларды жабатын тесттер

| 16-бөлімдегі тексеру | Автоматты тексеру | Қолмен не қалды |
| --- | --- | --- |
| Тестілеу жүйесі: эталон шешімдер OK, қате шешімдер күтілген вердиктті алады | `test_workspace.py::test_ft31_*` (fake Judge), `test_judge0_integration.py` (нақты Judge0) | Judge0 интеграциялық тестін серверде іске қосу (Q-15) |
| Функционалдық талаптар | `test_ft*` тесттері; әр ФТ ID-іне кемінде бір тест | Жазбаша сценарий бойынша қолмен тексеру |
| Автотесттер, CI жасыл | GitHub Actions: backend, frontend, secrets, compose | — |
| Цифрлық іздің толықтығы, қайта ойнату | `test_ft25_trace_rebuilds_the_whole_work_process` | Қайта ойнату интерфейсі 6b-кезеңде |
| Модель компоненттері: автоматты толтыру, оқытушы мәнінің сақталуы, нұсқалар | `test_panel.py::test_ft07_*` | — |
| AI бағасының сапасы (Pearson, Spearman, MAE, MD; база MAE 7,34, r 0,647) | `test_privacy.py::test_ft49_*`, `GET /api/assessments/{id}/agreement` | Пилот деректерімен есептеу |
| Кітап негізінде бағалау: сілтемелердің 90%-ы дұрыс бетке апарады | `test_ft35_every_book_evidence_has_book_chapter_and_page` (сілтеме құрылымы мен үзіндіге байланысы) | Іріктелген жұмыстарда оқытушы тексереді |
| Жүктеме: 100 студент, тест нәтижесі ≤ 10 с | `backend/loadtest/`, есеп: `docs/reports/load-test-2026-10-31.md` | Серверде толық стекпен қайталау |
| Қауіпсіздік: оқшаулау, басқалардың деректері, prompt injection | `test_sec14_*` (IDOR, RLS, жасырын тесттер, injection жиынтығы, append-only), `test_backup_restore.py` | Тәуелсіз ену тесті (`docs/security/pentest-checklist.md`), injection жиынтығын нақты модельмен іске қосу |
| Пайдаланушылар бағасы (SUS) | — | Пилоттан кейінгі сауалнама |

## 6a-кезең: олимпиада бөлімі

| Қабылдау критерийі (`docs/prompts/stage-6a-olympiad.md`) | Автоматты тексеру | Қолмен не қалды |
| --- | --- | --- |
| ICPC мен IOI нәтижелер кестесінің есептелуі | `test_olympiad.py::test_ot02_icpc_penalty_ties_and_compile_errors`, `test_ot02_ioi_points_for_subtasks_and_best_submission`, `test_ot02_icpc_standings_with_freeze_and_hidden_names`, `test_ot02_ioi_contest_scores_subtasks` | Жаттықтырушымен бір виртуалды контест өткізу |
| Жарыс кезінде AI-көмекшіге сұрау жіберу мүмкін емес | `test_ot02_assistant_and_hints_are_off_during_the_contest`, `test_ot03_virtual_contest_after_the_end` (виртуалды раунд кезінде де) | — |
| Бір сағат ережесі уақыт бойынша тексерілген | `test_ot05_editorial_opens_after_one_hour` (59 минутта жабық, 61 минутта ашық), `test_ot05_hints_open_step_by_step` | — |
| Стресс-тест айырмашылық табылған кірісті көрсетеді | `test_ot06_stress_test_shows_the_differing_input` | Нақты Judge0-мен тексеру (Q-15) |
| Есептер банкі, жад шектеуі 16–1024 МБ (ОТ-01) | `test_ot01_bank_fields_and_memory_limits`, `test_ot01_seeded_olympiad_bank_is_a_draft`, `test_ot01_part2_opens_when_topics_are_mastered` | Жаттықтырушы банктің жобасын (Q-13) тексеріп бекітеді |
| Деңгейге сай ұсыныс (ОТ-04), анықтамалық (ОТ-10) | `test_ot04_recommendations_are_slightly_above_the_rating`, `test_ot10_reference_lists_lessons_and_materials` | — |

## 7-кезең

| Қабылдау критерийі (`docs/prompts/stage-7-advanced.md`) | Автоматты тексеру | Қолмен не қалды |
| --- | --- | --- |
| Code-DKT: оқыту мен бағалау, BKT-мен салыстыру, модель болмаса немесе нашар болса BKT-ға қайту (ФТ-40) | `test_code_dkt.py::test_ft40_code_dkt_trains_and_beats_bkt_on_test_data`, `test_ft40_falls_back_to_bkt_without_a_good_real_model`, `test_ft40_progress_uses_bkt_when_no_model_and_says_so`; есеп: `docs/reports/code-dkt-vs-bkt.md` | Пилот деректерімен оқыту: `make train-dkt COURSE=N` |
| Жарыстан кейінгі талдау, қайта шешу тізімі, қос бағалау (ОТ-07) | `test_review.py::test_ot07_*` | — |
| Codeforces API лимитке сай, қате кезінде жүйе тоқтамайды (ОТ-08) | `test_ot08_requests_keep_to_the_codeforces_limit`, `test_ot08_api_errors_do_not_stop_the_system`, `test_ot08_a_handle_is_verified_for_one_student_only` | Нақты Codeforces-пен connector арқылы тексеру (сервер дайын болғанда) |
| Білім картасы (ОТ-09) | `test_ot09_knowledge_map_by_topic_and_rating_over_time` | — |
| Авторлық куәлікке арналған техникалық сипаттама | `docs/authorship/technical-description.md` | Өтініш берушінің деректерін толтыру |
