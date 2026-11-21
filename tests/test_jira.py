"""The JIRA provider, with HTTP faked at the requests boundary."""

import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from grind.jira import JiraProvider, adf_to_text, text_to_adf
from grind.providers import ProviderError
from grind.tickets import ME, ListQuery, TicketChanges, TicketDraft

URL = "https://acme.atlassian.net"
V3 = f"{URL}/rest/api/3"
V2 = "https://jira.acme.example/rest/api/2"


def raw_issue(key="PROJ-1", **fields):
    return {
        "key": key,
        "fields": {
            "summary": "Order more beans",
            "status": {
                "name": "In Progress",
                "statusCategory": {"key": "indeterminate"},
            },
            "issuetype": {"name": "Task"},
            "assignee": {"displayName": "Ada Lovelace"},
            "reporter": {"displayName": "Grace Hopper"},
            "labels": ["supplies"],
            "created": "2026-10-01T09:00:00.000+0000",
            "updated": "2026-11-01T09:00:00.000+0000",
            "description": text_to_adf("We are nearly out.\nDark roast please."),
            **fields,
        },
    }


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv("JIRA_TOKEN", "tok")
    return JiraProvider(
        "work", {"provider": "jira", "url": URL, "user": "ada@acme.example"}
    )


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("JIRA_TOKEN", "pat")
    return JiraProvider(
        "dc",
        {"url": "https://jira.acme.example", "api-version": 2, "project": "OPS"},
    )


# ── ADF ────────────────────────────────────────────────────────────────────


def test_text_round_trips_through_adf():
    text = "First line\nsecond line\n\nNew paragraph"
    assert adf_to_text(text_to_adf(text)) == text


def test_adf_to_text_passes_plain_strings_and_none():
    assert adf_to_text("already text") == "already text"
    assert adf_to_text(None) == ""


def test_adf_to_text_flattens_lists_and_mentions():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Ask "},
                    {"type": "mention", "attrs": {"text": "@Grace"}},
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": item}],
                            }
                        ],
                    }
                    for item in ("beans", "milk")
                ],
            },
        ],
    }
    assert adf_to_text(doc) == "Ask @Grace\n\n- beans\n- milk"


# ── Setup and auth ─────────────────────────────────────────────────────────


def test_url_is_required():
    with pytest.raises(ProviderError, match="missing 'url'"):
        JiraProvider("work", {})


def test_bad_api_version_is_rejected():
    with pytest.raises(ProviderError, match="api-version must be 2 or 3"):
        JiraProvider("work", {"url": URL, "api-version": 9})


def test_cloud_uses_basic_auth_with_user_and_token(cloud, requests_mock):
    requests_mock.get(f"{V3}/myself", json={"displayName": "Ada Lovelace"})
    assert cloud.whoami() == "Ada Lovelace"
    expected = base64.b64encode(b"ada@acme.example:tok").decode()
    assert requests_mock.last_request.headers["Authorization"] == f"Basic {expected}"


def test_server_uses_a_bearer_token_and_api_v2(server, requests_mock):
    requests_mock.get(f"{V2}/myself", json={"displayName": "Ada"})
    server.whoami()
    assert requests_mock.last_request.headers["Authorization"] == "Bearer pat"


def test_jira_error_messages_are_surfaced(cloud, requests_mock):
    requests_mock.get(
        f"{V3}/issue/PROJ-1",
        status_code=400,
        json={"errorMessages": ["Bad thing"], "errors": {"summary": "required"}},
    )
    with pytest.raises(ProviderError, match="400: Bad thing; summary: required"):
        cloud.get_ticket("PROJ-1")


# ── list ───────────────────────────────────────────────────────────────────


def sent_jql(requests_mock):
    """The JQL as sent, unlowered (requests-mock lowercases ``qs``)."""
    return parse_qs(urlsplit(requests_mock.last_request.url).query)["jql"][0]


def jira(monkeypatch, **config):
    monkeypatch.setenv("JIRA_TOKEN", "tok")
    return JiraProvider(
        "work", {"provider": "jira", "url": URL, "user": "ada@acme.example", **config}
    )


@pytest.mark.parametrize(
    ("config", "containers", "scope"),
    [
        ({"projects": ["PROJ", "OPS"]}, (), 'project in ("PROJ", "OPS")'),
        ({"projects": "PROJ"}, (), 'project = "PROJ"'),
        # Most specific wins, and replaces the level below it.
        ({"project": "PROJ", "projects": ["A", "B"]}, (), 'project in ("A", "B")'),
        ({"projects": ["A", "B"]}, ("OPS",), 'project = "OPS"'),
        ({"project": "PROJ"}, ("A", "B"), 'project in ("A", "B")'),
        ({}, ('Q"A',), 'project = "Q\\"A"'),
    ],
)
def test_list_scope_precedence(monkeypatch, requests_mock, config, containers, scope):
    requests_mock.get(f"{V3}/search/jql", json={"issues": []})
    jira(monkeypatch, **config).list_tickets(
        ListQuery(mine=False, containers=containers)
    )
    assert sent_jql(requests_mock) == (
        f"{scope} AND statusCategory != Done ORDER BY updated DESC"
    )


def test_the_source_jql_still_applies_to_a_group(monkeypatch, requests_mock):
    requests_mock.get(f"{V3}/search/jql", json={"issues": []})
    provider = jira(monkeypatch, projects=["A", "B"], jql="labels = backend")
    provider.list_tickets(ListQuery(mine=False, state="all"))
    assert sent_jql(requests_mock) == (
        'project in ("A", "B") AND (labels = backend) ORDER BY updated DESC'
    )


def test_everyone_across_a_group_needs_no_other_filter(monkeypatch, requests_mock):
    requests_mock.get(f"{V3}/search/jql", json={"issues": [raw_issue()]})
    provider = jira(monkeypatch, projects=["A", "B"])
    (ticket,) = provider.list_tickets(ListQuery(mine=False, state="all"))
    assert ticket.ref == "work:PROJ-1"


def test_list_builds_jql_and_maps_tickets(cloud, requests_mock):
    requests_mock.get(f"{V3}/search/jql", json={"issues": [raw_issue()]})
    (ticket,) = cloud.list_tickets(ListQuery(text='say "hi"', containers=("PROJ",)))
    assert requests_mock.last_request.qs["jql"] == [
        'project = "proj" and assignee = currentuser() and statuscategory != done '
        'and text ~ "say \\"hi\\"" order by updated desc'
    ]
    assert ticket.ref == "work:PROJ-1"
    assert ticket.title == "Order more beans"
    assert ticket.status == "In Progress" and ticket.is_open
    assert ticket.type == "Task"
    assert ticket.assignee == "Ada Lovelace"
    assert ticket.labels == ("supplies",)
    assert ticket.url == f"{URL}/browse/PROJ-1"
    assert ticket.body == "We are nearly out.\nDark roast please."


def test_list_closed_uses_the_done_category_and_marks_tickets_closed(
    cloud, requests_mock
):
    done = raw_issue(status={"name": "Done", "statusCategory": {"key": "done"}})
    requests_mock.get(f"{V3}/search/jql", json={"issues": [done]})
    (ticket,) = cloud.list_tickets(ListQuery(state="closed"))
    assert "statuscategory = done" in requests_mock.last_request.qs["jql"][0]
    assert not ticket.is_open


def test_list_includes_the_sources_extra_jql(monkeypatch, requests_mock):
    monkeypatch.setenv("JIRA_TOKEN", "tok")
    provider = JiraProvider("work", {"url": URL, "jql": "labels = backend"})
    requests_mock.get(f"{V3}/search/jql", json={"issues": []})
    provider.list_tickets(ListQuery(mine=False, state="all"))
    assert requests_mock.last_request.qs["jql"] == [
        "(labels = backend) order by updated desc"
    ]


def test_an_unbounded_list_is_refused_before_any_request(cloud, requests_mock):
    with pytest.raises(ProviderError, match="every ticket"):
        cloud.list_tickets(ListQuery(mine=False, state="all"))
    assert requests_mock.call_count == 0


def test_cloud_list_follows_next_page_tokens(cloud, requests_mock):
    requests_mock.get(
        f"{V3}/search/jql",
        [
            {"json": {"issues": [raw_issue("PROJ-1")], "nextPageToken": "abc"}},
            {"json": {"issues": [raw_issue("PROJ-2")]}},
        ],
    )
    tickets = cloud.list_tickets(ListQuery())
    assert [t.key for t in tickets] == ["PROJ-1", "PROJ-2"]
    assert requests_mock.request_history[1].qs["nextpagetoken"] == ["abc"]


def test_server_list_pages_with_start_at_and_the_default_project(server, requests_mock):
    requests_mock.get(
        f"{V2}/search",
        [
            {"json": {"issues": [raw_issue("OPS-1", description="x")], "total": 2}},
            {"json": {"issues": [raw_issue("OPS-2", description="y")], "total": 2}},
        ],
    )
    tickets = server.list_tickets(ListQuery())
    assert [t.key for t in tickets] == ["OPS-1", "OPS-2"]
    assert requests_mock.request_history[0].qs["jql"][0].startswith('project = "ops"')
    assert requests_mock.request_history[1].qs["startat"] == ["1"]


def test_list_respects_the_limit(cloud, requests_mock):
    requests_mock.get(
        f"{V3}/search/jql",
        json={
            "issues": [raw_issue(f"PROJ-{n}") for n in range(3)],
            "nextPageToken": "x",
        },
    )
    assert len(cloud.list_tickets(ListQuery(limit=3))) == 3
    assert requests_mock.last_request.qs["maxresults"] == ["3"]
    assert requests_mock.call_count == 1


# ── get ────────────────────────────────────────────────────────────────────


def test_get_with_comments(cloud, requests_mock):
    with_comments = raw_issue(
        comment={
            "comments": [
                {
                    "author": {"displayName": "Grace Hopper"},
                    "body": text_to_adf("Ordered."),
                    "created": "2026-11-02T10:00:00.000+0000",
                }
            ]
        }
    )
    requests_mock.get(f"{V3}/issue/PROJ-1", json=with_comments)
    ticket = cloud.get_ticket("PROJ-1", comments=True)
    assert requests_mock.last_request.qs["fields"][0].endswith(",comment")
    assert [(c.author, c.body) for c in ticket.comments] == [
        ("Grace Hopper", "Ordered.")
    ]


def test_get_tolerates_missing_people_and_description(cloud, requests_mock):
    bare = raw_issue(assignee=None, reporter=None, description=None)
    requests_mock.get(f"{V3}/issue/PROJ-1", json=bare)
    ticket = cloud.get_ticket("PROJ-1")
    assert (ticket.assignee, ticket.reporter, ticket.body) == ("", "", "")


# ── writes ─────────────────────────────────────────────────────────────────


def test_cloud_create_sends_adf_and_account_ids(cloud, requests_mock):
    requests_mock.get(f"{V3}/myself", json={"accountId": "acc-1"})
    requests_mock.post(f"{V3}/issue", json={"key": "PROJ-9"})
    requests_mock.get(f"{V3}/issue/PROJ-9", json=raw_issue("PROJ-9"))
    ticket = cloud.create_ticket(
        TicketDraft(
            title="Buy filters",
            body="V60",
            type="Bug",
            labels=("shop",),
            assignee=ME,
            container="PROJ",
        )
    )
    posted = next(r for r in requests_mock.request_history if r.method == "POST")
    assert posted.json() == {
        "fields": {
            "project": {"key": "PROJ"},
            "summary": "Buy filters",
            "issuetype": {"name": "Bug"},
            "description": text_to_adf("V60"),
            "labels": ["shop"],
            "assignee": {"accountId": "acc-1"},
        }
    }
    assert ticket.key == "PROJ-9"


def test_server_create_sends_plain_text_and_defaults(server, requests_mock):
    requests_mock.post(f"{V2}/issue", json={"key": "OPS-9"})
    requests_mock.get(f"{V2}/issue/OPS-9", json=raw_issue("OPS-9", description="x"))
    server.create_ticket(TicketDraft(title="t", body="plain", assignee="grace"))
    posted = next(r for r in requests_mock.request_history if r.method == "POST")
    assert posted.json() == {
        "fields": {
            "project": {"key": "OPS"},
            "summary": "t",
            "issuetype": {"name": "Task"},
            "description": "plain",
            "assignee": {"name": "grace"},
        }
    }


def test_create_uses_the_only_project_in_a_group(monkeypatch, requests_mock):
    requests_mock.post(f"{V3}/issue", json={"key": "OPS-1"})
    requests_mock.get(f"{V3}/issue/OPS-1", json=raw_issue("OPS-1"))
    jira(monkeypatch, projects=["OPS"]).create_ticket(TicketDraft(title="t"))
    assert requests_mock.request_history[0].json()["fields"]["project"] == {
        "key": "OPS"
    }


@pytest.mark.parametrize(
    ("config", "container", "expected"),
    [
        ({"project": "PROJ", "projects": ["OPS"]}, "", "OPS"),
        ({"project": "PROJ", "projects": ["OPS", "ADM"]}, "WEB", "WEB"),
        ({"project": "PROJ"}, "", "PROJ"),
    ],
)
def test_create_follows_the_same_precedence_as_list(
    monkeypatch, requests_mock, config, container, expected
):
    requests_mock.post(f"{V3}/issue", json={"key": f"{expected}-1"})
    requests_mock.get(f"{V3}/issue/{expected}-1", json=raw_issue(f"{expected}-1"))
    jira(monkeypatch, **config).create_ticket(
        TicketDraft(title="t", container=container)
    )
    assert requests_mock.request_history[0].json()["fields"]["project"] == {
        "key": expected
    }


def test_create_asks_when_projects_outranks_project(monkeypatch, requests_mock):
    provider = jira(monkeypatch, project="PROJ", projects=["OPS", "ADM"])
    with pytest.raises(ProviderError, match="Choose from: OPS, ADM"):
        provider.create_ticket(TicketDraft(title="t"))


def test_create_in_a_group_of_projects_asks_which(monkeypatch, requests_mock):
    provider = jira(monkeypatch, projects=["PROJ", "OPS"])
    with pytest.raises(ProviderError, match="Choose from: PROJ, OPS"):
        provider.create_ticket(TicketDraft(title="t"))
    assert requests_mock.call_count == 0


def test_create_without_a_project_is_explained(cloud, requests_mock):
    with pytest.raises(ProviderError, match="Which project"):
        cloud.create_ticket(TicketDraft(title="t"))
    assert requests_mock.call_count == 0


def test_update_sends_fields_and_label_operations(cloud, requests_mock):
    requests_mock.put(f"{V3}/issue/PROJ-1", status_code=204)
    requests_mock.get(f"{V3}/issue/PROJ-1", json=raw_issue())
    cloud.update_ticket(
        "PROJ-1",
        TicketChanges(title="New", add_labels=("a",), remove_labels=("b",)),
    )
    put = next(r for r in requests_mock.request_history if r.method == "PUT")
    assert put.json() == {
        "fields": {"summary": "New"},
        "update": {"labels": [{"add": "a"}, {"remove": "b"}]},
    }


def test_comment_is_sent_as_adf_on_cloud(cloud, requests_mock):
    requests_mock.post(
        f"{V3}/issue/PROJ-1/comment",
        json={"author": {"displayName": "Ada"}, "body": text_to_adf("Hi")},
    )
    comment = cloud.add_comment("PROJ-1", "Hi")
    assert requests_mock.last_request.json() == {"body": text_to_adf("Hi")}
    assert (comment.author, comment.body) == ("Ada", "Hi")


def test_cloud_assign_resolves_a_name_to_an_account_id(cloud, requests_mock):
    requests_mock.get(f"{V3}/user/search", json=[{"accountId": "acc-2"}])
    requests_mock.put(f"{V3}/issue/PROJ-1/assignee", status_code=204)
    requests_mock.get(f"{V3}/issue/PROJ-1", json=raw_issue())
    cloud.assign("PROJ-1", "grace")
    put = next(r for r in requests_mock.request_history if r.method == "PUT")
    assert put.json() == {"accountId": "acc-2"}


@pytest.mark.parametrize(
    "matches, message",
    [
        ([], "No JIRA user matches"),
        (
            [
                {"accountId": "1", "displayName": "Grace A"},
                {"accountId": "2", "displayName": "Grace B"},
            ],
            "several JIRA users \\(Grace A, Grace B\\)",
        ),
    ],
)
def test_cloud_assign_refuses_to_guess(cloud, requests_mock, matches, message):
    requests_mock.get(f"{V3}/user/search", json=matches)
    with pytest.raises(ProviderError, match=message):
        cloud.assign("PROJ-1", "grace")
    assert not [r for r in requests_mock.request_history if r.method == "PUT"]


def test_unassign(cloud, server, requests_mock):
    requests_mock.put(f"{V3}/issue/PROJ-1/assignee", status_code=204)
    requests_mock.get(f"{V3}/issue/PROJ-1", json=raw_issue())
    cloud.assign("PROJ-1", None)
    put = next(r for r in requests_mock.request_history if r.method == "PUT")
    assert put.json() == {"accountId": None}

    requests_mock.put(f"{V2}/issue/OPS-1/assignee", status_code=204)
    requests_mock.get(f"{V2}/issue/OPS-1", json=raw_issue("OPS-1", description=""))
    server.assign("OPS-1", None)
    put = [r for r in requests_mock.request_history if r.method == "PUT"][-1]
    assert put.json() == {"name": None}


TRANSITIONS = {
    "transitions": [
        {"id": "11", "name": "Start work", "to": {"name": "In Progress"}},
        {"id": "31", "name": "Resolve", "to": {"name": "Done"}},
    ]
}


@pytest.mark.parametrize("status, wanted", [("done", "31"), ("START WORK", "11")])
def test_transition_matches_target_status_or_transition_name(
    cloud, requests_mock, status, wanted
):
    requests_mock.get(f"{V3}/issue/PROJ-1/transitions", json=TRANSITIONS)
    requests_mock.post(f"{V3}/issue/PROJ-1/transitions", status_code=204)
    requests_mock.get(f"{V3}/issue/PROJ-1", json=raw_issue())
    cloud.transition("PROJ-1", status)
    posted = next(r for r in requests_mock.request_history if r.method == "POST")
    assert posted.json() == {"transition": {"id": wanted}}


def test_transition_to_an_unavailable_status_lists_the_options(cloud, requests_mock):
    requests_mock.get(f"{V3}/issue/PROJ-1/transitions", json=TRANSITIONS)
    with pytest.raises(ProviderError, match="Available: In Progress, Done"):
        cloud.transition("PROJ-1", "Blocked")
    assert not [r for r in requests_mock.request_history if r.method == "POST"]
