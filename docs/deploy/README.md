# Пилот серверіне орнату нұсқаулығы

Сервер әлі таңдалмаған (Q-02, Q-15). Сондықтан нұсқаулық Ubuntu Server 22.04 немесе 24.04 жүйесіне жалпы түрде жазылды. Заң бойынша дерекқор Қазақстан аумағындағы серверде тұруы керек (13, 14.3-бөлімдер). Сервер мемлекеттік университетке тиесілі болса, ҚР Үкіметінің № 832 қаулысының талаптары да ескеріледі.

## 1. Серверге қойылатын талаптар

| Құрамдас | 100 студентке ең аз талап | Ескерту |
| --- | --- | --- |
| Қосымша (Nginx, backend, worker, PostgreSQL, Redis, ClamAV) | 8 vCPU, 16 ГБ RAM, 200 ГБ SSD | Дискіні шифрлау керек (14.1) |
| Judge0 | 4–8 vCPU, 8 ГБ RAM | **cgroup v1 міндетті.** Judge0 1.13.1 cgroup v2-де кодты орындамайды (Q-15) |
| Жергілікті LLM (Ollama) | GPU, 16 ГБ VRAM (llama3.1:8b үшін 8 ГБ жеткілікті) | Q-08, Q-09: тек жергілікті модель |

Ұсынылатын схема: Judge0 үшін бөлек виртуалды машина (cgroup v1), ал қалғаны үшін GPU-сы бар бір сервер.

## 2. Серверді дайындау

```
sudo apt update && sudo apt install -y docker.io docker-compose-v2 make git
sudo usermod -aG docker $USER        # содан кейін жүйеден шығып, қайта кіріңіз
```

Judge0 тұратын машинада cgroup v1-ді қосу керек:

```
sudo sed -i 's/GRUB_CMDLINE_LINUX="/GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0 /' /etc/default/grub
sudo update-grub && sudo reboot
stat -fc %T /sys/fs/cgroup            # tmpfs шығуы керек (cgroup2fs емес)
```

Ескерту: systemd 256 және одан жаңа нұсқаларда cgroup v1-ге қосымша `SYSTEMD_CGROUP_ENABLE_LEGACY_FORCE=1` параметрі керек. Сондықтан Judge0 үшін Ubuntu 22.04 ұсынылады.

## 3. Орнату

```
git clone https://github.com/asetzhan/kod-izi.git && cd kod-izi
sh infra/scripts/init-env.sh          # .env жасалады, құпиялар кездейсоқ толтырылады
```

`.env` файлында мына мәндерді міндетті түрде тексеріңіз:

| Айнымалы | Пилотта |
| --- | --- |
| `APP_ENV` | `prod` |
| `COOKIE_SECURE` | `true` |
| `REQUIRE_2FA_FOR_STAFF`, `REQUIRE_CONSENT` | `true` |
| `LLM_PROVIDER` | `ollama` |
| `BACKUP_PASSPHRASE` | Ұзын құпия сөз. Оны серверден тыс та сақтаңыз (сейфте, құпия менеджерінде) |
| `RETENTION_DAYS` | Тапсырыс беруші бекіткен мерзім (Q-12 шешілгенде) |

Кілттерді құпиялар қоймасында (мысалы, HashiCorp Vault) сақтап, мезгіл-мезгіл ауыстыру ұсынылады (14.1). `.env` файлын ешқашан git-ке қоспаңыз.

```
make dev                              # сервистерді іске қосады
make llm                              # Ollama мен модельдерді жүктейді (GPU серверде)
make create-admin EMAIL=admin@university.kz
make seed                             # курстар каталогы мен эксперимент тапсырмаларының жобасы
```

Әкімші бірінші кіргенде жүйе екі факторлы аутентификацияны (TOTP) баптауды талап етеді. Ол үшін телефонға Google Authenticator, Microsoft Authenticator немесе Aegis қолданбасы керек.

### HTTPS

`infra/nginx/tls.conf.example` үлгісін сервердің Nginx конфигурациясына көшіріңіз:
- домен атауын ауыстырыңыз;
- сертификаттарды `/etc/nginx/certs/` папкасына орналастырыңыз (университеттің IT бөлімі береді немесе Let's Encrypt);
- frontend-ті `npm run build` арқылы жинап, `dist/` мазмұнын `/usr/share/nginx/html` папкасына қойыңыз.

Үлгіде мыналар бар: тек HTTPS (TLS 1.2+), HSTS, inline скриптсіз CSP, сұрау жиілігін шектеу.

### Дерекқор рөлі

Миграция `kodizi_app` рөлін жасайды (NOLOGIN). Қосымша осы рөлге ауысады, сондықтан жол деңгейіндегі қауіпсіздік (RLS) жұмыс істейді. Production-да қосымша суперқолданушы атымен емес, бөлек логинмен қосылуы керек:

```
CREATE ROLE kodizi_web LOGIN PASSWORD '...' IN ROLE kodizi_app;
```

Содан кейін `DATABASE_URL` мәнін осы логинмен жазыңыз. Миграцияларды кесте иесі рөлімен іске қосыңыз.

## 4. Резервтік көшірме және қалпына келтіру

```
docker compose -f infra/docker-compose.yml --env-file .env --profile backup up -d backup   # күн сайын
make backup                                                                                  # дереу
```

Көшірмелер `backups` томына жазылады, AES-256 арқылы шифрланады және 30 күн сақталады. Оларды серверден тыс жерге де көшіріңіз (шифрланған күйінде).

Қалпына келтіру:

```
docker compose -f infra/docker-compose.yml --env-file .env --profile backup run --rm \
  -e PGDATABASE=kodizi_restore backup restore.sh /backups/kodizi-db-<уақыт>.dump.enc /backups/kodizi-files-<уақыт>.tar.enc
```

Қалпына келтіру **тоқсан сайын** бөлек дерекқорға сыналады (14.1). Сынақтың автоматтандырылған нұсқасы: `backend/tests/test_backup_restore.py`. Ол көшірме жасап, оны қалпына келтіреді де, кестелерді, RLS-ті, рұқсаттар мен файлдарды салыстырады.

## 5. Дербес деректер

- Студент бірінші кіргенде дербес деректерді өңдеуге келісім береді. Келісім беті бағалау мен кері байланыстың AI көмегімен жасалатынын хабарлайды (14.3).
- Келісімді кері қайтарған немесе `RETENTION_DAYS` күннен бері белсенді болмаған студенттердің деректері анонимделеді. Бұл үшін `make retention` командасын cron арқылы аптасына бір рет іске қосыңыз.
- Әкімші жеке пайдаланушыны анонимдей алады: `POST /api/admin/users/{id}/anonymize`.
- Цифрлық із бен баға жойылмайды, өйткені олар тек толығатын кестелер. Бірақ олар аты-жөнсіз id-ге ғана байланып қалады.
- Зерттеу экспорты студенттерді псевдонимдермен көрсетеді: `GET /api/assessments/{id}/export.csv`.

## 6. Жүктеме тесті

Пилот алдында толық стекпен (нақты Judge0, RQ worker, Redis, Ollama) қайталаңыз:

```
cd backend
LOAD_PASSWORD=... python -m loadtest.prepare
LOAD_PASSWORD=... LOAD_TASK_ID=<id> LOAD_ASSESSMENT_ID=<id> \
  locust -f loadtest/locustfile.py --headless -u 100 -r 10 -t 5m --host https://example.edu.kz
```

Мақсат: «submission → verdict» 10 секундтан аспауы керек (13-бөлім). Әзірлеу машинасындағы нәтиже: `docs/reports/load-test-2026-10-31.md`. Тест аяқталған соң жүктеме аккаунттарын анонимдеңіз немесе өшіріңіз.

## 7. Пилот алдындағы тексерулер

- `docs/security/pentest-checklist.md` — тәуелсіз ену тестіне арналған бақылау тізімі.
- `docs/acceptance.md` — 16-бөлімдегі тексерулер және оларды жабатын тесттер.
- Judge0 интеграциялық тесті (`backend/tests/test_judge0_integration.py`) пен prompt injection жиынтығын нақты модельмен іске қосу (`OLLAMA_TEST_URL=... pytest -k injection`).
