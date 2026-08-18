"""Compatibility facade for image persistence now owned by Forma Core."""

from forma_core.persistence.images import *  # noqa: F401,F403
from forma_core.persistence.images import _supabase_storage_bucket  # noqa: F401
