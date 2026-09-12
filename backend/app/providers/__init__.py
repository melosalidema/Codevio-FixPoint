"""Tenant-scoped provider access.

``world`` contains the resettable/seedable mock providers (the "twins") used
for deterministic demos and evaluations. ``adapters`` is the only interface the
agent may call to read or mutate provider state; it injects the sealed tenant id
and never reads credentials or tenant ids from model arguments.
"""

from app.providers.adapters import AdapterSet
from app.providers.world import ProviderError, World

__all__ = ["AdapterSet", "ProviderError", "World"]
