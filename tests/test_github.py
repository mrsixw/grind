"""The GitHub provider, with HTTP faked at the requests boundary."""

from urllib.parse import parse_qs, urlsplit

import pytest

from grind.github import GitHubProvider
from grind.providers import ProviderError
from grind.tickets import ME, ListQuery, TicketChanges, TicketDraft

API = "https://api.github.com"


def issue(number=7, **overrides):
    return {
        "number": number,
        "title": "Descale the espresso machine",
        "state": "open",
        "repository_url": f"{API}/repos/acme/beans",
        "html_url": f"https://github.com/acme/beans/issues/{number}",
        "created_at": "2026-10-01T09:00:00Z",
        "updated_at": "2026-11-01T09:00:00Z",
        "user": {"login": "grace"},
        "assignees": [{"login": "ada"}],
        "labels": [{"name": "chore"}],
        "body": "It is furring up.",
        **overrides,
    }


@pytest.fixture
def gh(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    return GitHubProvider("oss", {"provider": "github", "repo": "acme/beans"})


@pytest.fixture
def gh_norepo(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    return GitHubProvider("oss", {"provider": "github"})


def test_token_falls_back_from_gh_token_to_github_token(monkeypatch, requests_mock):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "second")
    requests_mock.get(f"{API}/user", json={"login": "ada"})
    assert GitHubProvider("oss", {}).whoami() == "ada"
    assert requests_mock.last_request.headers["Authorization"] == "Bearer second"


def test_enterprise_url_is_honoured(monkeypatch, requests_mock):
    monkeypatch.setenv("GH_TOKEN", "tok")
    requests_mock.get("https://ghe.example/api/v3/user", json={"login": "ada"})
    provider = GitHubProvider("oss", {"url": "https://ghe.example/api/v3"})
    assert provider.whoami() == "ada"


# ── list ───────────────────────────────────────────────────────────────────


def test_list_builds_a_search_and_maps_the_tickets(gh, requests_mock):
    requests_mock.get(f"{API}/search/issues", json={"items": [issue()]})
    (ticket,) = gh.list_tickets(ListQuery(text="espresso"))
    assert requests_mock.last_request.qs["q"] == [
        "is:issue repo:acme/beans assignee:@me state:open espresso"
    ]
    assert ticket.ref == "oss:acme/beans#7"
    assert ticket.is_open and ticket.status == "open"
    assert ticket.assignee == "ada"
    assert ticket.reporter == "grace"
    assert ticket.labels == ("chore",)
    assert ticket.url == "https://github.com/acme/beans/issues/7"


def test_list_all_states_for_anyone_in_another_repo(gh, requests_mock):
    requests_mock.get(f"{API}/search/issues", json={"items": []})
    gh.list_tickets(ListQuery(mine=False, state="all", containers=("acme/milk",)))
    assert requests_mock.last_request.qs["q"] == ["is:issue repo:acme/milk"]


def scoped(monkeypatch, **config):
    monkeypatch.setenv("GH_TOKEN", "tok")
    return GitHubProvider("oss", {"provider": "github", **config})


def sent_query(requests_mock):
    """The search query as sent, unlowered (requests-mock lowercases ``qs``)."""
    return parse_qs(urlsplit(requests_mock.last_request.url).query)["q"][0]


@pytest.mark.parametrize(
    ("config", "containers", "expected"),
    [
        ({"org": "mrsixw"}, (), "org:mrsixw"),
        (
            {"repos": ["mrsixw/grind", "mrsixw/breakfast"]},
            (),
            "repo:mrsixw/grind repo:mrsixw/breakfast",
        ),
        ({"repos": "mrsixw/grind"}, (), "repo:mrsixw/grind"),
        # Most specific wins, and replaces everything below it.
        ({"org": "mrsixw", "repo": "mrsixw/grind"}, (), "repo:mrsixw/grind"),
        ({"repo": "acme/beans", "repos": ["acme/milk"]}, (), "repo:acme/milk"),
        ({"org": "mrsixw", "repos": ["mrsixw/grind"]}, ("acme",), "org:acme"),
        (
            {"org": "mrsixw"},
            ("acme/milk", "acme/beans"),
            "repo:acme/milk repo:acme/beans",
        ),
        ({}, ("acme", "mrsixw/grind"), "org:acme repo:mrsixw/grind"),
    ],
)
def test_list_scope_precedence(
    monkeypatch, requests_mock, config, containers, expected
):
    requests_mock.get(f"{API}/search/issues", json={"items": []})
    scoped(monkeypatch, **config).list_tickets(
        ListQuery(mine=False, containers=containers)
    )
    assert sent_query(requests_mock) == f"is:issue {expected} state:open"


def test_list_everyone_across_an_org(monkeypatch, requests_mock):
    requests_mock.get(f"{API}/search/issues", json={"items": [issue()]})
    (ticket,) = scoped(monkeypatch, org="mrsixw").list_tickets(ListQuery(mine=False))
    assert ticket.ref == "oss:acme/beans#7"
    assert requests_mock.call_count == 1


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"repo": "acme"}, "'acme' is not a repository"),
        ({"repos": ["acme/milk", "acme"]}, "'acme' is not a repository"),
        ({"org": "acme/milk"}, "should be an owner only"),
    ],
)
def test_a_malformed_configured_scope_fails_instead_of_widening(
    monkeypatch, requests_mock, config, message
):
    with pytest.raises(ProviderError, match=message):
        scoped(monkeypatch, **config).list_tickets(ListQuery())
    assert requests_mock.call_count == 0


def test_a_repos_value_that_is_not_a_list_of_names_is_explained(monkeypatch):
    with pytest.raises(ProviderError, match="'repos' must be a list of names"):
        scoped(monkeypatch, repos=["ok/repo", 3]).list_tickets(ListQuery())


def test_list_mine_needs_no_repo(gh_norepo, requests_mock):
    requests_mock.get(f"{API}/search/issues", json={"items": []})
    gh_norepo.list_tickets(ListQuery())
    assert requests_mock.last_request.qs["q"] == ["is:issue assignee:@me state:open"]


def test_list_everyone_without_a_repo_is_refused_before_any_request(
    gh_norepo, requests_mock
):
    with pytest.raises(ProviderError, match="needs a repository"):
        gh_norepo.list_tickets(ListQuery(mine=False))
    assert requests_mock.call_count == 0


def test_list_pages_until_the_limit(gh, requests_mock):
    requests_mock.get(
        f"{API}/search/issues",
        [
            {"json": {"items": [issue(n) for n in range(100)]}},
            {"json": {"items": [issue(n) for n in range(100, 150)]}},
        ],
    )
    tickets = gh.list_tickets(ListQuery(limit=150))
    assert len(tickets) == 150
    assert [r.qs["page"] for r in requests_mock.request_history] == [["1"], ["2"]]
    assert requests_mock.request_history[1].qs["per_page"] == ["50"]


def test_list_stops_on_a_short_page(gh, requests_mock):
    requests_mock.get(f"{API}/search/issues", json={"items": [issue()]})
    assert len(gh.list_tickets(ListQuery(limit=500))) == 1
    assert requests_mock.call_count == 1


def test_closed_as_not_planned_is_reported_as_such(gh, requests_mock):
    closed = issue(state="closed", state_reason="not_planned")
    requests_mock.get(f"{API}/search/issues", json={"items": [closed]})
    (ticket,) = gh.list_tickets(ListQuery(state="closed"))
    assert ticket.status == "not planned"
    assert not ticket.is_open


# ── get ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["acme/beans#7", "#7", "7"])
def test_get_accepts_full_and_short_keys(gh, requests_mock, key):
    requests_mock.get(f"{API}/repos/acme/beans/issues/7", json=issue())
    ticket = gh.get_ticket(key)
    assert ticket.key == "acme/beans#7"
    assert ticket.body == "It is furring up."
    assert ticket.comments == ()


def test_get_short_key_without_a_default_repo_is_explained(gh_norepo):
    with pytest.raises(ProviderError, match="owner/repo#123"):
        gh_norepo.get_ticket("#7")


def test_get_rejects_garbage_keys(gh):
    with pytest.raises(ProviderError, match="not a GitHub issue"):
        gh.get_ticket("PROJ-12")


def test_get_with_comments(gh, requests_mock):
    requests_mock.get(f"{API}/repos/acme/beans/issues/7", json=issue())
    requests_mock.get(
        f"{API}/repos/acme/beans/issues/7/comments",
        json=[
            {
                "user": {"login": "grace"},
                "body": "On it.",
                "created_at": "2026-11-02T10:00:00Z",
            }
        ],
    )
    (comment,) = gh.get_ticket("#7", comments=True).comments
    assert (comment.author, comment.body) == ("grace", "On it.")


def test_get_refuses_pull_requests(gh, requests_mock):
    requests_mock.get(
        f"{API}/repos/acme/beans/issues/7", json=issue(pull_request={"url": "x"})
    )
    with pytest.raises(ProviderError, match="pull request"):
        gh.get_ticket("#7")


def test_api_error_message_is_surfaced(gh, requests_mock):
    requests_mock.get(
        f"{API}/repos/acme/beans/issues/7",
        status_code=422,
        json={"message": "Validation Failed"},
    )
    with pytest.raises(ProviderError, match="422: Validation Failed"):
        gh.get_ticket("#7")


# ── writes ─────────────────────────────────────────────────────────────────


def test_create_posts_the_draft(gh, requests_mock):
    requests_mock.get(f"{API}/user", json={"login": "ada"})
    requests_mock.post(f"{API}/repos/acme/beans/issues", json=issue(8))
    ticket = gh.create_ticket(
        TicketDraft(title="Buy filters", body="V60", labels=("shop",), assignee=ME)
    )
    assert requests_mock.last_request.json() == {
        "title": "Buy filters",
        "body": "V60",
        "labels": ["shop"],
        "assignees": ["ada"],
    }
    assert ticket.key == "acme/beans#8"


def test_create_in_another_repo(gh, requests_mock):
    requests_mock.post(f"{API}/repos/acme/milk/issues", json=issue(1))
    gh.create_ticket(TicketDraft(title="t", container="acme/milk"))
    assert requests_mock.last_request.json() == {"title": "t", "body": ""}


def test_create_uses_the_only_repo_in_a_group(monkeypatch, requests_mock):
    requests_mock.post(f"{API}/repos/acme/milk/issues", json=issue(1))
    scoped(monkeypatch, repos=["acme/milk"]).create_ticket(TicketDraft(title="t"))
    assert requests_mock.called


def test_create_in_a_group_of_repos_asks_which_and_lists_them(monkeypatch):
    provider = scoped(monkeypatch, repos=["acme/milk", "acme/beans"])
    with pytest.raises(ProviderError, match="Choose from: acme/milk, acme/beans"):
        provider.create_ticket(TicketDraft(title="t"))


@pytest.mark.parametrize("config", [{"org": "mrsixw"}, {}])
def test_create_needs_a_whole_repo_not_an_org(monkeypatch, requests_mock, config):
    provider = scoped(monkeypatch, **config)
    with pytest.raises(ProviderError, match="Pass --in owner/repo"):
        provider.create_ticket(TicketDraft(title="t", container="mrsixw"))
    assert requests_mock.call_count == 0


def test_create_without_a_repo_is_explained(gh_norepo):
    with pytest.raises(ProviderError, match="Which repository"):
        gh_norepo.create_ticket(TicketDraft(title="t"))


def test_create_refuses_a_type(gh):
    with pytest.raises(ProviderError, match="--label"):
        gh.create_ticket(TicketDraft(title="t", type="Bug"))


def test_update_title_and_body_only_sends_those(gh, requests_mock):
    requests_mock.patch(f"{API}/repos/acme/beans/issues/7", json=issue())
    gh.update_ticket("#7", TicketChanges(title="New", body=""))
    assert requests_mock.last_request.json() == {"title": "New", "body": ""}
    assert requests_mock.call_count == 1


def test_update_labels_merges_with_the_existing_set(gh, requests_mock):
    current = issue(labels=[{"name": "chore"}, {"name": "stale"}])
    requests_mock.get(f"{API}/repos/acme/beans/issues/7", json=current)
    requests_mock.patch(f"{API}/repos/acme/beans/issues/7", json=issue())
    gh.update_ticket(
        "#7", TicketChanges(add_labels=("urgent", "chore"), remove_labels=("stale",))
    )
    assert requests_mock.last_request.json() == {"labels": ["chore", "urgent"]}


def test_comment(gh, requests_mock):
    requests_mock.post(
        f"{API}/repos/acme/beans/issues/7/comments",
        json={"user": {"login": "ada"}, "body": "Done.", "created_at": "2026-11-03"},
    )
    comment = gh.add_comment("#7", "Done.")
    assert requests_mock.last_request.json() == {"body": "Done."}
    assert comment.author == "ada"


def test_assign_to_me_someone_and_nobody(gh, requests_mock):
    requests_mock.get(f"{API}/user", json={"login": "ada"})
    requests_mock.patch(f"{API}/repos/acme/beans/issues/7", json=issue())
    gh.assign("#7", ME)
    assert requests_mock.last_request.json() == {"assignees": ["ada"]}
    gh.assign("#7", "grace")
    assert requests_mock.last_request.json() == {"assignees": ["grace"]}
    gh.assign("#7", None)
    assert requests_mock.last_request.json() == {"assignees": []}


@pytest.mark.parametrize(
    "status, payload",
    [
        ("closed", {"state": "closed", "state_reason": "completed"}),
        ("Done", {"state": "closed", "state_reason": "completed"}),
        ("not planned", {"state": "closed", "state_reason": "not_planned"}),
        ("reopen", {"state": "open", "state_reason": "reopened"}),
        ("open", {"state": "open"}),
    ],
)
def test_transition_maps_statuses(gh, requests_mock, status, payload):
    requests_mock.patch(f"{API}/repos/acme/beans/issues/7", json=issue())
    gh.transition("#7", status)
    assert requests_mock.last_request.json() == payload


def test_transition_to_an_unknown_status_lists_the_choices(gh, requests_mock):
    with pytest.raises(ProviderError, match="open, closed, not-planned"):
        gh.transition("#7", "In Progress")
    assert requests_mock.call_count == 0
