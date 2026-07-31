from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from blueprint_core import project_list_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, int]] = []

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.set_calls.append((key, ex))

    def incr(self, key: str) -> int:
        next_value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(next_value)
        return next_value


class ProjectListCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        project_list_cache._disabled_until = 0.0

    def test_round_trip_uses_hashed_identity_and_configured_ttl(self) -> None:
        redis = _FakeRedis()
        projects = [{"project_id": "project-1", "can_chat": True}]

        with patch.object(project_list_cache, "_get_redis_client", return_value=redis), patch.dict(
            "os.environ",
            {"PROJECTS_CACHE_TTL_SECONDS": "90", "REDIS_CACHE_PREFIX": "test"},
            clear=False,
        ):
            missed, generation = project_list_cache.get_cached_project_list("mine", "user-secret-id")
            project_list_cache.cache_project_list("mine", "user-secret-id", projects, generation)
            cached, cached_generation = project_list_cache.get_cached_project_list("mine", "user-secret-id")

        self.assertIsNone(missed)
        self.assertEqual("0", generation)
        self.assertEqual(projects, cached)
        self.assertEqual("0", cached_generation)
        self.assertEqual(90, redis.set_calls[0][1])
        self.assertNotIn("user-secret-id", redis.set_calls[0][0])
        self.assertEqual(projects, json.loads(redis.values[redis.set_calls[0][0]]))

    def test_invalidation_moves_readers_to_a_new_generation(self) -> None:
        redis = _FakeRedis()
        projects = [{"project_id": "project-1"}]

        with patch.object(project_list_cache, "_get_redis_client", return_value=redis):
            _, old_generation = project_list_cache.get_cached_project_list("public", None)
            project_list_cache.cache_project_list("public", None, projects, old_generation)
            project_list_cache.invalidate_project_lists()
            cached, new_generation = project_list_cache.get_cached_project_list("public", None)

        self.assertIsNone(cached)
        self.assertEqual("0", old_generation)
        self.assertEqual("1", new_generation)

    def test_no_redis_is_a_no_op(self) -> None:
        with patch.object(project_list_cache, "_get_redis_client", return_value=None):
            cached, generation = project_list_cache.get_cached_project_list("public", None)
            project_list_cache.cache_project_list("public", None, [], generation)
            project_list_cache.invalidate_project_lists()

        self.assertIsNone(cached)
        self.assertIsNone(generation)


if __name__ == "__main__":
    unittest.main()
