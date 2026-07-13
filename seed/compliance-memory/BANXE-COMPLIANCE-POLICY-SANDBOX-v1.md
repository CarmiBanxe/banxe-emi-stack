# BANXE Internal Compliance Policy — SANDBOX TRAINING DOCUMENT v1
# BANXE AI Bank | Compliance Memory Seed
# ⚠️ SANDBOX ONLY. SYNTHETIC INTERNAL POLICY. NOT APPROVED BY MLRO.
# All thresholds, procedures, and officer assignments are PLACEHOLDER.

---

## Политика: Внутренняя комплаенс-система BANXE AI Bank

**Статус:** [PLACEHOLDER — требует MLRO + Board sign-off]  
**Версия:** SANDBOX-v1  
**Дата создания:** 2026-07-09  
**Следующий пересмотр:** [PLACEHOLDER]  
**Ответственный:** [PLACEHOLDER — MLRO]

---

## 1. Организационная структура (PLACEHOLDER)

| Роль | Зона ответственности | Имя |
|------|---------------------|-----|
| MLRO | AML/KYC, SAR, комплаенс | [PLACEHOLDER] |
| CEO | Стратегические комплаенс-решения | [PLACEHOLDER] |
| CTIO | Технические контроли, инфраструктура | [PLACEHOLDER] |
| CFO | Safeguarding, FCA reporting, FIN060 | [PLACEHOLDER] |
| DPO | GDPR, данные клиентов | [PLACEHOLDER] |
| Compliance Officer | Ежедневный мониторинг | [PLACEHOLDER] |

---

## 2. AML/KYC политика (PLACEHOLDER)

### 2.1 Идентификация клиентов (CDD)

| Категория клиента | Уровень верификации | Документы |
|------------------|--------------------|---------—|
| Физические лица | Стандартный CDD | Паспорт/ID + proof of address |
| Юридические лица | Enhanced CDD | Устав, UBO > 25%, директора |
| PEP (Политически значимые лица) | EDD | Усиленный мониторинг + MLRO sign-off |
| Высокорисковые юрисдикции | EDD | [PLACEHOLDER список] |

### 2.2 Транзакционный мониторинг

**Пороги срабатывания алерта (PLACEHOLDER):**

```yaml
# PLACEHOLDER — не утверждены MLRO
individual_edd_threshold: "10000 GBP"  # I-04
corporate_edd_threshold: "50000 GBP"   # I-04
single_cash_report: "10000 GBP"        # PLACEHOLDER
cumulative_daily_alert: "50000 GBP"    # PLACEHOLDER
cross_border_report: "10000 EUR"       # PLACEHOLDER
```

### 2.3 Заблокированные юрисдикции (I-02)

Операции с резидентами/организациями из следующих стран **заблокированы без исключений:**

`RU` `BY` `IR` `KP` `CU` `MM` `AF` `VE` `SY`

**Реализация:** `services/aml/aml_thresholds.py` — enforced at payment flow level

---

## 3. Safeguarding Policy (CASS 15)

> Основан на FCA CASS 15 и PS25/12

### 3.1 Сегрегация средств

- Все клиентские средства хранятся на **отдельных счетах** от операционных средств BANXE
- Клиентские средства не могут использоваться для покрытия операционных расходов
- Учёт в реальном времени через Midaz ledger

### 3.2 Ежедневная сверка

- Время выполнения: [PLACEHOLDER] 00:30 UTC ежедневно
- Автоматический запуск: `services/recon/reconciliation_engine.py`
- Порог расхождения для алерта: [PLACEHOLDER] £100
- Эскалация MLRO при расхождении > [PLACEHOLDER] £1,000
- Audit trail: ClickHouse `safeguarding_events` table

### 3.3 Уведомление FCA

| Событие | Срок уведомления | Канал |
|---------|-----------------|-------|
| Расхождение > [PLACEHOLDER] | [PLACEHOLDER] | FCA RegData |
| Неспособность выполнить сегрегацию | Незамедлительно | FCA direct |
| Смена safeguarding банка | [PLACEHOLDER] рабочих дней | FCA RegData |

---

## 4. HITL Policy (I-27 — Human-in-the-Loop)

**Принцип:** AI ПРЕДЛАГАЕТ — Человек РЕШАЕТ. Никакой автономии выше L2 без явного gate.

| Тип решения | Уровень автономии | Требуемый approver |
|-------------|-------------------|--------------------|
| SAR filing | L4 (Human Only) | MLRO |
| EDD initation | L3 (Auto + HITL gate) | Compliance Officer |
| Sanctions block | L3 | MLRO |
| AML threshold change | L4 | MLRO + CEO |
| PEP onboarding | L4 | MLRO |
| FIN060 signing | L4 | CFO |
| Routine CDD | L3 | Compliance Officer |

**Таймауты HITL (PLACEHOLDER):**

```yaml
# PLACEHOLDER — требуют MLRO review
sar_filing_timeout_hours: 24
edd_gate_timeout_hours: 48
sanctions_reversal_timeout_hours: 1
aml_threshold_change_timeout_hours: 4
pep_onboarding_timeout_hours: 48
```

---

## 5. Data Retention (Минимальные требования)

| Тип данных | Минимальный срок | Правовое основание |
|------------|-----------------|-------------------|
| KYC документы | 5 лет после окончания отношений | MLR 2017 |
| Транзакционные записи | 5 лет | MLR 2017, CASS 15 |
| Записи мониторинга | 5 лет | MLR 2017 |
| Audit trail (ClickHouse) | 5 лет (TTL) | I-08, FCA |
| SAR | 5 лет | POCA 2002 |
| Жалобы | 5 лет | FCA |
| SM&CR записи | 6 лет | FCA SYSC |

---

## 6. Процедура подачи SAR

1. Агент (L3) выявляет подозрительный паттерн → **PROPOSES**
2. Compliance Officer проводит первичный review
3. Эскалация к MLRO (L4 gate — обязательно)
4. MLRO принимает решение (файл/не файл) в течение [PLACEHOLDER] часов
5. Подача в НКА (National Crime Agency) через Suspicious Activity Reports Online
6. Запись в ClickHouse audit trail (append-only, I-24)
7. Обратная связь AI-агенту (HITL feedback loop, I-27)

**КРИТИЧНО:** Информация о SAR НИКОГДА не раскрывается клиенту ("tipping off" = нарушение POCA 2002)

---

## 7. Consumer Duty (PS22/9)

| Требование | Описание | Статус |
|------------|----------|--------|
| Customer outcomes | Хорошие исходы для клиентов во всех продуктах | [PLACEHOLDER] |
| Monitoring | Ежеквартальный мониторинг outcome metrics | [PLACEHOLDER] |
| Уязвимые клиенты | Идентификация и дополнительная поддержка | [PLACEHOLDER] |
| Fair value assessment | Оценка справедливости цены/условий | [PLACEHOLDER] |

---

## Теги для Graphiti

`banxe-policy` `aml` `kyc` `cdd` `edd` `pep` `sar` `hitl` `i-27`  
`safeguarding` `cass15` `consumer-duty` `sm-cr` `mlro`  
`jurisdiction-block` `i-02` `i-04` `retention` `sandbox`

---
*SANDBOX | SYNTHETIC INTERNAL POLICY | NOT APPROVED BY MLRO | NOT LEGAL ADVICE | BANXE 2026*
