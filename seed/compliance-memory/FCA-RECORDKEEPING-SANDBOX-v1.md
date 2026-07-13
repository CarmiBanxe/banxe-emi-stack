# FCA Record-Keeping — SANDBOX TRAINING DOCUMENT v1
# BANXE AI Bank | Compliance Memory Seed
# ⚠️ SANDBOX ONLY. NOT LEGAL ADVICE. Synthetic summary for AI training.
# Source inspiration: FCA COBS 9A, SYSC 9.1, CASS 7/15, MLR 2017, PS25/12

---

## Обзор: Требования FCA к ведению документации

**Регулятор:** Financial Conduct Authority (FCA)  
**Применимо к BANXE:** Как FCA-авторизованному EMI (Electronic Money Institution)  
**Ключевые документы:** COBS, SYSC, CASS, MLR 2017, PS25/12

---

## CASS 15 — Safeguarding Records (P0 для BANXE)

| Требование | Описание | Срок хранения |
|------------|----------|--------------|
| Записи о сегрегации | Детали сегрегированных счетов и активов | 5 лет |
| Ежедневная сверка | Результаты reconciliation (CASS 7.15) | 5 лет |
| Audit trail расчётов | Записи обо всех изменениях safeguarding позиций | 5 лет |
| Отчёты о брешах | Любые нарушения CASS с планом устранения | 5 лет + 1 год |

**BANXE реализация:** `services/safeguarding/`, `services/recon/`

---

## SYSC 9.1 — General Record-Keeping

| Категория | Минимальный срок хранения | Примечания |
|-----------|--------------------------|-----------|
| Транзакционные записи | 5 лет | MIFID II: 7 лет для инвест. фирм |
| Коммуникации (email, сообщения) | 5 лет | При наличии инвестиционного бизнеса |
| Клиентские соглашения | Срок отношений + 5 лет | |
| Жалобы | 5 лет | 7 лет для MiFID II |

---

## MLR 2017 — AML Record-Keeping

| Тип записи | Срок хранения | Правовая база |
|------------|---------------|--------------|
| CDD (Customer Due Diligence) документы | 5 лет от окончания отношений | MLR 2017 reg.40 |
| Транзакционные записи (AML) | 5 лет от даты транзакции | MLR 2017 reg.40 |
| Записи о мониторинге | 5 лет | |
| SAR (Suspicious Activity Reports) | 5 лет | POCA 2002 s.330 |
| EDD документы | 5 лет | |

**BANXE реализация:** ClickHouse audit tables (I-08: TTL ≥ 5 лет)

---

## PS25/12 — Модернизация Safeguarding (2025)

> ⚠️ PS25/12 вступил в силу в 2025. Следующие требования — **PLACEHOLDER** для sandbox.

| Новое требование | Описание | Дедлайн |
|-----------------|----------|---------|
| Daily Reconciliation | Ежедневная сверка клиентских средств | [PLACEHOLDER] |
| Resolution Pack | Пакет материалов для несостоятельности | [PLACEHOLDER] |
| CASS 15 reporting | Автоматическая отчётность в FCA | [PLACEHOLDER] |
| Nominated Resolution Officer | Назначенный офицер по несостоятельности | [PLACEHOLDER] |

---

## FCA SM&CR — Accountability Records

Для Senior Management & Certification Regime:

| Запись | Описание | Хранение |
|--------|----------|---------|
| Responsibilities Maps | Индивидуальные зоны ответственности | Актуальная версия + история |
| Statements of Responsibilities | Формальные SOR для SMF holders | 6 лет |
| Conduct Rules breaches | Нарушения Conduct Rules | 6 лет |
| Fitness assessments | Ежегодная оценка пригодности | 6 лет |

---

## COBS 9A — Suitability Records (при наличии инвестиционного бизнеса)

- Запись об оценке пригодности клиента
- Рекомендации и их обоснование
- Хранение: 5 лет (розничный клиент: 8 лет)

**Применимость к BANXE:** [PLACEHOLDER — уточнить при расширении на инвестиционные продукты]

---

## Технические требования к записям (BANXE Implementation)

| Требование | Реализация |
|------------|-----------|
| Tamper-evident (защита от изменений) | Hash chain (SHA-256): `hash_prev` + `hash_self` |
| Append-only (только добавление) | ClickHouse (insert-only) + I-24 invariant |
| Поиск и восстановление | Graphiti temporal KG + ClickHouse |
| Backup | [PLACEHOLDER] |
| Access logs | pgAudit на всех PostgreSQL БД |
| Encryption at rest | [PLACEHOLDER] |

---

## Audit Trail минимальный состав

Каждая финансовая запись должна содержать:

```
- event_id      (UUID v7)
- timestamp_utc (ISO 8601, UTC)
- actor_id      (кто выполнил действие)
- subject_id    (на что направлено)
- action_type   (что было сделано)
- result        (APPROVED/REJECTED/ESCALATED)
- hash_prev     (SHA-256 предыдущей записи)
- hash_self     (SHA-256 текущей записи без hash_self)
```

---

## Ключевые политики (PLACEHOLDER)

- `FCA-RK-POLICY-001`: Матрица сроков хранения по типам данных [PLACEHOLDER]
- `FCA-RK-POLICY-002`: Процедура уничтожения данных после истечения срока [PLACEHOLDER]
- `FCA-RK-POLICY-003`: Escalation при обнаружении повреждённых записей [PLACEHOLDER]
- `FCA-RK-POLICY-004`: Business Continuity для record-keeping систем [PLACEHOLDER]

---

## Теги для Graphiti

`fca` `record-keeping` `cass15` `cobs` `sysc` `mlr2017` `ps25-12`  
`audit-trail` `retention` `smcr` `sar` `edd` `cdd` `tamper-evident`  
`append-only` `hash-chain` `sandbox`

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | BANXE 2026*
