# Терминдер сөздігі

Код, дерекқор және API атаулары ағылшынша, интерфейс мәтіндері қазақша және орысша (i18n). Төмендегі сәйкестікті бұзба.

| Қазақша | Кодтағы атауы | Ескерту |
| --- | --- | --- |
| Курс, тақырып | Course, Topic | |
| Stepik сабағы (сыртқы дереккөз) | ExternalLesson | seed/stepik_lessons.json |
| Тапсырма, тапсырма деңгейі | Task, TaskLevel | TaskLevel: I, II, III, IV (05-task-levels.md) |
| Деңгей белгілері | LevelFeatures | knowledge_actions, algorithm_freedom, edge_cases, justification; әрқайсысы 0–2 |
| Қысқа диагностикалық тапсырма | DiagnosticTask | dissertation/diagnostic-tasks.md |
| Бақылау жұмысы, жарыс | Assessment, Contest | |
| Тапсыру | Submission | |
| Цифрлық із оқиғасы | TraceEvent | Тек қосылады, өзгертілмейді, өшірілмейді |
| Программалау әрекетінің кезеңі | ActivityStage | understand, plan, code, test, debug, explain |
| Рубрика, критерий, дескриптор | Rubric, Criterion, Descriptor | seed/rubric_default.json; деңгейлер: low, mid, high |
| Модельдің бес компоненті | ModelComponent | goal (1), criteria (2), tasks (3), analysis (4), interpretation (5) |
| Компонент жазбасы | ComponentEntry | source: auto, teacher, auto_edited; нұсқалар тарихы |
| Ақпараттық белгі | Signal | 4-компоненттің нәтижесі |
| AI бағасы, оқытушы бағасы | AiGrade, TeacherGrade | AI бағасы — алдын ала, студентке оқытушы растағаннан кейін ғана көрінеді |
| Білім жағдайы, Беспалько коэффициенті | MasteryState, BespalkoK | K = a / p, шегі 0,7 |
| Білім компоненті, студент моделі | KnowledgeComponent, StudentModel | BKT, шегі 0,95 |
| Оқу материалы, үзінді | Material, Chunk | pgvector |
| Материал байланысы, бағалау негізі | MaterialBinding, assessment_basis | |
| Кері байланыс, ұсыным | Feedback, Recommendation | |
| AI сұхбаты | AiConversation | Режим: forbidden, hints_only, open |
| Аудит журналы | AuditLog | |
