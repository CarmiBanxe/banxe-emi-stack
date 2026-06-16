"""Incident-response signal derivation (read-only) — IL-195 / Sprint-57.

Houses the :mod:`incident_signal_port` hexagonal contract used by the
``IncidentResponseAgent`` (ORG §2.7.4) to triage security incidents. The port is
READ + classify only: it derives incident signals from the existing read-only
observability / device-fingerprint / ATO-prevention sources and never closes or
suppresses an incident.
"""
