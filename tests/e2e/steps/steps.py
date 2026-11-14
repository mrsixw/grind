"""Step definitions for the end-to-end suite.

Split out of ``conftest.py``, which is for fixtures. Nothing here names the CLI:
steps that need the binary or app name take the ``binary_name`` / ``app_name``
fixtures, so renaming the template's constants retargets these too.
"""

import json
import re
import shlex
from pathlib import Path

from pytest_bdd import given, parsers, then, when

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Matches an ANSI SGR escape, for asserting --no-colour really is colourless.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ── Running it ─────────────────────────────────────────────────────────────


@when(parsers.parse("I run the CLI with `{args}`"), target_fixture="result")
def _run_with_args(run_cli, args):
    return run_cli(shlex.split(args))


@when("I run the CLI with no arguments", target_fixture="result")
def _run_bare(run_cli):
    return run_cli([])


# ── Exit codes and streams ─────────────────────────────────────────────────


@then(parsers.parse("the exit code is {code:d}"))
def _exit_code(result, code):
    assert result.returncode == code, f"stderr was:\n{result.stderr}"


@then("stdout is empty")
def _stdout_empty(result):
    assert result.stdout.strip() == "", f"stdout was:\n{result.stdout}"


@then(parsers.parse('stdout contains "{text}"'))
def _stdout_contains(result, text):
    assert text in result.stdout, f"stdout was:\n{result.stdout}"


@then(parsers.parse('stdout does not contain "{text}"'))
def _stdout_lacks(result, text):
    assert text not in result.stdout, f"{text!r} leaked onto stdout:\n{result.stdout}"


@then(parsers.parse('stderr contains "{text}"'))
def _stderr_contains(result, text):
    assert text in result.stderr, f"stderr was:\n{result.stderr}"


@then("stderr is empty")
def _stderr_empty(result):
    assert result.stderr.strip() == "", f"stderr was:\n{result.stderr}"


@then("stdout carries no ANSI colour")
def _stdout_uncoloured(result):
    found = ANSI.findall(result.stdout)
    assert not found, f"--no-colour still emitted {len(found)} escapes"


@then("stdout is valid JSON", target_fixture="payload")
def _stdout_json(result):
    return json.loads(result.stdout)


@then("stdout reports the version from the VERSION file")
def _version_matches(result):
    expected = (REPO_ROOT / "VERSION").read_text().strip()
    assert result.stdout.strip().endswith(
        expected
    ), f"expected version {expected!r}, stdout was:\n{result.stdout}"


@then("stdout names the binary")
def _names_binary(result, binary_name):
    assert binary_name in result.stdout, f"stdout was:\n{result.stdout}"


# ── The config file on disk ────────────────────────────────────────────────


@given("no config file exists")
def _no_config(sandbox, app_name):
    path = sandbox["config"] / app_name / "config.toml"
    assert not path.exists(), f"{path} existed before the scenario started"


@then("the config file exists in the sandbox")
def _config_written(sandbox, app_name):
    path = sandbox["config"] / app_name / "config.toml"
    assert path.is_file(), f"{path} was not created — is XDG_CONFIG_HOME honoured?"


@given("a config file with a hand-edited marker")
def _seed_config(run_cli, sandbox, app_name):
    """Write a real config, then add a line no template would produce."""
    assert run_cli(["config", "init"]).returncode == 0
    path = sandbox["config"] / app_name / "config.toml"
    path.write_text(path.read_text() + '\n# hand-edited-marker\ntheme = "mono"\n')


@then("the hand-edited marker is still in the config file")
def _marker_survived(sandbox, app_name):
    path = sandbox["config"] / app_name / "config.toml"
    body = path.read_text()
    assert (
        "hand-edited-marker" in body
    ), f"`config init` clobbered a config the user had edited:\n{body}"


@then(parsers.parse("the completion script is evaluable by {shell}"))
def _completion_evaluable(result, shell, binary_name):
    """A completion script must be pure script on stdout, nothing else.

    Anything printed alongside it lands in the user's shell config via
    ``eval "$(... completions bash)"`` and is executed.
    """
    assert result.stdout.strip(), f"{shell} completion produced no stdout"
    assert "Usage:" not in result.stdout, f"usage text leaked into the {shell} script"
    assert "Error" not in result.stdout, f"an error leaked into the {shell} script"


# ── Sources and provider plugins ───────────────────────────────────────────

_TWO_SOURCES = """
[sources.oss]
provider = "github"

[sources.work]
provider = "jira"
url = "https://jira.invalid"
"""

#: A real, read-only provider plugin, written to disk exactly as
#: `pip install --target` would leave it: a module plus dist-info metadata
#: carrying the entry point. It serves one canned ticket and counts a
#: "request" each time it is actually asked, so the cache scenario can tell a
#: cache hit from a fetch.
_PLUGIN_MODULE = """
from grind.providers import Provider
from grind.tickets import Ticket


class DecafProvider(Provider):
    name = "decaf"

    def _ticket(self):
        return Ticket(
            source=self.source,
            key="DECAF-1",
            title="Refill the decaf jar",
            status="open",
            updated="2026-11-01T09:00:00Z",
        )

    def list_tickets(self, query):
        self.request_count += 1
        return [self._ticket()]

    def get_ticket(self, key, *, comments=False):
        self.request_count += 1
        return self._ticket()
"""


@given("a config file with GitHub and JIRA sources")
def _two_sources(sandbox, app_name):
    path = sandbox["config"] / app_name / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TWO_SOURCES)


@given(parsers.parse('a config file with a "{provider}" source'))
def _plugin_source(sandbox, app_name, provider):
    path = sandbox["config"] / app_name / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[sources.pot]\nprovider = "{provider}"\n')


def _plugin_dir(sandbox, app_name) -> Path:
    # cli_env sets no XDG_DATA_HOME, so the binary falls back to ~/.local/share.
    return sandbox["home"] / ".local" / "share" / app_name / "plugins"


@given(parsers.parse('a provider plugin named "{name}" is installed'))
def _install_plugin(sandbox, app_name, name):
    plugins = _plugin_dir(sandbox, app_name)
    dist_info = plugins / f"{app_name}_{name}-0.1.0.dist-info"
    dist_info.mkdir(parents=True)
    (plugins / f"{app_name}_{name}.py").write_text(_PLUGIN_MODULE)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {app_name}-{name}\nVersion: 0.1.0\n"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{app_name}.providers]\n{name} = {app_name}_{name}:DecafProvider\n"
    )


@then("stdout names the plugin directory in the sandbox")
def _plugin_dir_reported(result, sandbox, app_name):
    assert result.stdout.strip() == str(_plugin_dir(sandbox, app_name))


@then(parsers.parse('the JSON lists the ticket "{ref}"'))
def _json_lists(payload, ref):
    assert [ticket["ref"] for ticket in payload] == [ref]
