import re

import pytest
from click.testing import CliRunner
from freezegun import freeze_time

from grind import cli as cli_mod
from grind import ui as ui_mod
from grind.cli import main
from grind.tickets import Ticket
from tests.pantry import pantry_fixture  # noqa: F401  (the pantry fixture)


def _invoke(*args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, list(args), **kwargs)


def test_version():
    result = _invoke("--version")
    assert result.exit_code == 0
    # Assert the shape, not a substring of one particular version. The old
    # check looked for "0.", which matched 1.0.2 by luck and not 1.1.0; and
    # for "grind", which never matched, since CliRunner takes the prog name
    # from the callback function (`main`) rather than the console script.
    assert re.search(r"\bversion \d+\.\d+\.\d+", result.output), result.output


def test_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "--theme" in result.output
    assert "list" in result.output
    assert "create" in result.output
    assert "sources" in result.output
    assert "completions" in result.output
    assert "update" in result.output
    assert "config" in result.output


SOURCE_TOML = '\n[sources.oss]\nprovider = "pantry"\n'

ISSUE = Ticket(
    source="oss",
    key="acme/beans#7",
    title="Descale the espresso machine",
    status="open",
    assignee="ada",
    updated="2026-11-01T09:00:00Z",
)


@pytest.fixture(autouse=True)
def stocked_pantry(pantry, requests_mock):
    """One open ticket in the pantry plugin, for tests that need real output.

    requests_mock stays on so no test can reach the network by accident.
    """
    pantry.add(ISSUE)
    return pantry


def _config(tmp_path, body=""):
    """Write a config holding *body* plus one GitHub source; return its path."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(body + SOURCE_TOML)
    return str(cfg)


def test_bare_invocation_lists_tickets(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--no-colour", "--config", _config(tmp_path))
    assert result.exit_code == 0, result.output
    assert "oss:acme/beans#7" in result.stdout
    assert "Descale the espresso machine" in result.stdout


def test_bare_invocation_without_sources_points_at_config_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = _invoke("--no-colour", "--no-update-check")
    assert result.exit_code == 1
    assert "No sources configured" in result.stderr
    assert "config init" in result.stderr
    assert result.stdout == ""


def test_completions_bash():
    result = _invoke("completions", "bash")
    assert result.exit_code == 0
    assert "_GRIND_COMPLETE" in result.output


def test_completions_zsh():
    result = _invoke("completions", "zsh")
    assert result.exit_code == 0


def test_completions_fish():
    result = _invoke("completions", "fish")
    assert result.exit_code == 0


def test_completions_rejects_unknown_shell():
    result = _invoke("completions", "powershell")
    assert result.exit_code != 0


def test_completions_singular_name_is_gone():
    """The old spelling was removed outright — this is a template, not a product."""
    result = _invoke("completion", "bash")
    assert result.exit_code != 0


def test_shell_enum_members_are_their_lowercase_names():
    assert [s.value for s in cli_mod.Shell] == ["bash", "zsh", "fish"]
    assert cli_mod.Shell.BASH == "bash"


def test_config_init(tmp_path, monkeypatch):
    from grind import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "grind")
    result = _invoke("config", "init")
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_config_show(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("config", "show")
    assert result.exit_code == 0
    assert "Config file" in result.output


def test_theme_rainbow(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--theme", "rainbow", "sources")
    assert result.exit_code == 0


def test_no_update_check_skips_update(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-update-check", "--no-colour", "sources")
    assert called["n"] == 0


def test_update_check_runs_by_default(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-colour", "sources")
    assert called["n"] == 1


def test_update_check_not_run_for_config_show(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("config", "show")
    assert called["n"] == 0


def test_invalid_config_exits_with_error(tmp_path):
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("not = [valid toml")
    result = _invoke("--config", str(bad_cfg), "sources")
    assert result.exit_code == 1


def test_missing_explicit_config_exits_with_error(tmp_path):
    result = _invoke("--config", str(tmp_path / "nope.toml"), "sources")
    assert result.exit_code == 1
    assert "not found" in result.output


def test_invalid_cache_ttl_exits_with_error():
    result = _invoke("--cache-ttl", "banana", "sources")
    assert result.exit_code == 1


def test_settings_resolution_config_beats_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    cfg = tmp_path / "cfg.toml"
    cfg.write_text('theme = "rainbow"\n"cache-ttl" = "5m"\n')
    result = _invoke("--config", str(cfg), "--no-colour", "sources")
    assert result.exit_code == 0


def test_config_update_no_config_exits_1(tmp_path, monkeypatch):
    from grind import config as cfg_mod

    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [missing])
    result = _invoke("config", "update")
    assert result.exit_code == 1


def test_config_update_up_to_date_exits_0(tmp_path, monkeypatch):
    from grind import config as cfg_mod
    from grind.config import _DEFAULT_CONFIG_CONTENT

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_DEFAULT_CONFIG_CONTENT)
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [cfg_file])
    result = _invoke("config", "update")
    assert result.exit_code == 0


# ── update ──────────────────────────────────────────────────────────────────


def _stub_update(monkeypatch, status, current="1.0.0", detail="2.0.0"):
    monkeypatch.setattr(
        cli_mod, "perform_update", lambda _path: (status, current, detail)
    )
    monkeypatch.setattr(cli_mod, "_current_executable_path", lambda: "/tmp/grind")


def test_update_reports_success(monkeypatch):
    _stub_update(monkeypatch, cli_mod.UpdateStatus.UPDATED)
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 0
    assert "updated to v2.0.0" in result.output
    assert "install.sh" in result.output


def test_update_reports_already_current(monkeypatch):
    _stub_update(monkeypatch, cli_mod.UpdateStatus.UP_TO_DATE)
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 0
    assert "Already up to date, v1.0.0" in result.output


def test_update_unreachable_github_fails_cleanly(monkeypatch):
    _stub_update(monkeypatch, cli_mod.UpdateStatus.UNKNOWN, detail=None)
    result = _invoke("--no-colour", "update")
    assert result.exit_code != 0
    assert "Could not reach GitHub" in result.output
    assert "Traceback" not in result.output


def test_update_error_surfaces_detail(monkeypatch):
    _stub_update(monkeypatch, cli_mod.UpdateStatus.ERROR, detail="Permission denied")
    result = _invoke("--no-colour", "update")
    assert result.exit_code != 0
    assert "Permission denied" in result.output
    assert "Traceback" not in result.output


def test_update_does_not_also_print_the_update_notice(monkeypatch):
    """The trailing 'a new version exists' notice would be noise here."""
    _stub_update(monkeypatch, cli_mod.UpdateStatus.UP_TO_DATE)
    monkeypatch.setattr(
        cli_mod, "check_for_update", lambda **_kw: "🍟 A fresh order is ready!"
    )
    result = _invoke("--no-colour", "update")
    assert "fresh order" not in result.output


def test_current_executable_path_is_absolute(monkeypatch):
    monkeypatch.setattr(cli_mod.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_mod.sys, "argv", ["./grind"])
    assert cli_mod._current_executable_path().startswith("/")


def test_completions_survives_a_broken_config(tmp_path):
    """The shell runs this on every tab-press; a bad config must not leak in."""
    bad = tmp_path / "config.toml"
    bad.write_text('cache-ttl = "not-a-duration"\n')
    result = _invoke("--config", str(bad), "completions", "bash")
    assert result.exit_code == 0
    assert "_GRIND_COMPLETE" in result.stdout
    assert "Invalid TTL" not in result.output


def test_update_survives_a_broken_config(tmp_path, monkeypatch):
    """A config bad enough to break the CLI must not block updating past it."""
    _stub_update(monkeypatch, cli_mod.UpdateStatus.UP_TO_DATE)
    bad = tmp_path / "config.toml"
    bad.write_text('cache-ttl = "not-a-duration"\n')
    result = _invoke("--config", str(bad), "update")
    assert result.exit_code == 0
    assert "Already up to date" in result.output


def test_config_update_still_resolves_config(tmp_path):
    """'config update' must not be mistaken for the top-level 'update'."""
    bad = tmp_path / "config.toml"
    bad.write_text('cache-ttl = "not-a-duration"\n')
    result = _invoke("--config", str(bad), "config", "update")
    assert result.exit_code != 0
    assert "Invalid TTL" in result.output


def test_seasonal_calendar_off_is_accepted():
    # Regression: "off" was handled by apply_seasonal_colour but missing from
    # CALENDAR_NAMES, so click.Choice rejected it before it ever got there.
    result = _invoke("--no-update-check", "--seasonal-calendar", "off", "sources")
    assert result.exit_code == 0
    assert "PROVIDER" in result.output


def test_seasonal_calendar_rainbow_is_accepted():
    result = _invoke("--no-update-check", "--seasonal-calendar", "rainbow", "sources")
    assert result.exit_code == 0
    assert "PROVIDER" in result.output


def test_seasonal_calendar_rejects_unknown_values():
    result = _invoke("--seasonal-calendar", "klingon", "sources")
    assert result.exit_code != 0


# ── Release summary in the update notice ───────────────────────────────────


def _stub_update_check(monkeypatch, calls):
    def fake(show_summary=False):
        calls.append(show_summary)
        notice = "🍟 A fresh order is ready!"
        return notice + "\n  📋 - Did a thing" if show_summary else notice

    monkeypatch.setattr(cli_mod, "check_for_update", fake)


def test_update_summary_defaults_to_off(monkeypatch):
    calls = []
    _stub_update_check(monkeypatch, calls)
    result = _invoke("sources")
    assert result.exit_code == 0
    assert calls == [False]
    assert "📋" not in result.output


def test_update_summary_flag_shows_the_highlights(monkeypatch):
    calls = []
    _stub_update_check(monkeypatch, calls)
    result = _invoke("--update-summary", "sources")
    assert result.exit_code == 0
    assert calls == [True]
    assert "📋 - Did a thing" in result.output


def test_update_summary_reads_from_the_config_file(monkeypatch, tmp_path):
    calls = []
    _stub_update_check(monkeypatch, calls)
    cfg = tmp_path / "config.toml"
    cfg.write_text("update-summary = true\n")
    result = _invoke("--config", str(cfg), "sources")
    assert result.exit_code == 0
    assert calls == [True]


def test_no_update_summary_flag_beats_the_config_file(monkeypatch, tmp_path):
    calls = []
    _stub_update_check(monkeypatch, calls)
    cfg = tmp_path / "config.toml"
    cfg.write_text("update-summary = true\n")
    result = _invoke("--config", str(cfg), "--no-update-summary", "sources")
    assert result.exit_code == 0
    assert calls == [False]


def test_update_summary_is_skipped_when_update_check_is_off(monkeypatch):
    calls = []
    _stub_update_check(monkeypatch, calls)
    result = _invoke("--no-update-check", "--update-summary", "sources")
    assert result.exit_code == 0
    assert calls == []


# ── Easter eggs ────────────────────────────────────────────────────────────


@pytest.fixture
def quiet_updates(monkeypatch):
    """Silence the update notice so easter-egg output stands alone."""
    monkeypatch.setattr(cli_mod, "check_for_update", lambda show_summary=False: None)


@pytest.fixture
def gift_state(tmp_path, monkeypatch):
    """Point the once-a-year gift state at a temp dir."""
    monkeypatch.setattr(ui_mod, "get_state_dir", lambda: tmp_path)
    return tmp_path


def test_brew_flag_prints_a_recipe(quiet_updates):
    result = _invoke("--brew", "sources")
    assert result.exit_code == 0
    assert "Secret Coffee Recipe" in result.output


def test_cake_flag_prints_a_recipe(quiet_updates):
    result = _invoke("--cake", "sources")
    assert result.exit_code == 0
    assert "Secret Cake Recipe" in result.output


def test_easter_egg_flags_are_hidden_from_help():
    result = _invoke("--help")
    assert "--brew" not in result.output
    assert "--cake" not in result.output


def test_no_easter_eggs_by_default(quiet_updates):
    result = _invoke("sources")
    assert "Secret Coffee Recipe" not in result.output
    assert "Secret Cake Recipe" not in result.output


@freeze_time("2026-12-25")
def test_christmas_serves_a_brew_once_a_year(quiet_updates, gift_state):
    first = _invoke("sources")
    assert "Merry Christmas" in first.output
    second = _invoke("sources")
    assert "Merry Christmas" not in second.output


@freeze_time("2026-01-08")
def test_birthday_serves_cake_once_a_year(quiet_updates, gift_state):
    first = _invoke("sources")
    assert "birthday" in first.output
    second = _invoke("sources")
    assert "birthday" not in second.output


@freeze_time("2026-12-25")
def test_no_colour_suppresses_the_unbidden_gift(quiet_updates, gift_state):
    # Decoration nobody asked for should not appear in plain output.
    result = _invoke("--no-colour", "sources")
    assert "Merry Christmas" not in result.output


@freeze_time("2026-12-25")
def test_explicit_flag_still_works_with_no_colour(quiet_updates, gift_state):
    # --brew was asked for, so --no-colour only strips the styling.
    result = _invoke("--no-colour", "--brew", "sources")
    assert "Secret Coffee Recipe" in result.output


def test_easter_eggs_go_to_stderr(quiet_updates):
    runner = CliRunner()
    result = runner.invoke(main, ["--brew", "sources"], catch_exceptions=False)
    assert "Secret Coffee Recipe" in result.output
    assert "Secret Coffee Recipe" not in result.stdout


# ── Debug summary ──────────────────────────────────────────────────────────


def test_no_debug_summary_by_default(quiet_updates):
    result = _invoke("sources")
    assert "Debug summary" not in result.output


def test_debug_summary_reports_timing_and_work(quiet_updates):
    result = _invoke("--debug-summary", "sources")
    assert result.exit_code == 0
    assert "🐛 Debug summary" in result.output
    assert "Total elapsed:" in result.output
    assert "Items processed: 0" in result.output


def test_debug_summary_reports_cache_state(quiet_updates):
    off = _invoke("--debug-summary", "sources")
    assert re.search(r"Cache:\s+disabled", off.output)
    on = _invoke("--debug-summary", "--cache", "--cache-ttl", "2h", "sources")
    assert re.search(r"Cache:\s+enabled, ttl 7200s", on.output)


def test_debug_summary_includes_command_supplied_rows(quiet_updates, tmp_path):
    result = _invoke("--debug-summary", "--config", _config(tmp_path), "list")
    assert re.search(r"Requests to oss:\s+1", result.output)
    assert "Items processed: 1" in result.output


def test_debug_summary_rows_are_aligned(quiet_updates):
    result = _invoke("--debug-summary", "sources")
    # Labels differ in width, so it is the value column that must line up.
    # Only the summary block counts — sources prints its own tables.
    lines = result.output.splitlines()
    body = lines[next(i for i, ln in enumerate(lines) if "Debug summary" in ln) + 1 :]
    matches = [re.match(r"^ {2}(.+?):\s+(\S)", ln) for ln in body]
    value_columns = {m.start(2) for m in matches if m}
    assert len(value_columns) == 1, result.output


def test_debug_summary_reads_from_the_config_file(quiet_updates, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("debug-summary = true\n")
    result = _invoke("--config", str(cfg), "sources")
    assert "🐛 Debug summary" in result.output


def test_no_debug_summary_flag_beats_the_config_file(quiet_updates, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("debug-summary = true\n")
    result = _invoke("--config", str(cfg), "--no-debug-summary", "sources")
    assert "Debug summary" not in result.output


def test_debug_summary_goes_to_stderr(quiet_updates):
    runner = CliRunner()
    result = runner.invoke(main, ["--debug-summary", "sources"])
    assert "Debug summary" in result.output
    assert "Debug summary" not in result.stdout


# ── Environment-variable presence semantics ────────────────────────────────


@pytest.mark.parametrize("value", ["1", "0", "false", "off", "banana"])
def test_no_update_check_env_any_non_empty_value_suppresses(
    monkeypatch, quiet_updates, value
):
    # Presence is the signal, per no-color.org: the value is never parsed.
    calls = []
    monkeypatch.setattr(
        cli_mod, "check_for_update", lambda show_summary=False: calls.append(1)
    )
    monkeypatch.setenv("GRIND_NO_UPDATE_CHECK", value)
    result = _invoke("sources")
    assert result.exit_code == 0, result.output
    assert calls == [], f"{value!r} should suppress the update check"


def test_no_update_check_env_empty_leaves_check_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "check_for_update", lambda show_summary=False: calls.append(1)
    )
    monkeypatch.setenv("GRIND_NO_UPDATE_CHECK", "")
    result = _invoke("sources")
    assert result.exit_code == 0
    assert calls == [1], "an empty value must not suppress the update check"


@pytest.mark.parametrize("value", ["1", "0", "false", "banana"])
def test_no_colour_env_any_non_empty_value_disables_colour(
    monkeypatch, quiet_updates, value, tmp_path
):
    monkeypatch.setenv("GRIND_NO_COLOUR", value)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", _config(tmp_path), "--seasonal-calendar", "rainbow", "list"],
        color=True,
    )
    assert result.exit_code == 0, result.output
    assert "\033[" not in result.output, f"{value!r} should disable colour"


def test_no_colour_env_empty_leaves_colour_enabled(
    monkeypatch, quiet_updates, tmp_path
):
    monkeypatch.setenv("GRIND_NO_COLOUR", "")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", _config(tmp_path), "--seasonal-calendar", "rainbow", "list"],
        color=True,
    )
    assert result.exit_code == 0
    assert "\033[" in result.output


@pytest.mark.parametrize("var", ["GRIND_NO_UPDATE_CHECK", "GRIND_NO_COLOUR"])
def test_unparsable_env_value_never_aborts_the_run(monkeypatch, quiet_updates, var):
    # The regression: Click's envvar= on a flag rejected unrecognised values,
    # so a typo in a shell profile broke every invocation.
    monkeypatch.setenv(var, "banana")
    result = _invoke("sources")
    assert result.exit_code == 0, result.output
    assert "not a valid boolean" not in result.output


# ── no-colour config key ───────────────────────────────────────────────────


def _list_output(tmp_path, body="", extra_args=()):
    """List tickets with colour forced on, returning the output."""
    cfg = _config(tmp_path, body)
    runner = CliRunner()
    return runner.invoke(
        main,
        [
            "--config",
            str(cfg),
            "--seasonal-calendar",
            "rainbow",
            *extra_args,
            "list",
        ],
        color=True,
    )


def test_colour_on_by_default(tmp_path, quiet_updates, monkeypatch):
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    result = _list_output(tmp_path)
    assert result.exit_code == 0, result.output
    assert "\033[" in result.output


def test_no_colour_config_key_disables_colour(tmp_path, quiet_updates, monkeypatch):
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    result = _list_output(tmp_path, "no-colour = true\n")
    assert result.exit_code == 0, result.output
    assert "\033[" not in result.output


def test_no_colour_config_key_false_leaves_colour_on(
    tmp_path, quiet_updates, monkeypatch
):
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    result = _list_output(tmp_path, "no-colour = false\n")
    assert "\033[" in result.output


def test_no_colour_flag_beats_a_false_config_key(tmp_path, quiet_updates, monkeypatch):
    # Any one of the three switching colour off is enough; none can switch it
    # back on.
    monkeypatch.delenv("GRIND_NO_COLOUR", raising=False)
    result = _list_output(tmp_path, "no-colour = false\n", ["--no-colour"])
    assert "\033[" not in result.output


def test_no_colour_env_beats_a_false_config_key(tmp_path, quiet_updates, monkeypatch):
    monkeypatch.setenv("GRIND_NO_COLOUR", "1")
    result = _list_output(tmp_path, "no-colour = false\n")
    assert "\033[" not in result.output
