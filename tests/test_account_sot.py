"""MIG-M2.2 — advisory account/balance SoT scaffold (balance-free, read-only, sandbox-mock).

characterization: SoT port returns expected metadata/virtual-accounts/intermediaries; deterministic;
endpoints 200. contract/fence: DTOs are BALANCE-FREE (no balance/amount fields); SoT does NOT import
or call the Midaz ledger surface. fail-closed: counts consistent.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.models import account_sot as sot

client = TestClient(app)

_BALANCE_FIELDS = {"balance", "amount", "available", "ledger_balance", "amount_str"}


def test_metadata_shape_and_balance_free() -> None:
    resp = sot.account_sot_metadata_response()
    assert resp.source == "sandbox-mock"
    assert len(resp.accounts) == 3
    # balance-free: no balance/amount fields on any advisory DTO
    for model in (
        sot.AccountAdvisoryMetadata,
        sot.VirtualAccountDescriptor,
        sot.IntermediaryBankDescriptor,
    ):
        assert _BALANCE_FIELDS.isdisjoint(set(model.model_fields))


def test_virtual_accounts_and_intermediaries() -> None:
    va = sot.virtual_account_list_response()
    assert va.total == len(va.by_virtual_account) == 2
    assert all(v.source == "sandbox-mock" for v in va.by_virtual_account)
    inter = sot.intermediary_list_response()
    assert inter.total == len(inter.intermediaries) == 2


def test_deterministic() -> None:
    assert sot.account_sot_metadata_response() == sot.account_sot_metadata_response()


def test_sot_does_not_import_or_call_midaz_ledger() -> None:
    # fence: the SoT module must not import the live Midaz ledger surface / client (docstring may mention it)
    import api.models.account_sot as mod

    text = Path(mod.__file__).read_text()
    import_lines = [ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).lower()
    assert "ledger" not in joined and "midaz" not in joined  # no ledger/midaz imports
    assert "midaz_client" not in text  # no client call


def test_endpoints_200_balance_free() -> None:
    for path in (
        "/v1/account-sot/metadata",
        "/v1/account-sot/virtual-accounts",
        "/v1/account-sot/intermediaries",
    ):
        r = client.get(path)
        assert r.status_code == 200
        txt = r.text.lower()
        assert '"balance"' not in txt and '"amount"' not in txt
