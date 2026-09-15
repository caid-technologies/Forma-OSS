from pathlib import Path
p = Path('tests/api/test_project_list_cache.py')
s = p.read_text()
pos = s.index('\n\nif __name__')
s = s[:pos] + '''

class ProjectPageCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        project_list_cache._disabled_until = 0.0
        self.redis = _FakeRedis()
        self.client_patch = patch.object(project_list_cache, "_get_redis_client", return_value=self.redis)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.addCleanup(setattr, project_list_cache, "_disabled_until", 0.0)

    def test_page_round_trip_uses_ttl_and_separates_all_query_dimensions(self) -> None:
        items = [{"project_id": "one"}]
        with patch.object(project_list_cache, "_cache_ttl_seconds", return_value=90):
            missed, generation = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0, search="private query")
            self.assertIsNone(missed)
            project_list_cache.cache_project_page("public", None, items, 25, generation, limit=6, offset=0, search="private query")
        cached, _ = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0, search="private query")
        self.assertEqual({"items": items, "total": 25}, cached)
        self.assertEqual(90, self.redis.set_calls[0][1])
        self.assertNotIn("private query", self.redis.set_calls[0][0])
        for scope, owner, limit, offset, search in [
            ("public", None, 6, 6, "private query"),
            ("public", None, 12, 0, "private query"),
            ("public", None, 6, 0, "different"),
            ("mine", "user-a", 6, 0, "private query"),
            ("public", "user-b", 6, 0, "private query"),
        ]:
            self.assertIsNone(project_list_cache.get_cached_project_page(scope, owner, limit=limit, offset=offset, search=search)[0])
        self.assertIsNone(project_list_cache.get_cached_project_list("public", None)[0])

    def test_invalidation_also_rejects_a_late_write_from_the_old_generation(self) -> None:
        _, generation = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0)
        project_list_cache.invalidate_project_lists()
        project_list_cache.cache_project_page("public", None, [{"project_id": "deleted"}], 1, generation, limit=6, offset=0)
        cached, next_generation = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0)
        self.assertIsNone(cached)
        self.assertEqual("1", next_generation)

    def test_empty_page_is_a_hit_and_does_not_mutate_the_stored_payload(self) -> None:
        _, generation = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0)
        project_list_cache.cache_project_page("public", None, [], 0, generation, limit=6, offset=0)
        page, _ = project_list_cache.get_cached_project_page("public", None, limit=6, offset=0)
        self.assertEqual({"items": [], "total": 0}, page)
        page["items"].append({"project_id": "mutated"})
        self.assertEqual([], project_list_cache.get_cached_project_page("public", None, limit=6, offset=0)[0]["items"])

    def test_disabled_cache_and_failed_reads_fall_back_without_failing_requests(self) -> None:
        with patch.object(project_list_cache, "_get_redis_client", return_value=None):
            self.assertEqual((None, None), project_list_cache.get_cached_project_page("public", None, limit=6, offset=0))
            project_list_cache.cache_project_page("public", None, [], 0, None, limit=6, offset=0)
        with patch.object(self.redis, "get", side_effect=RuntimeError("offline")), self.assertLogs(project_list_cache.logger):
            self.assertEqual((None, None), project_list_cache.get_cached_project_page("public", None, limit=6, offset=0))
        self.assertEqual([], self.redis.set_calls)

    def test_malformed_payload_is_a_miss(self) -> None:
        key = project_list_cache._page_data_key("public", None, "0", 6, 0, None)
        for payload in [[], {"items": [], "total": True}, {"items": ["bad"], "total": 1}, {"items": [], "total": -1}]:
            project_list_cache._disabled_until = 0.0
            self.redis.values[key] = json.dumps(payload)
            with self.assertLogs(project_list_cache.logger):
                self.assertEqual((None, None), project_list_cache.get_cached_project_page("public", None, limit=6, offset=0))
''' + s[pos:]
p.write_text(s)
p = Path('tests/api/test_project_access.py')
s = p.read_text()
s = s.replace('        stack.enter_context(patch.object(main, "cache_project_list"))', '        stack.enter_context(patch.object(main, "cache_project_list"))\n        stack.enter_context(patch.object(main, "get_cached_project_page", return_value=(None, None)))\n        stack.enter_context(patch.object(main, "cache_project_page"))', 1)
pos = s.index('    def test_owner_list_includes_canonical_project_without_legacy_row(')
s = s[:pos] + '''    def test_public_page_cache_hit_keeps_owner_permissions_and_saved_state_private(self) -> None:
        base = {
            "project_id": "public-project",
            main._CACHE_OWNER_DIGEST_FIELD: main._project_owner_digest("user-a"),
            main._CACHE_OWNER_CHAT_FIELD: "owner-chat",
        }
        def engagement(_ids, user_id):
            return {"public-project": {"save_count": 5, "remix_count": 2, "saved": user_id == "user-a"}}
        with patch.object(main, "get_cached_project_page", return_value=({"items": [base], "total": 1}, "3")), patch.object(main, "project_engagement_for_ids", side_effect=engagement), patch.object(main, "_paginated_gallery_summaries") as db:
            owner = main.list_projects_endpoint(_user_context("user-a"), limit=6)
            other = main.list_projects_endpoint(_user_context("user-b"), limit=6)
            anonymous = main.list_projects_endpoint(_anonymous_context(), limit=6)
        db.assert_not_called()
        self.assertTrue(owner["items"][0]["can_chat"])
        self.assertTrue(owner["items"][0]["saved"])
        self.assertEqual("owner-chat", owner["items"][0]["chat_id"])
        for response in (other, anonymous):
            self.assertFalse(response["items"][0]["can_chat"])
            self.assertFalse(response["items"][0]["saved"])
            self.assertIsNone(response["items"][0]["chat_id"])
        for response in (owner, other, anonymous):
            self.assertNotIn(main._CACHE_OWNER_DIGEST_FIELD, response["items"][0])
            self.assertNotIn(main._CACHE_OWNER_CHAT_FIELD, response["items"][0])
        self.assertNotIn("saved", base)
        self.assertNotIn("can_chat", base)

    def test_public_page_cache_miss_normalizes_query_and_caches_only_base_records(self) -> None:
        base = {"project_id": "public-project", main._CACHE_OWNER_DIGEST_FIELD: "digest"}
        with patch.object(main, "get_cached_project_page", return_value=(None, "4")) as lookup, patch.object(main, "_paginated_gallery_summaries", return_value=([base], 1)) as db, patch.object(main, "cache_project_page") as store, patch.object(main, "project_engagement_for_ids", return_value={}):
            response = main.list_projects_endpoint(_anonymous_context(), limit=99, offset=-1, q=" fan ")
        lookup.assert_called_once_with("public", None, limit=50, offset=0, search="fan")
        self.assertEqual(50, db.call_args.kwargs["limit"])
        self.assertEqual(0, db.call_args.kwargs["offset"])
        self.assertEqual("fan", db.call_args.kwargs["search"])
        store.assert_called_once_with("public", None, [base], 1, "4", limit=50, offset=0, search="fan")
        self.assertEqual(50, response["limit"])
        self.assertFalse(response["has_more"])
        self.assertNotIn("saved", base)

''' + s[pos:]
p.write_text(s)
p = Path('apps/web/e2e/project-pagination.spec.ts')
p.write_text(p.read_text() + r'''

test.describe("gallery loading performance", () => {
  test("a cached page stays mounted while its refresh is pending", async ({ page }) => {
    let firstPageReads = 0;
    let release!: () => void;
    const pendingRefresh = new Promise<void>((resolve) => { release = resolve; });
    await page.route(/^https?:\/\/(?:localhost|127\.0\.0\.1):8000\/(?:api\/)?projects(?:\?|$)/, async (route) => {
      const url = new URL(route.request().url());
      if (Number(url.searchParams.get("offset") || 0) === 0 && ++firstPageReads > 1) {
        await pendingRefresh;
      }
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(pageResponse(url)) });
    });
    try {
      await openRoute(page, "/projects");
      await expect(projectCards(page)).toHaveCount(6);
      await page.getByRole("button", { name: "Next", exact: true }).click();
      await expect(projectCards(page)).toHaveCount(1);
      await page.getByRole("button", { name: "Previous", exact: true }).click();
      await expect.poll(() => firstPageReads).toBe(2);
      await expect(projectCards(page)).toHaveCount(6);
      await expect(page.locator(".forma-gui-card-skeleton")).toHaveCount(0);
      await expect(page.getByText("Page 1 of 2")).toBeVisible();
    } finally {
      release();
    }
  });

  test("a fast image is displayed while a sibling image summary is pending", async ({ page }) => {
    const counts = new Map<string, number>();
    let release!: () => void;
    const slow = new Promise<void>((resolve) => { release = resolve; });
    await mockProjectList(page, "projects");
    await page.route(/\/projects\/project-\d+\/image-summary$/, async (route) => {
      const id = route.request().url().match(/project-\d+/)![0];
      counts.set(id, (counts.get(id) || 0) + 1);
      if (id === "project-2") await slow;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({
        product_image_url: `https://images.example.test/${id}.svg`,
      }) });
    });
    await page.route("https://images.example.test/**", (route) => route.fulfill({
      contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>',
    }));
    try {
      await openRoute(page, "/projects");
      await expect(page.locator('img[src="https://images.example.test/project-1.svg"]')).toBeVisible();
      await expect.poll(() => counts.get("project-2")).toBe(1);
      await expect(page.locator('img[src="https://images.example.test/project-2.svg"]')).toHaveCount(0);
      release();
      await expect(page.locator('img[src="https://images.example.test/project-2.svg"]')).toBeVisible();
      expect(counts.get("project-2")).toBe(1);
    } finally {
      release();
    }
  });

  test("a failed uncached search shows an error, not stale results or an empty success", async ({ page }) => {
    await page.route(/^https?:\/\/(?:localhost|127\.0\.0\.1):8000\/(?:api\/)?projects(?:\?|$)/, async (route) => {
      const url = new URL(route.request().url());
      await route.fulfill(url.searchParams.has("q")
        ? { status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Gallery temporarily unavailable" }) }
        : { contentType: "application/json", body: JSON.stringify(pageResponse(url)) });
    });
    await openRoute(page, "/projects");
    await expect(projectCards(page)).toHaveCount(6);
    await page.getByPlaceholder("Search projects").fill("offline");
    await expect(page.getByText("Projects unavailable", { exact: true })).toBeVisible();
    await expect(page.locator(".forma-gui-card:not(.forma-gui-card-skeleton)")).toHaveCount(0);
  });
});
''')
