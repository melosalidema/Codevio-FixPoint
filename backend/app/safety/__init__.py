"""Deterministic safety layer.

Nothing in this package performs network I/O or trusts model output. It is the
only code path allowed to authorize or record mutations:

* :mod:`app.safety.models` - shared pydantic contracts
* :mod:`app.safety.canonical` - canonical JSON, action hashing, idempotency keys
* :mod:`app.safety.approval` - HMAC-signed, single-use, action-bound approvals
* :mod:`app.safety.audit` - append-only hash-chained ledger
* :mod:`app.safety.gateway` - deny-by-default policy enforcement point
* :mod:`app.safety.webhooks` - signature and replay verification
* :mod:`app.safety.verifier` - independent post-mutation verification
"""
