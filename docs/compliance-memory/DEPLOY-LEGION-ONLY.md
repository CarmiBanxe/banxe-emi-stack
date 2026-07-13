# Deploy Guide — Compliance Memory (SANDBOX)
# LEGION ONLY | Evo1: manual operator action later
# ⚠️ SANDBOX ONLY. НЕ развёртывать в production без MLRO/CTIO sign-off.

## Требования (Legion)

| Компонент | Версия | Примечание |
|-----------|--------|-----------|
| Docker Engine | ≥ 26.x | Проверить: `docker --version` |
| Docker Compose | ≥ 2.24 | Проверить: `docker compose version` |
| RAM | ≥ 8 GB | Neo4j + Graphiti требуют ~4 GB |
| Disk | ≥ 20 GB | Для Neo4j данных |
| Порты свободны | 7474, 7687, 6380, 8765 | Проверить: `ss -tlnp` |
| LLM endpoint | Local / OpenAI-compatible | Для Graphiti entity extraction |

---

## Шаг 1: Подготовка конфигурации

```bash
# Скопировать .env шаблон
cp infra/docker/.env.compliance-memory.example \
   infra/docker/.env.compliance-memory

# Заполнить обязательные значения:
# - GRAPHITI_LLM_API_KEY (OpenAI key или local LLM endpoint)
# - NEO4J_AUTH (изменить пароль neo4j/CHANGEME)
nano infra/docker/.env.compliance-memory
```

---

## Шаг 2: Запуск стека

```bash
cd /path/to/banxe-emi-stack

docker compose \
  -f infra/docker/docker-compose.compliance-memory.yml \
  --env-file infra/docker/.env.compliance-memory \
  up -d

# Проверить статус
docker compose \
  -f infra/docker/docker-compose.compliance-memory.yml \
  ps
```

---

## Шаг 3: Ожидание готовности Neo4j

Neo4j требует ~30–60 сек для инициализации.

```bash
# Стримить логи до появления "Started."
docker logs -f neo4j-compliance 2>&1 | grep -m1 "Started\."

# Проверить браузер (опционально):
# http://localhost:7474  (login: neo4j / <NEO4J_PASSWORD из .env>)
```

---

## Шаг 4: Загрузка seed-документов

```bash
# Запустить seed loader (запускается автоматически при start,
# но можно повторить вручную)
docker exec compliance-seed-loader python /app/load_seed.py

# Ожидаемый вывод:
# [INFO] Loading: PSD2-SCA-SANDBOX-v1.md ... OK
# [INFO] Loading: MiCA-CASP-SANDBOX-v1.md ... OK
# [INFO] Loading: FCA-RECORDKEEPING-SANDBOX-v1.md ... OK
# [INFO] Loading: BANXE-COMPLIANCE-POLICY-SANDBOX-v1.md ... OK
# [INFO] Loading: BANXE-HITL-THRESHOLDS-SANDBOX-v1.yaml ... OK
# [INFO] Loading: BANXE-RETENTION-SCHEDULE-SANDBOX-v1.yaml ... OK
# [INFO] Seed complete: 6 documents, N entities, M edges
```

---

## Шаг 5: Проверка работоспособности

```bash
# Health check
curl -s http://localhost:8765/health | jq .

# Ожидаемый ответ:
# {"status": "ok", "neo4j": "connected", "documents_loaded": 6}

# Тестовый запрос к memory
curl -s -X POST http://localhost:8765/search \
  -H "Content-Type: application/json" \
  -d '{"query": "EDD threshold PSD2 SCA exemption", "num_results": 3}' \
  | jq .
```

---

## Управление стеком

```bash
# Остановить (данные Neo4j сохранены в volume)
docker compose -f infra/docker/docker-compose.compliance-memory.yml down

# Остановить и удалить данные (ПОЛНАЯ ОЧИСТКА)
docker compose -f infra/docker/docker-compose.compliance-memory.yml down -v

# Посмотреть логи
docker compose -f infra/docker/docker-compose.compliance-memory.yml logs -f

# Перезагрузить seed после изменений
docker exec compliance-seed-loader python /app/load_seed.py --force-reload
```

---

## Порты (Legion)

| Сервис | Порт | Протокол | Описание |
|--------|------|----------|----------|
| Neo4j Browser | 7474 | HTTP | Веб-интерфейс Neo4j |
| Neo4j Bolt | 7687 | Bolt | Соединение Graphiti → Neo4j |
| Redis (compliance) | 6380 | TCP | Кэш (изолирован от основного Redis :6379) |
| Graphiti API | 8765 | HTTP | MCP + REST endpoint для агентов |

---

## Handoff: evo1

> ⚠️ ОПЕРАТОР выполняет развёртывание на evo1 вручную.  
> Central/Factory не имеет доступа к evo1.

### Контрольный список для оператора (evo1)

```
[ ] 1. Скопировать infra/docker/docker-compose.compliance-memory.yml на evo1
[ ] 2. Создать .env.compliance-memory с evo1-специфичными credentials:
       - NEO4J_AUTH = neo4j/<новый_надёжный_пароль>
       - GRAPHITI_LLM_API_KEY = <evo1_api_key>
       - GRAPHITI_LLM_BASE_URL = <evo1_LLM_endpoint>
[ ] 3. Проверить, что порты 7474/7687/6380/8765 не заняты на evo1
[ ] 4. Запустить docker compose up -d
[ ] 5. Запустить seed loader
[ ] 6. Проверить health endpoint
[ ] 7. Настроить доступ агентов через GRAPHITI_API_URL=http://<evo1_ip>:8765
[ ] 8. Уведомить команду о готовности evo1 compliance memory
```

### Что НЕ переносить на evo1 без отдельного review

```
[ ] Реальные данные клиентов (ЗАПРЕЩЕНО)
[ ] Production API ключи (отдельные credentials)
[ ] Неутверждённые HITL пороги (PLACEHOLDER → требуют MLRO sign-off)
```

---

## Устранение неполадок

| Симптом | Диагностика | Решение |
|---------|-------------|---------|
| Neo4j не запускается | `docker logs neo4j-compliance` | Проверить RAM / disk space |
| Порт 7687 занят | `ss -tlnp \| grep 7687` | Остановить конкурирующий процесс |
| Seed loader падает | `docker logs compliance-seed-loader` | Проверить LLM endpoint в .env |
| `connection refused :8765` | `docker ps \| grep graphiti` | Контейнер не запустился — см. логи |
| Graphiti → Neo4j timeout | `docker logs compliance-graphiti` | Подождать Neo4j, затем `docker restart compliance-graphiti` |

---
*SANDBOX | LEGION ONLY | EVO1: MANUAL OPERATOR ACTION | BANXE 2026*
