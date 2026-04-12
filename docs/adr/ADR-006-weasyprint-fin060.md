# ADR-006: WeasyPrint for FIN060 Monthly PDF Generation

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-015 + IL-052 + IL-054
**Author:** Moriel Carmi / Claude Code

---

## Context

FCA requires monthly FIN060a/b returns submitted as PDFs to the RegData portal (deadline: 15th of the following month, per CASS 15.12.4R). We need a PDF generation solution that:
1. Is self-hosted (financial data must not leave Banxe infrastructure)
2. Produces consistent, machine-readable PDFs matching FCA format expectations
3. Is Python-native (no external processes or API calls)
4. Supports HTML templates for maintainability

---

## Decision

**WeasyPrint** (Python HTML→PDF renderer, open-source, self-hosted).

Pipeline: `dbt models (fin060_monthly.sql)` → `fin060_generator.py` → `WeasyPrint` → `FIN060_YYYYMM.pdf` → `RegDataReturnService` → RegData API (stub).

---

## Rationale

| Criterion | WeasyPrint | reportlab | fpdf2 | wkhtmltopdf | JasperReports |
|-----------|-----------|-----------|-------|-------------|---------------|
| Python-native | Yes | Yes | Yes | No (subprocess) | No (JVM) |
| HTML templates | Yes | No (programmatic) | No (programmatic) | Yes | Yes |
| No external API | Yes | Yes | Yes | Yes | Yes |
| CSS/layout support | Full (CSS 2.1 + partial 3) | No | Minimal | Full | Full |
| WCAG accessibility | Good | Manual | Manual | Partial | Partial |
| Maintenance burden | Low (pip install) | Low | Low | High (binary) | High (JVM) |
| FCA format compliance | HTML template → easy to adjust | Hard to maintain | Hard to maintain | Possible | Possible |

WeasyPrint's HTML template approach makes it easiest to maintain FCA format compliance as requirements change.

---

## Consequences

### Positive
- HTML template (`services/reporting/fin060_generator.py`) is readable and auditable
- PDF output is reproducible: same input data → identical PDF (satisfies FCA reproducibility requirement)
- No subprocess or external service calls — pure Python

### Negative / Risks
- WeasyPrint has complex CSS dependencies (cairo, pango, libffi) — may be harder to install in some environments
- WeasyPrint is slower than reportlab for simple PDFs

### Mitigations
- `Dockerfile` includes WeasyPrint system dependencies
- `MockFIN060Generator` stub in `regdata_return.py` enables tests without WeasyPrint installed
- `# pragma: no cover` on `RealFIN060Generator` (infra dependency)

---

## RegData Submission (Stub)

The RegData API submission (`LiveRegDataClient`) is currently **STUB** — requires `FCA_REGDATA_API_KEY` (CEO action: obtain from FCA RegData portal). See `services/reporting/regdata_return.py` for the stub implementation.

---

## References

- `services/reporting/fin060_generator.py` — FIN060 generation
- `services/reporting/regdata_return.py` — RegData submission + stub
- `dbt/models/marts/fin060/fin060_monthly.sql` — source data
- IL-015: FIN060 Phase 4 (cron + submission)
- IL-052: FIN060 API + SAR auto-filing
