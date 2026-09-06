from pathlib import Path


runtime_path = Path("src/runtime_v2.py")
text = runtime_path.read_text(encoding="utf-8")
if "_original_priority_fetch = base.fetch_priority_news_items" not in text:
    text = text.replace(
        "_original_generic_fetch = base._original_fetch_news_items\n",
        "_original_generic_fetch = base._original_fetch_news_items\n_original_priority_fetch = base.fetch_priority_news_items\n",
        1,
    )
start = text.index("def _x_first_fetch_news_items():")
end = text.index("\ndef _fetch_preserved_special_items", start)
new_fetch = '''def _x_first_fetch_news_items():
    """Merge fast X timelines with independent mainstream web coverage.

    Fresh X is preferred for speed, but an X outage must never create a newsroom
    coverage hole. Google-indexed X rows are deliberately excluded from the web
    fallback because fresh/direct X ingestion owns those sources.
    """
    global _x_news_keys
    merged = {}
    try:
        x_items = fetch_builtin_x_news_items()
    except Exception as exc:
        print(f"Newsroom X source error: {exc}", file=sys.stderr)
        x_items = []
    _x_news_keys = {item.key for item in x_items}
    for item in x_items:
        merged.setdefault(item.key, item)

    try:
        web_items = _original_generic_fetch()
    except Exception as exc:
        print(f"Mainstream web source error: {exc}", file=sys.stderr)
        web_items = []
    for item in web_items:
        if str(getattr(item, "source", "")).endswith(" / X"):
            continue
        merged.setdefault(item.key, item)

    print(f"NEWS_SOURCE_MERGE x={len(x_items)} web={len(web_items)} total={len(merged)}")
    return list(merged.values())

'''
text = text[:start] + new_fetch + text[end + 1:]
text = text.replace(
    "    base.fetch_priority_news_items = _no_priority_web_news\n",
    "    base.fetch_priority_news_items = _original_priority_fetch\n",
    1,
)
runtime_path.write_text(text, encoding="utf-8")


sources_path = Path("src/sources.py")
sources = sources_path.read_text(encoding="utf-8")
if "import sys\n" not in sources.split("from dataclasses", 1)[0]:
    sources = sources.replace("import re\n", "import re\nimport sys\n", 1)
sources = sources.replace(
    '''        try:\n            items = _fetch_google_news_query(session, fallback_source, query, lang)\n        except Exception:\n            continue\n''',
    '''        try:\n            items = _fetch_google_news_query(session, fallback_source, query, lang)\n        except Exception as exc:\n            print(f"NEWS_SOURCE_ERROR source={fallback_source!r} error={exc}", file=sys.stderr)\n            continue\n''',
    1,
)
sources = sources.replace(
    '''        try:\n            items = _fetch_google_news_query(session, fallback_source, query, lang, allow_special_source=True)\n        except Exception:\n            continue\n''',
    '''        try:\n            items = _fetch_google_news_query(session, fallback_source, query, lang, allow_special_source=True)\n        except Exception as exc:\n            print(f"NEWS_SOURCE_ERROR source={fallback_source!r} error={exc}", file=sys.stderr)\n            continue\n''',
    1,
)
sources_path.write_text(sources, encoding="utf-8")
