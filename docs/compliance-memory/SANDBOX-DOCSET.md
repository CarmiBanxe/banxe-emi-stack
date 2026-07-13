# Compliance Memory — SANDBOX DOCUMENT SET
# BANXE AI Bank | TRAINING ONLY | NOT LEGAL ADVICE
# ⚠️ Все документы синтетические. Не содержат реальных данных. Пороги — PLACEHOLDER.

## Назначение набора документов

Набор предназначен для наполнения Graphiti knowledge graph обучающим контекстом
о регуляторных требованиях, применимых к BANXE как EMI (Electronic Money Institution)
под надзором FCA (UK) с криптоактивными операциями (MiCA EU).

## Состав: 6 seed-документов

### 1. PSD2-SCA-SANDBOX-v1.md
**Тема:** Strong Customer Authentication (SCA) в рамках PSD2 / RTS on SCA  
**Ключевые концепции:**
- Элементы SCA: knowledge / possession / inherence
- Динамическая привязка (dynamic linking) для платёжных операций
- Исключения: малые суммы, доверенные получатели, корпоративные платежи
- TRA (Transaction Risk Analysis) — условия применения
- Мониторинг fraud rate для TRA-исключений  

**Теги:** `psd2`, `sca`, `rts-sca`, `authentication`, `exemptions`  
**Статус:** SANDBOX — синтетический пересказ, не первоисточник

---

### 2. MiCA-CASP-SANDBOX-v1.md
**Тема:** MiCA Regulation (EU 2023/1114) — CASP authorisation & obligations  
**Ключевые концепции:**
- Классификация криптоактивов: ART / EMT / прочие
- CASP authorisation требования
- White paper disclosure обязательства
- Safeguarding клиентских криптоактивов
- Travel Rule (FATF R.16 → MiCA Art.70)
- Market Abuse (Market Manipulation, Insider Dealing)

**Теги:** `mica`, `casp`, `crypto`, `art`, `emt`, `travel-rule`, `market-abuse`  
**Статус:** SANDBOX — синтетический пересказ, не первоисточник

---

### 3. FCA-RECORDKEEPING-SANDBOX-v1.md
**Тема:** FCA Record-Keeping obligations (SYSC 9, CASS 7/15, MAR 1)  
**Ключевые концепции:**
- SYSC 9.1: обязательное ведение записей
- Минимальные сроки хранения: 5 лет (default), 7 лет (pension/product advice)
- CASS 15: safeguarding records (ежедневная сверка)
- Audit trail требования (append-only, tamper-evident)
- Уведомление FCA о существенных инцидентах (SUP 15)

**Теги:** `fca`, `sysc9`, `cass15`, `record-keeping`, `audit-trail`, `retention`  
**Статус:** SANDBOX — синтетический пересказ, не первоисточник

---

### 4. BANXE-COMPLIANCE-POLICY-SANDBOX-v1.md
**Тема:** Внутренняя политика соответствия BANXE (синтетическая)  
**Ключевые концепции:**
- Процедура AML screening (MLRO workflow)
- Пороги EDD: £10k (физ. лица) / £50k (юр. лица) — **PLACEHOLDER**
- HITL gates: SAR filing, PEP onboarding, sanction escalation
- Blocked jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE/SY (I-02)
- Escalation matrix: L1→L2→L3→L4

**Теги:** `banxe-policy`, `aml`, `edd`, `hitl`, `jurisdictions`, `escalation`  
**Статус:** SANDBOX — не утверждена MLRO / Compliance Officer

---

### 5. BANXE-HITL-THRESHOLDS-SANDBOX-v1.yaml
**Тема:** Human-in-the-loop пороги принятия решений  
**Поля:**
```yaml
threshold_id, category, trigger_condition,
autonomy_level (L1-L4), required_roles, timeout_minutes,
escalate_to, placeholder: true
```
**Статус:** **ВСЕ ЗНАЧЕНИЯ — PLACEHOLDER** (требуют утверждения MLRO/CEO)

---

### 6. BANXE-RETENTION-SCHEDULE-SANDBOX-v1.yaml
**Тема:** Расписание хранения записей  
**Поля:**
```yaml
record_class, description, retention_years,
legal_basis, review_date, placeholder: true
```
**Статус:** **PLACEHOLDER** (требует проверки юридической службой)

---

## Принципы загрузки в Graphiti

Каждый документ загружается как `document-loaded` event (см. GRAPHITI-EVENT-SCHEMA.md).

```
document → episodic memory nodes
         → entity extraction (concepts, thresholds, roles, regulations)
         → relationship edges (requires, triggers, escalates-to, references)
         → temporal validity timestamps
```

## Что НЕ входит в sandbox docset

| Исключено | Причина |
|-----------|---------|
| Реальные тексты PSD2 / MiCA / FCA Handbook | Требует лицензии / парсинга |
| Данные клиентов (транзакции, KYC) | Запрещено |
| Production API credentials | Запрещено |
| Утверждённые пороги AML | Pending MLRO sign-off |
| Реальные случаи SAR | Конфиденциально |

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | BANXE 2026*
