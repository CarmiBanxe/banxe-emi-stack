from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from difflib import SequenceMatcher
import hashlib

from services.sanctions_screening.models import (
    EntityType,
    HitStore,
    ListSource,
    ListStore,
    MatchConfidence,
    ScreeningHit,
    ScreeningReport,
    ScreeningRequest,
    ScreeningResult,
    ScreeningStore,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
AML_EDD_THRESHOLD = Decimal("10000")  # I-04
MATCH_THRESHOLD_POSSIBLE = Decimal("65")  # I-01
MATCH_THRESHOLD_CONFIRMED = Decimal("85")  # I-01

_ALL_SOURCES = [ListSource.OFSI, ListSource.EU_CONSOLIDATED]


class ScreeningEngine:
    def __init__(
        self,
        screening_store: ScreeningStore,
        list_store: ListStore,
        hit_store: HitStore,
    ) -> None:
        self._store = screening_store
        self._lists = list_store
        self._hits = hit_store

    def screen_entity(
        self,
        entity_name: str,
        entity_type: EntityType | str,
        nationality: str,
        date_of_birth: str | None = None,
        requested_by: str = "system",
    ) -> ScreeningReport:
        ts = datetime.now(UTC).isoformat()
        raw = f"{entity_name}{ts}".encode()
        request_id = f"req_{hashlib.sha256(raw).hexdigest()[:8]}"
        etype = EntityType(entity_type) if isinstance(entity_type, str) else entity_type
        req = ScreeningRequest(
            request_id, entity_name, etype, nationality, date_of_birth, requested_by, ts
        )
        self._store.save_request(req)

        # I-02: hard-block for blocked jurisdictions
        if nationality.upper() in BLOCKED_JURISDICTIONS:
            report_id = f"rep_{hashlib.sha256(request_id.encode()).hexdigest()[:8]}"
            report = ScreeningReport(
                report_id=report_id,
                request_id=request_id,
                result=ScreeningResult.CONFIRMED_MATCH,
                hits=[],
                screened_at=ts,
                notes=f"I-02: blocked jurisdiction {nationality.upper()}",
            )
            self._store.save_report(report)
            return report

        hits = self._scan_lists(request_id, entity_name, nationality, date_of_birth)
        result = self._determine_result(hits)
        report_id = f"rep_{hashlib.sha256(request_id.encode()).hexdigest()[:8]}"
        report = ScreeningReport(
            report_id=report_id, request_id=request_id, result=result, hits=hits, screened_at=ts
        )
        self._store.save_report(report)
        return report

    def screen_transaction(
        self,
        counterparty_name: str,
        amount_gbp: Decimal,
        nationality: str,
    ) -> ScreeningReport:
        notes = ""
        if amount_gbp >= AML_EDD_THRESHOLD:  # I-04
            notes = f"I-04: EDD required — amount £{amount_gbp} >= £{AML_EDD_THRESHOLD}"
        report = self.screen_entity(counterparty_name, EntityType.INDIVIDUAL, nationality)
        # Rebuild report with EDD note if needed
        if notes:
            ts = datetime.now(UTC).isoformat()
            report = ScreeningReport(
                report_id=report.report_id,
                request_id=report.request_id,
                result=report.result,
                hits=report.hits,
                screened_at=report.screened_at,
                notes=notes,
            )
            self._store.save_report(report)
        return report

    def batch_screen(self, entities: list[dict]) -> list[ScreeningReport]:
        return [
            self.screen_entity(
                e.get("name", ""),
                e.get("entity_type", EntityType.INDIVIDUAL),
                e.get("nationality", "GB"),
                e.get("date_of_birth"),
                e.get("requested_by", "system"),
            )
            for e in entities
        ]

    def get_screening_history(self, entity_name: str) -> list[ScreeningReport]:
        # Return all reports — simplified: scan all saved requests
        results = []
        return results  # stub: no full-text search in InMemory

    def calculate_match_score(self, name_a: str, name_b: str) -> Decimal:  # I-01
        ratio = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
        return Decimal(str(ratio * 100)).quantize(Decimal("0.01"))

    # --- private helpers ---

    def _scan_lists(
        self,
        request_id: str,
        entity_name: str,
        nationality: str,
        dob: str | None,
    ) -> list[ScreeningHit]:
        hits: list[ScreeningHit] = []
        for source in _ALL_SOURCES:
            entries = self._lists.get_entries(source)
            for entry in entries:
                score = self.calculate_match_score(entity_name, entry["name"])
                if score < MATCH_THRESHOLD_POSSIBLE:
                    continue
                confidence = (
                    MatchConfidence.HIGH
                    if score >= MATCH_THRESHOLD_CONFIRMED
                    else MatchConfidence.MEDIUM
                )
                entry_id = entry["id"]
                hit_id = f"hit_{hashlib.sha256(f'{request_id}{entry_id}'.encode()).hexdigest()[:8]}"
                hit = ScreeningHit(
                    hit_id=hit_id,
                    request_id=request_id,
                    list_source=source,
                    match_confidence=confidence,
                    match_score=score,
                    matched_name=entry["name"],
                    matched_entity_id=entry["id"],
                    details=f"nationality:{entry.get('nationality', '?')} type:{entry.get('type', '?')}",
                )
                self._hits.append(hit)  # I-24
                hits.append(hit)
        return hits

    def _determine_result(self, hits: list[ScreeningHit]) -> ScreeningResult:
        if not hits:
            return ScreeningResult.CLEAR
        if any(h.match_confidence == MatchConfidence.HIGH for h in hits):
            return ScreeningResult.CONFIRMED_MATCH
        return ScreeningResult.POSSIBLE_MATCH
