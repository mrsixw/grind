import tomllib

import pytest

from grind.config import (
    _DEFAULT_CONFIG_CONTENT,
    _extract_option_blocks,
    _key_present_in_file,
    load_config,
    misplaced_settings,
    show_config,
    update_config,
    write_default_config,
)


def test_load_config_missing_explicit_path_raises(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_config(str(tmp_path / "nonexistent.toml"))


def test_load_config_no_search_path_hit_returns_empty(tmp_path, monkeypatch):
    from grind import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [tmp_path / "none.toml"])
    assert load_config() == {}


def test_load_config_reads_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('theme = "rainbow"\ncache = true\n')
    result = load_config(str(cfg_file))
    assert result["theme"] == "rainbow"
    assert result["cache"] is True


def test_load_config_invalid_toml_raises(tmp_path):
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("not = [valid toml")
    with pytest.raises(ValueError, match="Config parse error"):
        load_config(str(cfg_file))


def test_write_default_config_creates_file(tmp_path, monkeypatch):
    from grind import xdg

    monkeypatch.setattr(xdg, "get_config_dir", lambda: tmp_path / "grind")
    from grind import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "grind")
    path = write_default_config()
    assert path.exists()
    assert "theme" in path.read_text()


def test_default_config_content_has_all_keys():
    assert "theme" in _DEFAULT_CONFIG_CONTENT
    assert "cache" in _DEFAULT_CONFIG_CONTENT
    assert "seasonal-colours" in _DEFAULT_CONFIG_CONTENT
    assert "no-update-check" in _DEFAULT_CONFIG_CONTENT


def test_show_config_empty():
    output = show_config({})
    assert "no config keys set" in output


def test_show_config_with_values():
    output = show_config({"theme": "rainbow", "cache": True})
    assert "theme" in output
    assert "rainbow" in output


def test_extract_option_blocks_returns_all_keys():
    blocks = _extract_option_blocks(_DEFAULT_CONFIG_CONTENT)
    keys = [k for k, _ in blocks]
    assert "theme" in keys
    assert "cache" in keys
    assert "seasonal-colours" in keys
    assert "emoji" in keys
    assert "progress" in keys
    assert "section-style" in keys
    assert "no-update-check" in keys


def test_extract_option_blocks_block_includes_comment():
    blocks = dict(_extract_option_blocks(_DEFAULT_CONFIG_CONTENT))
    assert "# theme =" in blocks["theme"]
    assert "Equivalent to:" in blocks["theme"]


def test_key_present_in_file_active():
    assert _key_present_in_file("theme", 'theme = "dark"\n')


def test_key_present_in_file_commented():
    assert _key_present_in_file("theme", '# theme = "default"\n')


def test_key_present_in_file_absent():
    assert not _key_present_in_file("theme", "cache = true\n")


def test_update_config_no_file(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [missing])
    result = update_config()
    assert result is False


def test_update_config_already_up_to_date(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_DEFAULT_CONFIG_CONTENT)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    result = update_config()
    assert result is True
    # No backup should be written
    assert not list(tmp_path.glob("*.bak.*"))


def test_update_config_adds_missing_keys(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("# minimal config\n# theme = default\n")
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    result = update_config()
    assert result is True
    updated = cfg_file.read_text()
    # backup written
    assert list(tmp_path.glob("config.toml.bak.*"))
    # missing keys appended
    assert "cache" in updated
    assert "seasonal-colours" in updated
    assert "no-update-check" in updated
    # existing key not duplicated
    assert updated.count("# theme =") == 1


def test_update_config_preserves_modes(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("# minimal config\n")
    cfg_file.chmod(0o600)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    assert (cfg_file.stat().st_mode & 0o777) == 0o600
    backup = next(tmp_path.glob("config.toml.bak.*"))
    assert (backup.stat().st_mode & 0o777) == 0o600


def test_update_config_adds_options_above_the_tables(monkeypatch, tmp_path):
    """An option added below [sources.oss] would belong to that source."""
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    sources = '# my sources\n[sources.oss]\nprovider = "github"\n'
    cfg_file.write_text(f'theme = "dark"\n\n{sources}')
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    updated = cfg_file.read_text()
    # The sources, with the comment above them, are still last and unchanged.
    assert updated.endswith(sources)
    assert updated.index("# section-style =") < updated.index("# my sources")
    # Uncommented where it was put, the option is a top-level setting.
    enabled = tomllib.loads(
        updated.replace('# section-style = "indent"', 'section-style = "gutter"')
    )
    assert enabled["section-style"] == "gutter"
    assert misplaced_settings(enabled) == []


def test_update_config_without_tables_still_appends(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('theme = "dark"')
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    updated = cfg_file.read_text()
    assert updated.startswith('theme = "dark"\n\n# --- Added by config update')
    assert tomllib.loads(updated) == {"theme": "dark"}


def test_misplaced_settings_names_options_inside_a_source():
    cfg = {
        "theme": "dark",
        "sources": {
            "oss": {"provider": "github", "repo": "a/b", "section-style": "gutter"},
            "work": {"provider": "jira", "emoji": False},
        },
    }
    assert misplaced_settings(cfg) == [("oss", "section-style"), ("work", "emoji")]
    assert misplaced_settings({"sources": "oops"}) == []


#: A config an earlier ``config update`` broke: its blocks went in after the
#: source, so TOML read every option in them as a setting of that source.
BROKEN_BY_AN_OLD_UPDATE = """\
debug-summary = true

# ----- Source definitions -----

[sources.oss]
   provider = "github"
   repo = "acme/beans"

# [sources.work]
#   provider = "jira"

# --- Added by config update (grind v0.5.0) on 2026-11-26 12:08:39 ---

# How tables are drawn.
table-style = "outline"

# Print emoji.
emoji = true

# --- Added by config update (grind v0.6.0) on 2026-11-26 13:11:38 ---

# How show lays out its sections.
section-style = "gutter"
"""


def test_update_config_moves_blocks_an_old_update_put_below_a_table(
    monkeypatch, tmp_path
):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(BROKEN_BY_AN_OLD_UPDATE)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    before = tomllib.loads(BROKEN_BY_AN_OLD_UPDATE)
    assert misplaced_settings(before) == [
        ("oss", "table-style"),
        ("oss", "emoji"),
        ("oss", "section-style"),
    ]
    assert update_config() is True
    updated = cfg_file.read_text()
    after = tomllib.loads(updated)
    assert after["section-style"] == "gutter"
    assert after["table-style"] == "outline"
    assert after["emoji"] is True
    assert after["sources"] == {"oss": {"provider": "github", "repo": "acme/beans"}}
    assert misplaced_settings(after) == []
    # The source and the commented one under it are untouched, and last.
    assert updated.endswith(
        '[sources.oss]\n   provider = "github"\n   repo = "acme/beans"\n\n'
        '# [sources.work]\n#   provider = "jira"\n'
    )
    # Above the heading that introduces the tables, not under it.
    heading = updated.index("# ----- Source definitions -----")
    assert updated.index("v0.6.0") < heading
    assert updated[heading:].startswith("# ----- Source definitions -----\n\n[s")
    # The blocks keep their own comments, in order, and the original is kept.
    assert updated.index("v0.5.0") < updated.index("v0.6.0") < updated.index("[s")
    assert updated.index("# How show lays out") < updated.index("section-style =")
    backup = next(tmp_path.glob("config.toml.bak.*"))
    assert backup.read_text() == BROKEN_BY_AN_OLD_UPDATE


def test_update_config_says_what_it_moved(monkeypatch, tmp_path, capsys):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(BROKEN_BY_AN_OLD_UPDATE)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    update_config()
    err = capsys.readouterr().err
    assert "Moved 2 block(s) an earlier update left below your first table" in err
    assert "Now in effect: table-style, emoji, section-style" in err
    assert "still inside" not in err


def test_update_config_leaves_a_block_holding_a_source_key_alone(monkeypatch, tmp_path):
    """A key only a source takes means the user meant that block for it."""
    from grind import config as cfg_mod

    config = (
        '[sources.oss]\nprovider = "github"\n\n'
        "# --- Added by config update (grind v0.5.0) on 2026-11-26 ---\n"
        'repo = "acme/beans"\nemoji = true\n'
    )
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(config)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    after = tomllib.loads(cfg_file.read_text())
    assert after["sources"]["oss"]["repo"] == "acme/beans"
    assert misplaced_settings(after) == [("oss", "emoji")]


def test_a_config_with_its_blocks_in_place_is_left_alone(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    source = '\n[sources.oss]\nprovider = "github"\n'
    cfg_file.write_text(_DEFAULT_CONFIG_CONTENT + source)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    assert not list(tmp_path.glob("*.bak.*"))


def _update(monkeypatch, tmp_path, content):
    """Run config update on *content*; return the file after and its parse."""
    from grind import config as cfg_mod

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(content)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    assert update_config() is True
    updated = cfg_file.read_text()
    return updated, tomllib.loads(updated)


SEPARATOR = "# --- Added by config update (grind v0.5.0) on 2026-11-26 ---\n"
SOURCE = '[sources.oss]\nprovider = "github"\n'
MULTILINE_JQL = 'jql = """\n[urgent]\n"""'


def test_a_block_whose_option_is_already_set_is_not_moved(
    monkeypatch, tmp_path, capsys
):
    """Moving it would set emoji twice, which is not valid TOML."""
    content = f"emoji = false\n\n{SOURCE}\n{SEPARATOR}emoji = true\n"
    _updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is False
    assert parsed["sources"]["oss"]["emoji"] is True
    assert "'emoji' is still inside [sources.oss]" in capsys.readouterr().err


def test_two_blocks_setting_the_same_option_move_only_the_first(monkeypatch, tmp_path):
    work = '[sources.work]\nprovider = "jira"\n'
    content = f"{SOURCE}\n{SEPARATOR}emoji = true\n\n{work}\n{SEPARATOR}emoji = false\n"
    _updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is True
    assert parsed["sources"]["work"]["emoji"] is False


@pytest.mark.parametrize(
    "line",
    ['"repo" = "acme/beans"', 'headers.accept = "json"', MULTILINE_JQL],
    ids=["quoted", "dotted", "multiline"],
)
def test_a_block_holding_anything_but_plain_options_is_not_moved(
    monkeypatch, tmp_path, line
):
    content = f"{SOURCE}\n{SEPARATOR}emoji = true\n{line}\n"
    _updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["sources"]["oss"]["emoji"] is True
    assert "emoji" not in parsed


def test_a_commented_out_source_after_a_block_stays_below_the_tables(
    monkeypatch, tmp_path
):
    commented = '# [sources.work]\n#   provider = "jira"\n'
    content = f"{SOURCE}\n{SEPARATOR}emoji = true\n\n{commented}"
    updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is True
    assert updated.endswith(f"{SOURCE}\n{commented}")


def test_a_second_source_keeps_its_comment_and_its_blank_line(monkeypatch, tmp_path):
    work = '# Work JIRA\n[sources.work]\nprovider = "jira"\n'
    content = f"{SOURCE}\n{SEPARATOR}emoji = true\n\n{work}"
    updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is True
    assert parsed["sources"] == {
        "oss": {"provider": "github"},
        "work": {"provider": "jira"},
    }
    assert updated.endswith(f"{SOURCE}\n{work}")


def test_only_moving_blocks_says_so_and_adds_nothing(monkeypatch, tmp_path, capsys):
    content = f"{_DEFAULT_CONFIG_CONTENT}\n{SOURCE}\n{SEPARATOR}emoji = false\n"
    _updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is False
    err = capsys.readouterr().err
    assert "Moved 1 block(s)" in err
    assert "missing option" not in err


def test_without_a_heading_new_options_stay_under_their_own_section(
    monkeypatch, tmp_path
):
    """Commented options above the table mean the heading is theirs."""
    content = "# ----- Display -----\n\n# emoji = true\n\n" + SOURCE
    updated, _parsed = _update(monkeypatch, tmp_path, content)
    assert updated.startswith("# ----- Display -----\n\n# emoji = true\n\n# --- Added")


def test_a_block_with_every_option_still_commented_out_is_moved(
    monkeypatch, tmp_path, capsys
):
    """How update writes them: uncommenting one later must still work."""
    block = f"{SEPARATOR}\n# Print emoji.\n# emoji = true\n"
    content = f"{_DEFAULT_CONFIG_CONTENT}\n{SOURCE}\n{block}"
    updated, _parsed = _update(monkeypatch, tmp_path, content)
    assert updated.index("# Print emoji.") < updated.index(SOURCE)
    assert "Moved 1 block(s)" in capsys.readouterr().err
    enabled = tomllib.loads(updated.replace(block, block.replace("# emoji", "emoji")))
    assert enabled["emoji"] is True
    # A second run finds nothing to do, and writes no second backup.
    backups = list(tmp_path.glob("*.bak.*"))
    _update(monkeypatch, tmp_path, updated)
    assert list(tmp_path.glob("*.bak.*")) == backups


def test_an_option_with_no_blank_line_before_the_next_table_moves_whole(
    monkeypatch, tmp_path
):
    work = '[sources.work]\nprovider = "jira"\n'
    content = f"{SOURCE}\n{SEPARATOR}# Print emoji.\nemoji = true\n{work}"
    updated, parsed = _update(monkeypatch, tmp_path, content)
    assert parsed["emoji"] is True
    assert updated.index("# Print emoji.") < updated.index(SOURCE)


def test_a_file_that_is_not_valid_toml_is_left_alone(monkeypatch, tmp_path):
    from grind import config as cfg_mod

    content = f"{SOURCE}\n{SEPARATOR}emoji = true\nbroken =\n"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(content)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    update_config()
    # The old block stays where it was, under the source; only the missing
    # options are added, above the table as always.
    assert cfg_file.read_text().endswith(content)
