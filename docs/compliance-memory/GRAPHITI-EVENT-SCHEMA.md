# Graphiti Event Schema — COMPLIANCE MEMORY
# BANXE AI Bank | SANDBOX | TRAINING ONLY
# Append-only. No UPDATE. No DELETE. Ever.

## Назначение

Эта схема определяет формат **compliance event** для append-only audit trail
в Graphiti temporal knowledge graph.

Каждое событие — неизменяемый узел в графе. Hash-chain обеспечивает
tamper-evident последовательность (I-24).

---

## Полная схема события

```json
{
  "event_id":          "uuid-v7 | string",
  "event_type":        "string | enum — см. EventType ниже",
  "subject_type":      "string | enum — Customer | Transaction | Document | Agent | Policy",
  "subject_id":        "string — идентификатор субъекта (anonymised в sandbox)",
  "actor_type":        "string | enum — AI_AGENT | HUMAN | SYSTEM | EXTERNAL",
  "actor_id":          "string — agent_id или user_id исполнителя действия",
  "timestamp_utc":     "ISO 8601 UTC — 2026-07-13T10:00:00.000Z",
  "decision":          "string | enum — APPROVED | REJECTED | ESCALATED | PENDING | DEFERRED",
  "reason_code":       "string — машиночитаемый код причины, напр. AML_THRESHOLD_BREACH",
  "reason_text":       "string — человекочитаемое объяснение (max 500 chars)",
  "policy_refs":       ["string"] — список policy_id / rule_id, напр. ['I-02', 'PSD2-RTS-Art11'],
  "evidence_refs":     ["string"] — ссылки на документы/транзакции/скриншоты,
  "risk_level":        "LOW | MEDIUM | HIGH | CRITICAL",
  "requires_human":    "boolean — true если HITL gate",
  "human_reviewer_id": "string | null — заполняется после ревью HITL",
  "retention_class":   "string | enum — STANDARD_5Y | EXTENDED_7Y | PERMANENT | SANDBOX",
  "hash_prev":         "string — SHA-256 hash предыдущего события в цепочке (append-only chain)",
  "hash_self":         "string — SHA-256(event без hash_self поля) — самоверифицируемый",
  "tags":              ["string"] — свободные теги, напр. ['aml', 'hitl', 'sar-candidate']
}
```

---

## Перечень типов событий (EventType enum)

| event_type | Описание |
|------------|----------|
| `document-loaded` | Загрузка seed/compliance документа в память |
| `policy-evaluated` | AI агент оценил политику и вынес решение |
| `hitl-escalation` | Решение передано на проверку человеку (HITL gate) |
| `hitl-resolution` | Человек принял решение по HITL запросу |
| `aml-screening` | AML проверка клиента или транзакции |
| `sanctions-check` | Проверка по санкционным спискам |
| `edd-triggered` | Запущена Enhanced Due Diligence |
| `sar-candidate` | Транзакция/клиент помечены как кандидат на SAR |
| `sar-filed` | SAR подан (только MLRO, L4) |
| `jurisdiction-block` | Платёж заблокирован (I-02: blocked jurisdiction) |
| `threshold-breach` | Превышен порог (AML, EDD, risk) |
| `session-start` | Начало AI-сессии агента |
| `session-end` | Завершение AI-сессии агента |
| `memory-query` | Агент выполнил запрос к compliance memory |
| `retention-review` | Плановая проверка сроков хранения |
| `policy-update` | Обновление политики в memory (только оператор) |

---

## Пример 1: HITL escalation event

```json
{
  "event_id":          "01928f4e-3a7b-7c2d-9e1f-000000000001",
  "event_type":        "hitl-escalation",
  "subject_type":      "Transaction",
  "subject_id":        "SANDBOX-TX-0042",
  "actor_type":        "AI_AGENT",
  "actor_id":          "aml-check-agent-v1",
  "timestamp_utc":     "2026-07-13T10:30:00.000Z",
  "decision":          "ESCALATED",
  "reason_code":       "AML_THRESHOLD_BREACH",
  "reason_text":       "Transaction amount exceeds EDD threshold [PLACEHOLDER]. Routing to MLRO for manual review per I-04.",
  "policy_refs":       ["I-02", "I-04", "MLR-2017-r28", "BANXE-AML-POLICY-S3"],
  "evidence_refs":     ["SANDBOX-TX-0042-raw", "SANDBOX-CUSTOMER-0017-kyc"],
  "risk_level":        "HIGH",
  "requires_human":    true,
  "human_reviewer_id": null,
  "retention_class":   "EXTENDED_7Y",
  "hash_prev":         "a3f8d2c1e4b90712f6a5c3d8e1b4f2a9c7e0d3b8f5a2c1e4d7b0f3a6c9e2d5",
  "hash_self":         "b7c4e1f8a2d5b0e3c6f9a2d5b8e1c4f7a0d3b6e9c2f5a8d1b4e7c0f3a6d9e2",
  "tags":              ["aml", "edd", "hitl", "mlro-required", "sandbox"]
}
```

---

## Пример 2: document-loaded event

```json
{
  "event_id":          "01928f4e-3a7b-7c2d-9e1f-000000000002",
  "event_type":        "document-loaded",
  "subject_type":      "Document",
  "subject_id":        "PSD2-SCA-SANDBOX-v1",
  "actor_type":        "SYSTEM",
  "actor_id":          "seed-loader-v1",
  "timestamp_utc":     "2026-07-13T09:00:00.000Z",
  "decision":          "APPROVED",
  "reason_code":       "SEED_LOAD_OK",
  "reason_text":       "Sandbox compliance document loaded into Graphiti memory. Source: seed/compliance-memory/PSD2-SCA-SANDBOX-v1.md",
  "policy_refs":       [],
  "evidence_refs":     ["seed/compliance-memory/PSD2-SCA-SANDBOX-v1.md"],
  "risk_level":        "LOW",
  "requires_human":    false,
  "human_reviewer_id": null,
  "retention_class":   "SANDBOX",
  "hash_prev":         "0000000000000000000000000000000000000000000000000000000000000000",
  "hash_self":         "a3f8d2c1e4b90712f6a5c3d8e1b4f2a9c7e0d3b8f5a2c1e4d7b0f3a6c9e2d5",
  "tags":              ["seed", "psd2", "sca", "document", "sandbox"]
}
```

---

## Append-only invariant (I-24)

```
ПРАВИЛО: Ни одно событие в compliance memory НЕ может быть изменено или удалено.

Реализация:
  - Neo4j: событие создаётся как READ-ONLY node после записи (ACL на уровне DB)
  - hash_prev образует linked list — разрыв цепочки = tamper signal
  - hash_self позволяет верифицировать целостность отдельного события
  - Graphiti episode nodes: only CREATE allowed, no MERGE/DELETE

Нарушение I-24 = P0 compliance incident.
```

---

## Retention classes

| retention_class | Срок хранения | Основание |
|-----------------|--------------|-----------|
| `SANDBOX` | До очистки sandbox среды | Нет регуляторного требования |
| `STANDARD_5Y` | 5 лет | FCA SYSC 9.1, CASS 15 |
| `EXTENDED_7Y` | 7 лет | MLR 2017, pension advice |
| `PERMANENT` | Постоянно | SAR records, board minutes |

---

## Примеры запросов к Graphiti memory

```python
# Запрос: найти все события HITL escalation за последние 30 дней
results = await graphiti.search(
    query="HITL escalation AML threshold breach",
    center_node_uuid=None,
    num_results=10,
    search_filters={"event_type": "hitl-escalation"}
)

# Запрос: получить политики, применимые к транзакции с blocked jurisdiction
results = await graphiti.search(
    query="blocked jurisdiction payment RU BY IR",
    num_results=5
)

# Запрос: найти retention schedule для AML records
results = await graphiti.search(
    query="retention schedule AML SAR records years",
    num_results=3
)
```

---

## Примечания о среде

```
⚠️  LEGION ONLY: Этот schema файл — часть sandbox skeleton.
    Graphiti knowledge graph настроен ТОЛЬКО для Legion (localhost).

⚠️  EVO1: Ручное развёртывание оператором. Отдельные credentials.
    Neo4j URI, Graphiti API key и OpenAI/LLM endpoint должны быть
    сконфигурированы заново перед развёртыванием на evo1.

⚠️  PRODUCTION: Требует дополнительного security review:
    - Шифрование Neo4j bolt connection (TLS)
    - Отдельные credentials для каждой среды
    - Audit log экспорт в ClickHouse (I-24)
    - MLRO review всех HITL threshold значений
```

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | BANXE 2026*
