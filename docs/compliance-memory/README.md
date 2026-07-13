# Compliance Memory — SANDBOX SKELETON
# BANXE AI Bank | Legion-only | TRAINING USE ONLY
# ⚠️ НЕ для production. НЕ юридическая консультация. Все пороги — PLACEHOLDER.

## Назначение

Этот пакет создаёт **обучающую память соответствия требованиям** (compliance memory)
на базе Graphiti (temporal knowledge graph) для BANXE AI Bank.

Цель — дать агентам AI-Bank контекст о регуляторных требованиях (PSD2, MiCA, FCA)
в sandbox-режиме, без реальных данных клиентов и без production-коннекторов.

## Ограничения (ОБЯЗАТЕЛЬНО ПРОЧЕСТЬ)

| Ограничение | Статус |
|-------------|--------|
| Реальные данные клиентов | ❌ ЗАПРЕЩЕНО |
| Production-коннекторы (BankAxle, Midaz live) | ❌ ЗАПРЕЩЕНО |
| Реальный парсинг регуляторных документов | ❌ НЕ РЕАЛИЗОВАН |
| Юридическая консультация | ❌ НЕ ЯВЛЯЕТСЯ |
| Официально утверждённые пороги | ⚠️ ВСЕ = PLACEHOLDER |
| Среда развёртывания | Legion ONLY → evo1 позднее (вручную оператором) |

## Состав пакета

```
docs/compliance-memory/
├── README.md                        ← этот файл
├── SANDBOX-DOCSET.md                ← описание набора документов
├── GRAPHITI-EVENT-SCHEMA.md         ← схема событий Graphiti
└── DEPLOY-LEGION-ONLY.md            ← инструкция развёртывания на Legion

infra/docker/
├── docker-compose.compliance-memory.yml
└── .env.compliance-memory.example

seed/compliance-memory/
├── PSD2-SCA-SANDBOX-v1.md          ← PSD2 / SCA sandbox-документ
├── MiCA-CASP-SANDBOX-v1.md         ← MiCA / CASP sandbox-документ
├── FCA-RECORDKEEPING-SANDBOX-v1.md ← FCA record-keeping sandbox-документ
├── BANXE-COMPLIANCE-POLICY-SANDBOX-v1.md
├── BANXE-HITL-THRESHOLDS-SANDBOX-v1.yaml
└── BANXE-RETENTION-SCHEDULE-SANDBOX-v1.yaml
```

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│           COMPLIANCE MEMORY STACK (SANDBOX)          │
│                  Legion-only                         │
├──────────────────┬──────────────────────────────────┤
│  Graphiti MCP    │  Neo4j 5.x Community              │
│  :8765 (MCP)    │  :7474 (Browser) :7687 (Bolt)     │
│  compliance-     │  Graph: banxe_compliance_sandbox   │
│  memory-api      │                                    │
├──────────────────┴──────────────────────────────────┤
│  Redis :6380 (compliance-memory namespace)           │
├──────────────────────────────────────────────────────┤
│  Seed loader: scripts/load-compliance-seed.py        │
│  Reads: seed/compliance-memory/*.md *.yaml           │
└──────────────────────────────────────────────────────┘
```

## Быстрый старт (Legion)

```bash
# 1. Скопировать .env
cp infra/docker/.env.compliance-memory.example infra/docker/.env.compliance-memory

# 2. Запустить стек
docker compose -f infra/docker/docker-compose.compliance-memory.yml --env-file infra/docker/.env.compliance-memory up -d

# 3. Дождаться готовности Neo4j (~30 сек)
docker compose -f infra/docker/docker-compose.compliance-memory.yml logs -f neo4j-compliance

# 4. Загрузить seed-документы
docker exec compliance-seed-loader python /app/load_seed.py

# 5. Проверить
curl http://localhost:8765/health
```

Полные инструкции: [DEPLOY-LEGION-ONLY.md](DEPLOY-LEGION-ONLY.md)

## Handoff на evo1

Ручное развёртывание на evo1 выполняется оператором.
Инструкция: [DEPLOY-LEGION-ONLY.md](DEPLOY-LEGION-ONLY.md) § "Handoff: evo1"

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | © BANXE 2026*
