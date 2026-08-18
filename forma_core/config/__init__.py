"""Central configuration package for Forma.

Callers should normally import the live singleton with::

    from forma_core.config import config

Runtime resolution and the credential-safe client contract are kept alongside
the environment boundary in this package.
"""

from forma_core.config.environment import (
    AppConfig,
    CLOUDFLARE_ENABLE_THINKING_ENV,
    DEFAULT_GENERATION_WORKFLOW,
    DEFAULT_GENERATION_WORKFLOW_ENV,
    TRUE_VALUES,
    config,
)


__all__ = [
    "AppConfig",
    "CLOUDFLARE_ENABLE_THINKING_ENV",
    "DEFAULT_GENERATION_WORKFLOW",
    "DEFAULT_GENERATION_WORKFLOW_ENV",
    "TRUE_VALUES",
    "config",
]
