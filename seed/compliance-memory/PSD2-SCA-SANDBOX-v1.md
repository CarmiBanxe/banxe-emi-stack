# PSD2 / SCA — SANDBOX TRAINING DOCUMENT v1
# BANXE AI Bank | Compliance Memory Seed
# ⚠️ SANDBOX ONLY. NOT LEGAL ADVICE. Synthetic summary for AI training.
# Source inspiration: PSD2 Directive 2015/2366/EU, EBA RTS on SCA (EU 2018/389)

---

## Обзор: Strong Customer Authentication (SCA)

**Регулятор:** European Banking Authority (EBA) / FCA (UK post-Brexit: PSR 2017)  
**Применимо к:** Платёжным сервисам BANXE — онлайн-платежи, доступ к счёту  
**Цель SCA:** Подтвердить личность плательщика через ≥2 независимых фактора

---

## Элементы SCA

| Категория | Описание | Примеры |
|-----------|----------|---------|
| Knowledge (знание) | Что-то, что знает только пользователь | PIN, пароль, кодовое слово |
| Possession (владение) | Что-то, чем владеет пользователь | Телефон (OTP), hardware token |
| Inherence (неотъемлемость) | Биометрия пользователя | Отпечаток пальца, Face ID, голос |

**Правило:** Для SCA требуются ≥2 независимых фактора из разных категорий.

---

## Динамическая привязка (Dynamic Linking)

Для платёжных транзакций SCA должна включать **dynamic linking**:
- Код аутентификации связан с конкретной суммой и получателем
- Если сумма или получатель изменятся → требуется новая SCA
- Пользователь видит сумму и получателя до аутентификации

**Реализация в BANXE:** Keycloak + TOTP/WebAuthn с передачей transaction context.

---

## Исключения из SCA

> ⚠️ Все суммовые пороги ниже — **PLACEHOLDER**. Официальные значения из RTS.

| Исключение | Условие | Порог | Статус |
|------------|---------|-------|--------|
| Contactless POS | Малая сумма | [PLACEHOLDER] €50 per tx, €150 cumulative | PLACEHOLDER |
| Удалённые эл. платежи | Малая сумма | [PLACEHOLDER] €30 per tx, €100 cumulative или 5 tx | PLACEHOLDER |
| Доверенные получатели | В white-list плательщика | Любая сумма | Whitelist требует SCA при добавлении |
| TRA (Transaction Risk Analysis) | Низкий риск по fraud model | [PLACEHOLDER] €100/€250/€500 в зависимости от fraud rate | PLACEHOLDER |
| Корпоративные платежи | B2B через dedicated payment process | Нет порога | Требует EBA признания |
| Повторяющиеся платежи | Одинаковая сумма, получатель | Без ограничений | Первый платёж требует SCA |

---

## TRA (Transaction Risk Analysis) — условия применения

Для применения TRA-исключения BANXE должен поддерживать:
1. Fraud rate ниже допустимого порога (reference fraud rates из RTS)
2. Реальный анализ риска транзакции (не статический)
3. Ведение записей об исключениях для регуляторной отчётности

**Fraud rate мониторинг:** `services/fraud/` (Jube :5001, Marble :5002)

---

## Реализация в BANXE (SANDBOX reference)

```
Платёжный запрос
  → AML Check (L3 auto + HITL gate)
  → SCA required? → check exemptions
  → SCA triggered → Keycloak AuthN (TOTP/WebAuthn)
  → Dynamic linking → transaction confirmed
  → Ledger (Midaz) → create_tx()
  → Audit log (ClickHouse, I-24)
```

---

## Ключевые политики (PLACEHOLDER)

- `SCA-POLICY-001`: Минимальные требования к факторам аутентификации [PLACEHOLDER]
- `SCA-POLICY-002`: Список разрешённых исключений по юрисдикциям [PLACEHOLDER]
- `SCA-POLICY-003`: Процедура мониторинга fraud rate для TRA [PLACEHOLDER]

---

## Теги для Graphiti

`psd2` `sca` `authentication` `dynamic-linking` `tra` `exemptions`  
`knowledge` `possession` `inherence` `fraud-rate` `keycloak` `sandbox`

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | BANXE 2026*
