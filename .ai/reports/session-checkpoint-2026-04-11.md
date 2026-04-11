# Session Checkpoint — 2026-04-11 ~4:00 AM
## Branch: refactor/claude-ai-scaffold

---

## Завершено в этой сессии

### Task 1 — PostgreSQL / SQLAlchemy async layer ✅

| Файл | Статус |
|------|--------|
| `services/database.py` | Создан — async engine + sessionmaker + Base + get_db() |
| `api/db/__init__.py` | Создан |
| `api/db/models.py` | Создан — Customer + AuthSession ORM models |
| `api/deps.py` | Обновлён — get_db() импортируется из services.database |
| `api/routers/auth.py` | Обновлён — async, DB lookup → InMemory fallback, AuthSession persist |
| `api/routers/customers.py` | Обновлён — async create_customer с DB write (IntegrityError handled) |
| `alembic/env.py` | Создан — async migrations, render_as_batch=True |
| `alembic/versions/fc383d99d6d3_create_customers_auth_sessions.py` | Создан — customers + auth_sessions tables |
| `tests/conftest.py` | Создан — in-memory SQLite fixture, get_db override |
| `tests/test_auth_router.py` | Обновлён — db_session fixture, 5+ тестов |

**Результат**: все pre-commit хуки прошли, pytest 1157+ тестов зелёные, git push выполнен.

### Vercel deploy (предыдущая сессия) ✅
- URL: https://web-next-ruby-iota.vercel.app
- Login page подключён к backend через Server Action
- `BANXE_API_URL` в vercel.json = `https://api.banxe.com` (placeholder до Task 2)

---

## Не завершено

### Task 2 — ngrok + Vercel ENV ❌

**Причина остановки**: ngrok требует authtoken (бесплатный аккаунт).

**Что осталось**:
1. Получить authtoken на https://dashboard.ngrok.com → Your Authtoken
2. `! /tmp/ngrok config add-authtoken <TOKEN>`
3. Запустить туннель: `! /tmp/ngrok http 8000 --log=stdout &`
4. Забрать публичный URL из `curl http://localhost:4040/api/tunnels`
5. Обновить Vercel env через API:
   ```bash
   VERCEL_TOKEN=<token>
   PROJECT_ID=<id>
   curl -X POST "https://api.vercel.com/v9/projects/$PROJECT_ID/env" \
     -H "Authorization: Bearer $VERCEL_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"key":"BANXE_API_URL","value":"https://xxxx.ngrok-free.app","type":"plain","target":["production"]}'
   ```
6. Передеплой: `cd /home/mmber/banxe-ui && npx vercel --prod --yes`

**ngrok binary**: `/tmp/ngrok` (уже скачан, v3 stable linux-amd64)

**Vercel токен**: в env `VERCEL_TOKEN` или в `/home/mmber/banxe-ui/.env.local`

### Task 3 — EAS Build ❌

**Причина**: EAS не залогинен (требует интерактивный браузер).

**Что осталось**:
1. `! eas login` — войти через браузер (expo.dev аккаунт)
2. `cd /home/mmber/banxe-ui/apps/mobile && eas build:configure`
3. `eas build --platform all --profile development`
4. Сохранить ссылки на expo.dev/builds

---

## Состояние backend

```
Backend: python3 -m uvicorn api.main:app --port 8000
PID: 593597
URL: http://localhost:8000
Health: GET /v1/health → (нет эндпоинта, но 404 подтверждает что сервер жив)
DB: SQLite dev (banxe_dev.db), PostgreSQL-ready через DATABASE_URL env
```

---

## Как продолжить в следующей сессии

```
cd /home/mmber/banxe-emi-stack
git status   # убедись что на refactor/claude-ai-scaffold

# Task 2 — нужен ngrok token от пользователя:
! /tmp/ngrok config add-authtoken <ТВОЙ_TOKEN>
# Дальше автоматически...

# Task 3 — нужен eas login:
! eas login
# Дальше автоматически...
```

**Контекст в памяти**: `/home/mmber/.claude/projects/-opt-banxe/memory/`
