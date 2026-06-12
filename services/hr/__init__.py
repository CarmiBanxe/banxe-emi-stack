"""HR operations domain seam (read + bounded-write) — IL-197 / Sprint-58.

Houses the :mod:`hr_port` hexagonal contract used by the ``HRAgent`` (ORG-STRUCTURE
§2.9) to run routine people-operations (training tracking, conduct-rule attestations)
and to prepare/apply Senior-Management-Function (SMF) appointments. Routine HR ops are
L1 AUTO; an SMF appointment is NEVER autonomous — its application requires a CEO
authorization token (SM&CR), enforced both at the port (``apply_smf_appointment`` raises
without a token) and at the agent governance layer (forced CEO step-up, defence-in-depth).

The mask reads SMF/role data from the existing SM&CR registry
(``services/compliance_automation/smcr_registry.py``) through a read-only
:class:`~services.hr.hr_port.SMCRReadHandle` Protocol — it never imports or mutates the
compliance_automation domain. No real HRIS integration yet (I-10): the in-memory doubles
here are unit-test scaffolding only.
"""
