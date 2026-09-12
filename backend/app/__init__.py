"""Fixpoint backend package.

The deterministic safety layer lives in :mod:`app.safety`; the untrusted
agent side lives in :mod:`app.agent`. Nothing in ``app.agent`` may mutate
provider state directly - every mutation flows through the Action Gateway.
"""

__version__ = "0.2.0"
