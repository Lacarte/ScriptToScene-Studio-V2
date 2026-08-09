"""Script provider package — compatibility facade over the provider hub.

The registry, discovery, and lookup logic lives in
`studio.shared.providers_common.hub`; this module only binds the `script` domain
so the package has the same shape as the three domains that already ship
providers (contracts.md §19.2, §27).

Domain request/result models live in `contract.py` (contracts.md §32.1);
the shared ABC is `base.ScriptProvider`.
"""

from studio.shared.providers_common.hub import bind_domain
from studio.story.providers.base import ScriptProvider
from studio.story.providers.contract import ScriptRequest, ScriptResultPayload

registry, discover, get_provider, list_providers, init_script_registry = bind_domain('script')

__all__ = [
    'registry',
    'discover',
    'get_provider',
    'list_providers',
    'init_script_registry',
    'ScriptProvider',
    'ScriptRequest',
    'ScriptResultPayload',
]
