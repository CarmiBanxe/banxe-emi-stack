"""
services/hitl/feedback_loop.py — Supervised HITL Feedback Loop (IL-056)
Phase 2 #10 | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
CTIO and CEO review HOLD cases and record decisions (APPROVE / REJECT / ESCALATE).
Each decision is written to the feedback corpus in HITLService.

This module analyses that corpus and produces a FeedbackReport with:
  - Pattern statistics: approval rates by review reason, fraud score bucket, amount
  - ThresholdProposals: suggested parameter changes (NEVER applied automatically)
  - DeciderStats: per-operator activity (audit trail, bias detection)

I-27 (INVARIANT — HARD CONSTRAINT):
  FeedbackLoopAnalyser PROPOSES only. No code is modified, no model is updated,
  no threshold is changed by this module. Every ThresholdProposal has
  requires_human_approval=True. The proposals are text artefacts for review.

FCA / regulatory basis:
  - EU AI Act Art.14: meaningful human oversight of high-risk AI decisions
  - PS22/9 Consumer Duty: monitor outcomes and act when patterns show consumer harm
  - MLR 2017 Reg.26: governance and internal controls must be reviewed

Typical usage (monthly or on-demand by CTIO / Compliance):
    from services.hitl.hitl_service import HITLService
    from services.hitl.feedback_loop import FeedbackLoopAnalyser

    svc = HITLService()
    corpus = svc.get_feedback_corpus()
    report = FeedbackLoopAnalyser().analyse(corpus)
    print(report.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import logging
from statistics import mean

logger = logging.getLogger(__name__)

# ── Minimum sample sizes ──────────────────────────────────────────────────────
_MIN_SAMPLE_PROPOSAL = 10  # minimum decisions to issue a ThresholdProposal
_MIN_SAMPLE_STATS = 3  # minimum decisions to report bucket stats

# ── Proposal confidence bands ─────────────────────────────────────────────────
_CONF_HIGH = "HIGH"  # ≥ 30 samples and clear signal
_CONF_MEDIUM = "MEDIUM"  # 10-29 samples
_CONF_LOW = "LOW"  # < 10 samples (informational only)

# ── Thresholds that trigger proposals ─────────────────────────────────────────
_APPROVAL_HIGH_WATERMARK = 0.85  # if approval_rate > this → threshold may be too conservative
_APPROVAL_LOW_WATERMARK = (
    0.15  # if approval_rate < this → almost always rejected, auto-reject candidate
)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ReasonStats:
    """
    Approval / rejection pattern for a single ReviewReason.
    Source: HITLDecision.reasons field in corpus.
    """

    reason: str
    total: int
    approved: int
    rejected: int
    escalated: int
    approval_rate: float  # approved / (approved + rejected); None if no terminal decisions
    avg_fraud_score: float
    avg_amount: Decimal

    @property
    def terminal_count(self) -> int:
        return self.approved + self.rejected


@dataclass
class RiskBucketStats:
    """
    Approval rate bucketed by fraud score (0-9, 10-19, ..., 90-100).
    Identifies which fraud score ranges are routinely approved vs rejected.
    """

    bucket_label: str  # e.g. "60-69"
    bucket_min: int
    bucket_max: int
    total: int
    approved: int
    rejected: int
    approval_rate: float


@dataclass
class AmountBucketStats:
    """Approval rate bucketed by transaction amount (GBP bands)."""

    bucket_label: str  # e.g. "£1k-5k"
    total: int
    approved: int
    rejected: int
    approval_rate: float


@dataclass
class DeciderStats:
    """
    Per-operator (CTIO / CEO / MLRO) decision statistics.
    Supports FCA audit trail and bias detection.
    """

    decided_by: str
    total_decisions: int
    approved: int
    rejected: int
    escalated: int
    approval_rate: float
    avg_fraud_score: float
    top_reasons: list[str]  # top 3 reasons this operator sees


@dataclass
class ThresholdProposal:
    """
    A SUPERVISED proposal to adjust a decision threshold.

    I-27: requires_human_approval is ALWAYS True.
    This object is never executed — it is a text artefact for human review.
    """

    proposal_id: str
    parameter: str  # e.g. "FRAUD_HOLD_THRESHOLD", "VELOCITY_DAILY_LIMIT"
    current_value: str  # human-readable current value
    proposed_direction: str  # "RAISE" | "LOWER" | "REVIEW"
    rationale: str
    evidence: str  # statistics that support this proposal
    confidence: str  # HIGH / MEDIUM / LOW
    requires_human_approval: bool = True  # I-27: ALWAYS True
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_direction": self.proposed_direction,
            "rationale": self.rationale,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "requires_human_approval": self.requires_human_approval,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class FeedbackReport:
    """
    Full supervised learning report produced by FeedbackLoopAnalyser.

    Includes:
      - reason_stats: by ReviewReason
      - risk_buckets: by fraud score band
      - amount_buckets: by amount band
      - decider_stats: per operator
      - proposals: ThresholdProposals (human must apply)
      - corpus_size: how many decisions were analysed
      - generated_at: report timestamp
    """

    corpus_size: int
    reason_stats: list[ReasonStats]
    risk_buckets: list[RiskBucketStats]
    amount_buckets: list[AmountBucketStats]
    decider_stats: list[DeciderStats]
    proposals: list[ThresholdProposal]
    generated_at: datetime

    def summary(self) -> str:
        """Return a human-readable summary for CTIO/CEO review."""
        lines = [
            "=== HITL Feedback Report ===",
            f"Generated: {self.generated_at.strftime('%d %b %Y %H:%M UTC')}",
            f"Corpus: {self.corpus_size} decisions analysed",
            "",
            "── Approval rates by reason ──",
        ]
        for rs in sorted(self.reason_stats, key=lambda r: r.approval_rate):
            lines.append(
                f"  {rs.reason:<25} {rs.approval_rate * 100:5.1f}% approve "
                f"({rs.total} cases, avg fraud {rs.avg_fraud_score:.0f})"
            )
        if self.proposals:
            lines.append("")
            lines.append(f"── Proposals ({len(self.proposals)}) — REQUIRE HUMAN APPROVAL ──")
            for p in self.proposals:
                lines.append(
                    f"  [{p.confidence}] {p.parameter}: {p.proposed_direction} — {p.rationale}"
                )
        else:
            lines.append("")
            lines.append("── No threshold proposals (insufficient data or no clear signal) ──")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "corpus_size": self.corpus_size,
            "generated_at": self.generated_at.isoformat(),
            "proposals": [p.to_dict() for p in self.proposals],
            "reason_stats": [
                {
                    "reason": rs.reason,
                    "total": rs.total,
                    "approved": rs.approved,
                    "rejected": rs.rejected,
                    "escalated": rs.escalated,
                    "approval_rate": rs.approval_rate,
                    "avg_fraud_score": rs.avg_fraud_score,
                    "avg_amount": str(rs.avg_amount),
                }
                for rs in self.reason_stats
            ],
            "decider_stats": [
                {
                    "decided_by": ds.decided_by,
                    "total_decisions": ds.total_decisions,
                    "approval_rate": ds.approval_rate,
                    "top_reasons": ds.top_reasons,
                }
                for ds in self.decider_stats
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Analyser
# ─────────────────────────────────────────────────────────────────────────────


class FeedbackLoopAnalyser:
    """
    Reads the HITL feedback corpus and produces a FeedbackReport.

    I-27: this class NEVER modifies thresholds, NEVER writes to any store,
    NEVER triggers automated actions. It is purely analytical.

    Args:
        min_sample_proposal: minimum corpus records needed to issue a proposal
        approval_high_watermark: if approval_rate > this, threshold may be too conservative
        approval_low_watermark: if approval_rate < this, cases routinely rejected

    Usage:
        corpus = hitl_service.get_feedback_corpus()
        report = FeedbackLoopAnalyser().analyse(corpus)
    """

    def __init__(
        self,
        min_sample_proposal: int = _MIN_SAMPLE_PROPOSAL,
        approval_high_watermark: float = _APPROVAL_HIGH_WATERMARK,
        approval_low_watermark: float = _APPROVAL_LOW_WATERMARK,
    ) -> None:
        self._min_sample = min_sample_proposal
        self._high = approval_high_watermark
        self._low = approval_low_watermark

    def analyse(self, corpus: list[dict]) -> FeedbackReport:
        """
        Analyse feedback corpus → FeedbackReport.

        corpus: list of dicts from HITLDecision.to_corpus_record()
        Each record has: case_id, transaction_id, customer_id, amount,
                         fraud_score, reasons, outcome, decided_by, decided_at, notes
        """
        if not corpus:
            logger.info("FeedbackLoopAnalyser: empty corpus, returning empty report")
            return FeedbackReport(
                corpus_size=0,
                reason_stats=[],
                risk_buckets=[],
                amount_buckets=[],
                decider_stats=[],
                proposals=[],
                generated_at=datetime.now(UTC),
            )

        reason_stats = self._analyse_by_reason(corpus)
        risk_buckets = self._analyse_risk_buckets(corpus)
        amount_buckets = self._analyse_amount_buckets(corpus)
        decider_stats = self._analyse_deciders(corpus)
        proposals = self._propose_thresholds(reason_stats, risk_buckets)

        logger.info(
            "FeedbackLoopAnalyser: corpus=%d decisions analysed, %d proposals generated",
            len(corpus),
            len(proposals),
        )

        return FeedbackReport(
            corpus_size=len(corpus),
            reason_stats=reason_stats,
            risk_buckets=risk_buckets,
            amount_buckets=amount_buckets,
            decider_stats=decider_stats,
            proposals=proposals,
            generated_at=datetime.now(UTC),
        )

    # ── Reason stats ──────────────────────────────────────────────────────────

    def _analyse_by_reason(self, corpus: list[dict]) -> list[ReasonStats]:
        """
        Group corpus records by review reason and compute per-reason statistics.
        A single decision may have multiple reasons — it counts in each.
        """
        from collections import defaultdict

        buckets: dict[str, list[dict]] = defaultdict(list)
        for record in corpus:
            for reason in record.get("reasons", []):
                buckets[reason].append(record)

        result: list[ReasonStats] = []
        for reason, records in sorted(buckets.items()):
            approved = sum(1 for r in records if r.get("outcome") == "APPROVE")
            rejected = sum(1 for r in records if r.get("outcome") == "REJECT")
            escalated = sum(1 for r in records if r.get("outcome") == "ESCALATE")
            terminal = approved + rejected
            approval_rate = (approved / terminal) if terminal > 0 else 0.0

            fraud_scores = [
                r.get("fraud_score", 0) for r in records if r.get("fraud_score") is not None
            ]
            amounts = [Decimal(str(r.get("amount", "0"))) for r in records]

            result.append(
                ReasonStats(
                    reason=reason,
                    total=len(records),
                    approved=approved,
                    rejected=rejected,
                    escalated=escalated,
                    approval_rate=approval_rate,
                    avg_fraud_score=mean(fraud_scores) if fraud_scores else 0.0,
                    avg_amount=(sum(amounts) / len(amounts)) if amounts else Decimal("0"),
                )
            )
        return result

    # ── Risk bucket stats ─────────────────────────────────────────────────────

    def _analyse_risk_buckets(self, corpus: list[dict]) -> list[RiskBucketStats]:
        """
        Split corpus by fraud score into 10-point buckets (0-9, 10-19, ..., 90-100).
        """
        # Build buckets: (min, max) → label
        bucket_defs = [(i, i + 9, f"{i}-{i + 9}") for i in range(0, 100, 10)]
        bucket_defs[-1] = (90, 100, "90-100")

        result = []
        for bmin, bmax, label in bucket_defs:
            records = [r for r in corpus if bmin <= int(r.get("fraud_score", 0)) <= bmax]
            if len(records) < _MIN_SAMPLE_STATS:
                continue
            approved = sum(1 for r in records if r.get("outcome") == "APPROVE")
            rejected = sum(1 for r in records if r.get("outcome") == "REJECT")
            terminal = approved + rejected
            approval_rate = (approved / terminal) if terminal > 0 else 0.0
            result.append(
                RiskBucketStats(
                    bucket_label=label,
                    bucket_min=bmin,
                    bucket_max=bmax,
                    total=len(records),
                    approved=approved,
                    rejected=rejected,
                    approval_rate=approval_rate,
                )
            )
        return result

    # ── Amount bucket stats ───────────────────────────────────────────────────

    def _analyse_amount_buckets(self, corpus: list[dict]) -> list[AmountBucketStats]:
        """
        Split corpus by transaction amount into GBP bands.
        Bands: £0-1k, £1k-5k, £5k-10k, £10k-50k, £50k+
        """
        bands = [
            (Decimal("0"), Decimal("999.99"), "£0-1k"),
            (Decimal("1000"), Decimal("4999.99"), "£1k-5k"),
            (Decimal("5000"), Decimal("9999.99"), "£5k-10k"),
            (Decimal("10000"), Decimal("49999.99"), "£10k-50k"),
            (Decimal("50000"), Decimal("999999999"), "£50k+"),
        ]
        result = []
        for bmin, bmax, label in bands:
            records = [r for r in corpus if bmin <= Decimal(str(r.get("amount", "0"))) <= bmax]
            if len(records) < _MIN_SAMPLE_STATS:
                continue
            approved = sum(1 for r in records if r.get("outcome") == "APPROVE")
            rejected = sum(1 for r in records if r.get("outcome") == "REJECT")
            terminal = approved + rejected
            approval_rate = (approved / terminal) if terminal > 0 else 0.0
            result.append(
                AmountBucketStats(
                    bucket_label=label,
                    total=len(records),
                    approved=approved,
                    rejected=rejected,
                    approval_rate=approval_rate,
                )
            )
        return result

    # ── Decider stats ─────────────────────────────────────────────────────────

    def _analyse_deciders(self, corpus: list[dict]) -> list[DeciderStats]:
        """
        Per-operator statistics: CTIO, CEO, MLRO etc.
        Supports bias detection and FCA accountability trail.
        """
        from collections import Counter, defaultdict

        by_decider: dict[str, list[dict]] = defaultdict(list)
        for record in corpus:
            decider = record.get("decided_by", "unknown")
            by_decider[decider].append(record)

        result = []
        for decider, records in sorted(by_decider.items()):
            approved = sum(1 for r in records if r.get("outcome") == "APPROVE")
            rejected = sum(1 for r in records if r.get("outcome") == "REJECT")
            escalated = sum(1 for r in records if r.get("outcome") == "ESCALATE")
            terminal = approved + rejected
            approval_rate = (approved / terminal) if terminal > 0 else 0.0

            fraud_scores = [
                r.get("fraud_score", 0) for r in records if r.get("fraud_score") is not None
            ]
            avg_fraud = mean(fraud_scores) if fraud_scores else 0.0

            # Top 3 reasons this operator sees
            all_reasons: list[str] = []
            for r in records:
                all_reasons.extend(r.get("reasons", []))
            top_reasons = [r for r, _ in Counter(all_reasons).most_common(3)]

            result.append(
                DeciderStats(
                    decided_by=decider,
                    total_decisions=len(records),
                    approved=approved,
                    rejected=rejected,
                    escalated=escalated,
                    approval_rate=approval_rate,
                    avg_fraud_score=avg_fraud,
                    top_reasons=top_reasons,
                )
            )
        return result

    # ── Threshold proposals ───────────────────────────────────────────────────

    def _propose_thresholds(
        self,
        reason_stats: list[ReasonStats],
        risk_buckets: list[RiskBucketStats],
    ) -> list[ThresholdProposal]:
        """
        Generate ThresholdProposals based on statistical patterns.

        I-27: These are TEXT ARTEFACTS. The caller must review and manually apply.
        Every proposal has requires_human_approval=True.
        """
        proposals: list[ThresholdProposal] = []
        p_id = 0

        def _next_id() -> str:
            nonlocal p_id
            p_id += 1
            return f"PROP-{p_id:03d}"

        def _confidence(sample: int) -> str:
            if sample >= 30:
                return _CONF_HIGH
            if sample >= _MIN_SAMPLE_PROPOSAL:
                return _CONF_MEDIUM
            return _CONF_LOW

        by_reason = {rs.reason: rs for rs in reason_stats}

        # ── VELOCITY: high approval → threshold may be too conservative ──────
        for reason_key in ("VELOCITY_DAILY", "VELOCITY_MONTHLY"):
            rs = by_reason.get(reason_key)
            if rs and rs.terminal_count >= self._min_sample and rs.approval_rate > self._high:
                proposals.append(
                    ThresholdProposal(
                        proposal_id=_next_id(),
                        parameter=reason_key.replace("VELOCITY_", "VELOCITY_LIMIT_"),
                        current_value="current limit",
                        proposed_direction="RAISE",
                        rationale=(
                            f"{rs.approval_rate * 100:.0f}% of {reason_key} holds are approved by operators "
                            f"({rs.approved}/{rs.terminal_count}). "
                            f"The velocity threshold may be lower than operationally necessary."
                        ),
                        evidence=(
                            f"Sample: {rs.total} cases | "
                            f"Avg fraud score: {rs.avg_fraud_score:.1f} | "
                            f"Avg amount: £{rs.avg_amount:,.2f}"
                        ),
                        confidence=_confidence(rs.terminal_count),
                    )
                )

        # ── EDD: high approval → EDD threshold may be too low ────────────────
        rs_edd = by_reason.get("EDD_REQUIRED")
        if (
            rs_edd
            and rs_edd.terminal_count >= self._min_sample
            and rs_edd.approval_rate > self._high
        ):
            proposals.append(
                ThresholdProposal(
                    proposal_id=_next_id(),
                    parameter="EDD_AMOUNT_THRESHOLD",
                    current_value="£10,000",
                    proposed_direction="RAISE",
                    rationale=(
                        f"{rs_edd.approval_rate * 100:.0f}% of EDD-triggered holds are approved. "
                        f"The £10,000 EDD threshold (I-04) may generate excessive manual work. "
                        f"Review with Compliance before changing — FCA/MLR 2017 Reg.28 applies."
                    ),
                    evidence=(
                        f"Sample: {rs_edd.total} cases | Avg amount: £{rs_edd.avg_amount:,.2f}"
                    ),
                    confidence=_confidence(rs_edd.terminal_count),
                )
            )

        # ── FRAUD: low approval → almost always rejected, auto-reject candidate ──
        rs_fraud = by_reason.get("FRAUD_HIGH")
        if (
            rs_fraud
            and rs_fraud.terminal_count >= self._min_sample
            and rs_fraud.approval_rate < self._low
        ):
            proposals.append(
                ThresholdProposal(
                    proposal_id=_next_id(),
                    parameter="FRAUD_HOLD_THRESHOLD",
                    current_value="score ≥ 70 → HOLD",
                    proposed_direction="LOWER",
                    rationale=(
                        f"Only {rs_fraud.approval_rate * 100:.0f}% of FRAUD_HIGH holds are approved "
                        f"({rs_fraud.approved}/{rs_fraud.terminal_count}). "
                        f"Most FRAUD_HIGH cases could transition directly to REJECT, "
                        f"reducing MLRO workload."
                    ),
                    evidence=(
                        f"Sample: {rs_fraud.total} cases | "
                        f"Avg fraud score: {rs_fraud.avg_fraud_score:.1f}"
                    ),
                    confidence=_confidence(rs_fraud.terminal_count),
                )
            )

        # ── STRUCTURING: routinely rejected → auto-reject candidate ───────────
        rs_struct = by_reason.get("STRUCTURING")
        if (
            rs_struct
            and rs_struct.terminal_count >= self._min_sample
            and rs_struct.approval_rate < self._low
        ):
            proposals.append(
                ThresholdProposal(
                    proposal_id=_next_id(),
                    parameter="STRUCTURING_AUTO_REJECT",
                    current_value="HOLD (human review)",
                    proposed_direction="REVIEW",
                    rationale=(
                        f"Only {rs_struct.approval_rate * 100:.0f}% of STRUCTURING holds are approved. "
                        f"Consider escalating directly to SAR filing without HOLD step. "
                        f"Requires Compliance review — POCA 2002 s.330 obligations apply."
                    ),
                    evidence=f"Sample: {rs_struct.total} cases",
                    confidence=_confidence(rs_struct.terminal_count),
                )
            )

        # ── Risk bucket: low-score range routinely approved → relax HOLD ─────
        for bucket in risk_buckets:
            if (
                bucket.bucket_max <= 69
                and bucket.total >= self._min_sample
                and bucket.approval_rate > self._high
            ):
                proposals.append(
                    ThresholdProposal(
                        proposal_id=_next_id(),
                        parameter="FRAUD_HOLD_THRESHOLD",
                        current_value="score ≥ 70 → HOLD",
                        proposed_direction="RAISE",
                        rationale=(
                            f"Fraud score bucket {bucket.bucket_label}: "
                            f"{bucket.approval_rate * 100:.0f}% approval rate "
                            f"({bucket.approved}/{bucket.total}). "
                            f"Cases in this band are routinely approved — "
                            f"raising HOLD threshold may reduce operator workload."
                        ),
                        evidence=(
                            f"Bucket {bucket.bucket_label}: {bucket.total} cases, "
                            f"approved {bucket.approved}, rejected {bucket.rejected}"
                        ),
                        confidence=_confidence(bucket.total),
                    )
                )
                break  # one proposal per parameter type is enough

        logger.debug(
            "FeedbackLoopAnalyser: %d proposals generated from %d reason buckets + %d risk buckets",
            len(proposals),
            len(reason_stats),
            len(risk_buckets),
        )
        return proposals
