from panel.luna_capabilities import build_capability_registry


def test_registry_classifies_reads_and_mutations():
    registry = build_capability_registry()

    assert registry.get("search_stories").mutates is False
    assert registry.get("inspect_panel_state").requires_confirmation is False
    assert registry.get("builder_ci_status").mutates is False

    for name in (
        "translate_story",
        "publish_story",
        "reject_and_block_story",
        "move_story_to_review",
        "add_source",
        "rename_source",
        "enable_source",
        "disable_source",
        "delete_source",
        "set_source_review_only",
        "set_newsroom_alarm",
        "builder_prepare",
        "builder_prepare_merge",
    ):
        capability = registry.get(name)
        assert capability.mutates is True, name
        assert capability.requires_confirmation is True, name


def test_registry_has_no_generic_dangerous_capability():
    names = {cap.name for cap in build_capability_registry().all()}
    forbidden = {"shell", "exec", "run_command", "sql", "set_env", "read_secret", "http_proxy"}
    assert not names.intersection(forbidden)


def test_registry_tool_schemas_are_unique_and_include_operator_surface():
    schemas = build_capability_registry().tool_schemas()
    names = [schema["name"] for schema in schemas]

    assert len(names) == len(set(names))
    assert "search_stories" in names
    assert "rename_source" in names
    assert "publish_story" in names
    assert "set_source_review_only" in names
    assert "set_newsroom_alarm" in names
    assert "builder_ci_status" in names


def test_every_mutating_capability_requires_confirmation():
    registry = build_capability_registry()
    assert all(cap.requires_confirmation for cap in registry.all() if cap.mutates)
