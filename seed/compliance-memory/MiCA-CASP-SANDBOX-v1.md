# MiCA / CASP — SANDBOX TRAINING DOCUMENT v1
# BANXE AI Bank | Compliance Memory Seed
# ⚠️ SANDBOX ONLY. NOT LEGAL ADVICE. Synthetic summary for AI training.
# Source inspiration: MiCA Regulation EU 2023/1114 (Markets in Crypto-Assets)

---

## Обзор: MiCA и BANXE как CASP

**Регулятор:** ESMA / National Competent Authorities (EU); FCA (UK — отдельный режим)  
**Вступление в силу:** 30 декабря 2024 (CASP provisions)  
**Применимо к BANXE:** Как провайдеру крипто-услуг (CASP — Crypto-Asset Service Provider)

---

## Классификация криптоактивов по MiCA

| Тип | Описание | Примеры | Дополнительные требования |
|-----|----------|---------|--------------------------|
| ART (Asset-Referenced Token) | Привязан к ≥2 активам/валютам/корзине | Синтетические стейблкоины | Whitepaper, reserve proof, capital req. |
| EMT (E-Money Token) | Привязан к 1 фиатной валюте | USDC (EUR), GBPT | Банковская лицензия / EMI required |
| Прочие | Не ART/EMT | BTC, ETH, utility tokens | Базовые CASP требования |

**Позиция BANXE:** EMI лицензия (FCA) позволяет работать с EMT. ART — отдельный анализ.

---

## CASP Authorisation Requirements

Для получения CASP авторизации по MiCA:

1. **Юридическое лицо** в ЕС (или признанная третья страна)
2. **Минимальный капитал:** [PLACEHOLDER] — зависит от типа услуг
3. **Fit and proper** требования к руководству
4. **Whitepaper** для каждого криптоактива (исключения для maliy сумм)
5. **Политики** AML/KYC, Market Abuse, Safeguarding
6. **Страхование** или аналогичный механизм защиты

---

## Whitepaper обязательства

| Требование | Описание |
|------------|----------|
| Содержание | Описание проекта, рисков, прав держателей, технологии |
| Публикация | До публичного предложения |
| Уведомление NCA | Не менее чем за 20 рабочих дней |
| Ответственность | Эмитент несёт ответственность за точность |
| Обновление | При существенных изменениях |

---

## Safeguarding клиентских криптоактивов (MiCA Art.70+)

> Аналог CASS 7 (FCA) для крипто-сферы

- Клиентские активы **сегрегированы** от активов CASP
- Не могут использоваться в собственных операциях CASP
- Ежедневная сверка (reconciliation)
- Запись в реестре клиентских активов
- Disaster recovery план для ключей/кошельков

**BANXE Implementation reference:** `services/safeguarding/`, CASS 15 P0 stack

---

## Travel Rule (FATF R.16 → MiCA Art.83)

| Порог | Требование | Статус |
|-------|------------|--------|
| [PLACEHOLDER] €1 000 | Передача originator + beneficiary info | PLACEHOLDER |
| Ниже порога | Рекомендуется, не обязательно | PLACEHOLDER |

**Данные originator:** Имя, DLT-адрес, номер счёта  
**Данные beneficiary:** Имя, DLT-адрес  
**Хранение:** 5 лет (FCA) / [PLACEHOLDER] по MiCA

---

## Market Abuse (MiCA Title VI)

| Запрещённое действие | Описание |
|---------------------|----------|
| Market Manipulation | Искусственное движение цены, wash trading, spoofing |
| Insider Dealing | Торговля на инсайдерской информации |
| Unlawful Disclosure | Раскрытие инсайдерской информации третьим лицам |

**BANXE obligations:**
- Политика и процедуры предотвращения market abuse
- Мониторинг подозрительных транзакций
- Уведомление NCA при подозрении (аналог SAR в AML)

---

## Ключевые политики (PLACEHOLDER)

- `MiCA-POLICY-001`: Классификация криптоактивов BANXE [PLACEHOLDER]
- `MiCA-POLICY-002`: Travel Rule implementation [PLACEHOLDER]
- `MiCA-POLICY-003`: Market Abuse monitoring procedures [PLACEHOLDER]
- `MiCA-POLICY-004`: Safeguarding клиентских crypto-активов [PLACEHOLDER]

---

## Теги для Graphiti

`mica` `casp` `crypto` `art` `emt` `travel-rule` `market-abuse`  
`safeguarding` `whitepaper` `insider-dealing` `market-manipulation`  
`esma` `eu-regulation` `sandbox`

---
*SANDBOX | TRAINING ONLY | NOT LEGAL ADVICE | BANXE 2026*
