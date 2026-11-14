"""The plugin interface: the registry, reference parsing and HttpProvider."""

import pytest
import requests

from grind import providers as providers_mod
from grind.providers import (
    HttpProvider,
    Provider,
    ProviderError,
    available_providers,
    build_sources,
    plugin_dir,
    resolve_ref,
)
from grind.tickets import ListQuery, Ticket, TicketChanges, TicketDraft


class ReadOnly(Provider):
    """The smallest legal plugin: it can only read."""

    name = "readonly"

    def list_tickets(self, query):
        return [Ticket(source=self.source, key="1", title="t", status="open")]

    def get_ticket(self, key, *, comments=False):
        return Ticket(source=self.source, key=key, title="t", status="open")


class Kettle(HttpProvider):
    name = "kettle"
    default_token_env = ("KETTLE_TOKEN",)

    def list_tickets(self, query):
        return []

    def get_ticket(self, key, *, comments=False):
        self.request("GET", f"/tickets/{key}")
        return Ticket(source=self.source, key=key, title="t", status="open")


class FakeEntryPoint:
    def __init__(self, name, target):
        self.name, self.value, self._target = name, f"fake:{name}", target

    def load(self):
        if isinstance(self._target, Exception):
            raise self._target
        return self._target


@pytest.fixture
def plugins(monkeypatch):
    """Install fake entry points, as an installed plugin package would."""

    def install(**targets):
        eps = [FakeEntryPoint(name, target) for name, target in targets.items()]
        monkeypatch.setattr(providers_mod, "entry_points", lambda group: eps)

    install()
    return install


# ── Registry ───────────────────────────────────────────────────────────────


def test_builtin_providers_are_always_available(plugins):
    assert available_providers() == {"github": "built-in", "jira": "built-in"}


def test_entry_point_plugins_are_discovered_and_built(plugins):
    plugins(readonly=ReadOnly)
    assert "readonly" in available_providers()
    sources = build_sources({"sources": {"tea": {"provider": "readonly"}}})
    assert isinstance(sources["tea"], ReadOnly)
    assert sources["tea"].list_tickets(ListQuery())[0].ref == "tea:1"


def test_a_plugin_cannot_shadow_a_builtin(plugins):
    plugins(github=ReadOnly)
    assert available_providers()["github"] == "built-in"
    sources = build_sources({"sources": {"oss": {"provider": "github"}}})
    assert not isinstance(sources["oss"], ReadOnly)


def test_unknown_provider_lists_what_is_available(plugins):
    with pytest.raises(ProviderError, match="Unknown provider 'trello'.*github, jira"):
        build_sources({"sources": {"x": {"provider": "trello"}}})


def test_a_plugin_that_fails_to_import_is_reported_not_raised(plugins):
    plugins(broken=ImportError("no module named beans"))
    with pytest.raises(ProviderError, match="failed to load.*beans"):
        build_sources({"sources": {"x": {"provider": "broken"}}})


def test_a_plugin_that_is_not_a_provider_is_rejected(plugins):
    plugins(notone=dict)
    with pytest.raises(ProviderError, match="not a grind Provider"):
        build_sources({"sources": {"x": {"provider": "notone"}}})


@pytest.mark.parametrize(
    "cfg, message",
    [
        ({"sources": {"x": {}}}, "needs a 'provider' key"),
        ({"sources": {"x": "github"}}, "needs a 'provider' key"),
        ({"sources": "github"}, "table of tables"),
        ({"sources": {"a:b": {"provider": "github"}}}, "must not contain ':'"),
    ],
)
def test_malformed_source_config_is_explained(plugins, cfg, message):
    with pytest.raises(ProviderError, match=message):
        build_sources(cfg)


def test_no_sources_table_means_no_sources(plugins):
    assert build_sources({}) == {}


def test_plugin_dir_lives_under_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert plugin_dir() == tmp_path / "grind" / "plugins"


def test_plugin_dir_is_put_on_sys_path_when_it_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "grind" / "plugins"
    directory.mkdir(parents=True)
    path = []
    monkeypatch.setattr(providers_mod.sys, "path", path)
    available_providers()
    assert path == [str(directory)]


# ── References ─────────────────────────────────────────────────────────────


def _sources(*names):
    return {name: ReadOnly(name, {}) for name in names}


def test_ref_with_a_source_prefix():
    provider, key = resolve_ref("work:PROJ-1", _sources("work", "oss"))
    assert (provider.source, key) == ("work", "PROJ-1")


def test_ref_prefix_is_optional_with_one_source():
    provider, key = resolve_ref("acme/beans#7", _sources("oss"))
    assert (provider.source, key) == ("oss", "acme/beans#7")


def test_ambiguous_ref_names_the_sources():
    with pytest.raises(ProviderError, match="<source>:<key>.*work, oss"):
        resolve_ref("PROJ-1", _sources("work", "oss"))


def test_ref_with_no_sources_at_all():
    with pytest.raises(ProviderError, match="none configured"):
        resolve_ref("PROJ-1", {})


# ── Read-only plugins ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.create_ticket(TicketDraft(title="t")),
        lambda p: p.update_ticket("1", TicketChanges(title="t")),
        lambda p: p.add_comment("1", "hi"),
        lambda p: p.assign("1", None),
        lambda p: p.transition("1", "done"),
        lambda p: p.whoami(),
    ],
)
def test_unimplemented_writes_refuse_politely(call):
    with pytest.raises(ProviderError, match="'readonly' provider.*does not support"):
        call(ReadOnly("tea", {}))


# ── HttpProvider ───────────────────────────────────────────────────────────


@pytest.fixture
def kettle(monkeypatch):
    monkeypatch.setenv("KETTLE_TOKEN", "s3cret")
    return Kettle("k", {"url": "https://kettle.example/api/"})


def test_http_provider_requires_a_url():
    with pytest.raises(ProviderError, match="missing 'url'"):
        Kettle("k", {})


def test_http_provider_sends_a_bearer_token_and_counts_requests(kettle, requests_mock):
    requests_mock.get("https://kettle.example/api/tickets/9", json={})
    kettle.get_ticket("9")
    sent = requests_mock.last_request
    assert sent.headers["Authorization"] == "Bearer s3cret"
    assert sent.headers["User-Agent"].startswith("grind")
    assert kettle.request_count == 1


def test_token_env_in_config_overrides_the_default(monkeypatch, requests_mock):
    monkeypatch.setenv("KETTLE_TOKEN", "default")
    monkeypatch.setenv("OTHER", "chosen")
    kettle = Kettle("k", {"url": "https://kettle.example", "token-env": "OTHER"})
    requests_mock.get("https://kettle.example/tickets/9", json={})
    kettle.get_ticket("9")
    assert requests_mock.last_request.headers["Authorization"] == "Bearer chosen"


def test_missing_token_names_the_variable(monkeypatch):
    monkeypatch.delenv("KETTLE_TOKEN", raising=False)
    kettle = Kettle("k", {"url": "https://kettle.example"})
    with pytest.raises(ProviderError, match="Set KETTLE_TOKEN"):
        kettle.get_ticket("9")


@pytest.mark.parametrize(
    "status, text",
    [
        (401, "token was rejected"),
        (403, "not allowed"),
        (404, "not found"),
        (500, "answered 500: kettle on fire"),
    ],
)
def test_http_errors_become_provider_errors(kettle, requests_mock, status, text):
    requests_mock.get(
        "https://kettle.example/api/tickets/9",
        status_code=status,
        text="kettle on fire",
    )
    with pytest.raises(ProviderError, match=text):
        kettle.get_ticket("9")


def test_connection_failures_become_provider_errors(kettle, requests_mock):
    requests_mock.get(
        "https://kettle.example/api/tickets/9",
        exc=requests.exceptions.ConnectTimeout("too slow"),
    )
    with pytest.raises(ProviderError, match="Could not reach source 'k'.*too slow"):
        kettle.get_ticket("9")


def test_the_token_never_appears_in_an_error(kettle, requests_mock):
    requests_mock.get("https://kettle.example/api/tickets/9", status_code=401)
    with pytest.raises(ProviderError) as excinfo:
        kettle.get_ticket("9")
    assert "s3cret" not in str(excinfo.value)
