from pathlib import Path
p = Path('forma_core/project_list_cache.py')
s = p.read_text()
addition = '''

def _page_data_key(
    scope: str, owner_user_id: Optional[str], generation: str,
    limit: int, offset: int, search: Optional[str],
) -> str:
    # Keep search text and user identifiers out of Redis keys. Callers pass the
    # same normalized pagination/search values to both the cache and the DB.
    query_digest = hashlib.sha256((search or "").encode("utf-8")).hexdigest()
    return f"{_data_key(scope, owner_user_id, generation)}:page:{limit}:{offset}:{query_digest}"


def get_cached_project_page(
    scope: str, owner_user_id: Optional[str], *, limit: int, offset: int,
    search: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Read an unpersonalized page using the existing list invalidation token."""
    client = _available_client()
    if client is None:
        return None, None
    try:
        generation = _current_generation(client)
        raw_value = client.get(_page_data_key(scope, owner_user_id, generation, limit, offset, search))
        if raw_value is None:
            return None, generation
        decoded = json.loads(raw_value)
        if (
            not isinstance(decoded, dict)
            or not isinstance(decoded.get("items"), list)
            or any(not isinstance(item, dict) for item in decoded["items"])
            or type(decoded.get("total")) is not int
            or decoded["total"] < 0
        ):
            raise ValueError("cached project page has an invalid shape")
        return decoded, generation
    except Exception as exc:
        _record_failure("page read", exc)
        return None, None


def cache_project_page(
    scope: str, owner_user_id: Optional[str], items: list[dict[str, Any]],
    total: int, generation: Optional[str], *, limit: int, offset: int,
    search: Optional[str] = None,
) -> None:
    """Cache base records, never response-specific saved/owner capabilities.

    A concurrent invalidation must leave this write in the OLD generation,
    just like cache_project_list. All existing list invalidations cover pages.
    """
    if generation is None:
        return
    client = _available_client()
    if client is None:
        return
    try:
        client.set(
            _page_data_key(scope, owner_user_id, generation, limit, offset, search),
            json.dumps({"items": items, "total": total}, separators=(",", ":"), ensure_ascii=False),
            ex=_cache_ttl_seconds(),
        )
    except Exception as exc:
        _record_failure("page write", exc)
'''
assert s.count('\ndef invalidate_project_lists() -> None:') == 1
s = s.replace('\ndef invalidate_project_lists() -> None:', addition + '\n\ndef invalidate_project_lists() -> None:')
p.write_text(s)
p = Path('apps/api/main.py')
s = p.read_text()
s = s.replace('    cache_project_list,\n    get_cached_project_list,', '    cache_project_list,\n    cache_project_page,\n    get_cached_project_list,\n    get_cached_project_page,', 1)
old = '''        if limit is not None:
            items, total = _paginated_gallery_summaries(
                owner_user_id=None,
                visibility="public",
                limit=limit,
                offset=offset,
                search=q,
                summary_builder=_gallery_inventory_cache_record,
                on_page_records=lambda records: _log_gallery_legacy_fallback("public", records),
                include_search_in_page_call=True,
            )
'''
new = '''        if limit is not None:
            limit = max(1, min(int(limit), 50))
            offset = max(0, int(offset))
            q = (q or "").strip() or None
            cached_page, generation = get_cached_project_page(
                "public", None, limit=limit, offset=offset, search=q,
            )
            if cached_page is not None:
                items, total = cached_page["items"], cached_page["total"]
            else:
                items, total = _paginated_gallery_summaries(
                    owner_user_id=None,
                    visibility="public",
                    limit=limit,
                    offset=offset,
                    search=q,
                    summary_builder=_gallery_inventory_cache_record,
                    on_page_records=lambda records: _log_gallery_legacy_fallback("public", records),
                    include_search_in_page_call=True,
                )
                cache_project_page(
                    "public", None, jsonable_encoder(items), total, generation,
                    limit=limit, offset=offset, search=q,
                )
            # Personalization and engagement stay OUTSIDE the shared cache.
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
