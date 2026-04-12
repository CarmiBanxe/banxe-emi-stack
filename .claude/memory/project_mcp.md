---
name: Project: MCP Server (IL-MCP-01)
description: Banxe MCP Server — 34 tools exposing all financial services to Claude agents via Model Context Protocol
type: project
---

# IL-MCP-01 — Banxe MCP Server

**Status:** DONE ✅
**Коммиты:** b858855, 91e2ed9, fbdb803, 8688e74 (core); расширен в каждом последующем IL
**Модуль:** `banxe_mcp/server.py`

## Что построено

Центральный MCP (Model Context Protocol) сервер, экспонирующий все финансовые сервисы как инструменты для Claude-агентов. Использует `fastmcp` библиотеку.

## Текущий реестр инструментов (34 tools)

### Финансовые (IL-MCP-01 core)
| Tool | Описание |
|------|---------|
| `get_account_balance` | Баланс счёта через Midaz |
| `list_accounts` | Все счета организации |
| `get_transaction_history` | История транзакций |
| `get_kyc_status` | KYC статус клиента |
| `check_aml_alert` | AML проверка транзакции |
| `get_exchange_rate` | FX курс через Frankfurter |
| `get_payment_status` | Статус платежа |
| `get_recon_status` | Статус reconciliation |
| `get_breach_history` | История нарушений CASS 15 |
| `get_discrepancy_trend` | Тренд расхождений |
| `run_reconciliation` | Запуск сверки (dry_run по умолчанию) |

### Agent Routing Layer (IL-ARL-01)
| Tool | Описание |
|------|---------|
| `route_agent_task` | Маршрутизация задачи на tier1/2/3 |
| `query_reasoning_bank` | Поиск в reasoning bank |
| `get_routing_metrics` | Метрики routing за N часов |
| `manage_playbooks` | CRUD playbooks |

### Design System (IL-ADDS-01)
| Tool | Описание |
|------|---------|
| `generate_component` | Mitosis → React/Vue/Angular |
| `sync_design_tokens` | Синхронизация токенов из Penpot |
| `visual_compare` | Сравнение компонентов |
| `list_design_components` | Каталог компонентов |

### Compliance KB (IL-CKS-01)
| Tool | Описание |
|------|---------|
| `kb_list_notebooks` | Список регуляторных ноутбуков |
| `kb_get_notebook` | Детали ноутбука |
| `kb_query` | RAG запрос к compliance KB |
| `kb_search` | Поиск по ноутбуку |
| `kb_compare_versions` | Сравнение версий регуляций |
| `kb_get_citations` | Цитаты из источников |

### Transaction Monitor (IL-RTM-01)
| Tool | Описание |
|------|---------|
| `monitor_score_transaction` | AML скоринг транзакции |
| `monitor_get_alerts` | Список AML алертов |
| `monitor_get_alert_detail` | Детали алерта |
| `monitor_get_velocity` | Velocity метрики клиента |
| `monitor_dashboard_metrics` | Dashboard метрики |

### Experiment Copilot (IL-CEC-01)
| Tool | Описание |
|------|---------|
| `experiment_design` | Дизайн compliance эксперимента |
| `experiment_list` | Список экспериментов |
| `experiment_get_metrics` | Метрики AML baseline |
| `experiment_propose_change` | Propose изменение (dry_run) |

## Архитектура
- Все tools вызывают внутренние FastAPI endpoints (не прямой доступ к БД)
- Транспорт: stdio MCP
- Аудит: каждый tool логирует в ClickHouse (I-24)
- DI: `_api_post()` / `_api_get()` хелперы + `_fx_get()` для Frankfurter

## Запуск
```bash
# В Claude Code / .mcp.json:
{"banxe": {"command": "python", "args": ["-m", "banxe_mcp.server"]}}
```

## **Why:** Агенты не должны иметь прямого доступа к БД — только через typed, audited MCP tools.
## **How to apply:** При добавлении нового сервиса — обязательно добавить MCP tools в banxe_mcp/server.py.
