"""Animator provider package — compatibility facade over the provider hub.

The registry, discovery, and lookup logic lives in
`studio.shared.providers_common.hub`; this module only binds the `animator` domain
and keeps the historical import surface working.
"""

from studio.shared.providers_common.hub import bind_domain

registry, discover, get_provider, list_providers, init_animator_registry = bind_domain('animator')

__all__ = ['registry', 'discover', 'get_provider', 'list_providers', 'init_animator_registry']
