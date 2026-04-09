"""
mock_aspsp.py — Lightweight mock ASPSP (PSD2 sandbox)
FA-07 | IL-011 | FCA CASS 7.15 | banxe-emi-stack

Implements the subset of PSD2 AIS API used by statement_poller.py:
  GET /actuator/health
  GET /v1/accounts
  GET /v1/accounts/{account_id}/transactions

Returns CAMT.053 XML with configurable closing balances for the
two safeguarding accounts. Replaces adorsys open-banking-gateway
for sandbox validation of the full CAMT.053 → ReconciliationEngine pipeline.

Run:
  uvicorn services.recon.mock_aspsp:app --host 0.0.0.0 --port 8888
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from textwrap import dedent

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="Banxe Mock ASPSP", version="1.0.0")

# ── Config from env ───────────────────────────────────────────────────────────
# Sandbox IBANs — only set after network-isolation + logging validation
OPERATIONAL_IBAN = os.environ.get("SAFEGUARDING_OPERATIONAL_IBAN", "GB29BARC20201530093459")
CLIENT_FUNDS_IBAN = os.environ.get("SAFEGUARDING_CLIENT_FUNDS_IBAN", "GB94BARC20201530093460")
OPERATIONAL_ACCT = os.environ.get(
    "SAFEGUARDING_OPERATIONAL_ACCOUNT", "019d6332-f274-709a-b3a7-983bc8745886"
)
CLIENT_FUNDS_ACCT = os.environ.get(
    "SAFEGUARDING_CLIENT_FUNDS_ACCOUNT", "019d6332-da7f-752f-b9fd-fa1c6fc777ec"
)

# Mock balances — override in .env for specific test scenarios
MOCK_OPERATIONAL_BALANCE = Decimal(os.environ.get("MOCK_OPERATIONAL_BALANCE", "125000.00"))
MOCK_CLIENT_FUNDS_BALANCE = Decimal(os.environ.get("MOCK_CLIENT_FUNDS_BALANCE", "480000.00"))

_ACCOUNTS = [
    {
        "resourceId": OPERATIONAL_ACCT,
        "iban": OPERATIONAL_IBAN,
        "currency": "GBP",
        "name": "Banxe Safeguarding Operational",
        "accountType": "CACC",
        "_balance": MOCK_OPERATIONAL_BALANCE,
    },
    {
        "resourceId": CLIENT_FUNDS_ACCT,
        "iban": CLIENT_FUNDS_IBAN,
        "currency": "GBP",
        "name": "Banxe Safeguarding Client Funds",
        "accountType": "CACC",
        "_balance": MOCK_CLIENT_FUNDS_BALANCE,
    },
]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/actuator/health")
def health():
    return {"status": "UP", "service": "mock-aspsp"}


@app.get("/v1/accounts")
def list_accounts():
    accounts = [{k: v for k, v in acct.items() if not k.startswith("_")} for acct in _ACCOUNTS]
    return JSONResponse({"accounts": accounts})


@app.get("/v1/accounts/{account_id}/transactions")
def get_transactions(
    account_id: str,
    dateFrom: str = Query(default=None),
    dateTo: str = Query(default=None),
    bookingStatus: str = Query(default="booked"),
):
    acct = next((a for a in _ACCOUNTS if a["resourceId"] == account_id), None)
    if not acct:
        return Response(status_code=404)

    stmt_date = dateTo or dateFrom or date.today().isoformat()
    try:
        d = date.fromisoformat(stmt_date)
    except ValueError:
        d = date.today()

    xml = _build_camt053(acct, d)
    return Response(content=xml, media_type="application/xml")


# ── CAMT.053 builder ──────────────────────────────────────────────────────────


def _build_camt053(acct: dict, stmt_date: date) -> bytes:
    """
    Generate ISO 20022 CAMT.053 (Bank-to-Customer Statement) XML.
    Contains closing booked balance (CLBD) for the statement date.
    DECIMAL amounts only — never float (I-24).
    """
    balance = acct["_balance"]
    now_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    msg_id = f"BANXE-{stmt_date.strftime('%Y%m%d')}-{acct['resourceId'][-8:]}"

    xml = dedent(f"""\
    <?xml version="1.0" encoding="UTF-8"?>
    <Document
      xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <BkToCstmrStmt>
        <GrpHdr>
          <MsgId>{msg_id}</MsgId>
          <CreDtTm>{now_ts}</CreDtTm>
        </GrpHdr>
        <Stmt>
          <Id>{msg_id}-STMT</Id>
          <CreDtTm>{now_ts}</CreDtTm>
          <FrToDt>
            <FrDtTm>{stmt_date.isoformat()}T00:00:00+00:00</FrDtTm>
            <ToDtTm>{stmt_date.isoformat()}T23:59:59+00:00</ToDtTm>
          </FrToDt>
          <Acct>
            <Id><IBAN>{acct["iban"]}</IBAN></Id>
            <Ccy>{acct["currency"]}</Ccy>
            <Nm>{acct["name"]}</Nm>
          </Acct>
          <Bal>
            <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
            <Amt Ccy="{acct["currency"]}">{balance:.2f}</Amt>
            <CdtDbtInd>CRDT</CdtDbtInd>
            <Dt><Dt>{stmt_date.isoformat()}</Dt></Dt>
          </Bal>
        </Stmt>
      </BkToCstmrStmt>
    </Document>
    """)
    return xml.encode("utf-8")
