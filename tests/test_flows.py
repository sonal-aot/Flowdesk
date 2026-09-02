"""Running the bundled flows, and publishing new ones."""

from __future__ import annotations

import time

import json

import pytest

from conftest import FIXTURES, auth_headers, publish_fixture
from flowdesk import bpmn_inspect, main

ADMIN = ("northwind", "admin")
EDITOR = ("northwind", "editor")
REVIEWER = ("northwind", "reviewer")
SUBMITTER = ("northwind", "submitter")

# Bound per test by the `client` fixture; `h` needs the client to sign in.
_client = None


def h(who):
    return auth_headers(_client, *who)


@__import__("pytest").fixture(autouse=True)
def _bind_client(client):
    global _client
    _client = client
    yield
    _client = None


def flows(client, who=SUBMITTER):
    response = client.get("/flows", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def start(client, process_id, who=SUBMITTER):
    response = client.post(f"/flows/{process_id}/start", json={}, headers=h(who))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def open_tasks(client, who=SUBMITTER, mine=True):
    response = client.get(f"/tasks?mine={str(mine).lower()}", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def complete(client, task_id, payload, who=SUBMITTER):
    response = client.post(
        f"/tasks/{task_id}/complete", json={"payload": payload}, headers=h(who)
    )
    assert response.status_code == 200, response.text
    return response.json()


def instance(client, instance_id, who=SUBMITTER):
    response = client.get(f"/instances/{instance_id}", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_workspace_has_no_flows(client):
    """Nothing is bundled: a flow exists only once somebody publishes it."""
    assert flows(client) == []
    assert flows(client, ("initech", "submitter")) == []


def test_a_published_flow_belongs_to_its_company_alone(client):
    publish_fixture(client, "expense_approval", tenant="northwind")

    assert [row["process_id"] for row in flows(client)] == [
        "Process_expense_approval"
    ]
    # Initech published nothing, so Initech has nothing -- same diagram or not.
    assert flows(client, ("initech", "submitter")) == []
    assert (
        client.get(
            "/flows/Process_expense_approval",
            headers=auth_headers(client, "initech", "admin"),
        ).status_code
        == 404
    )


def test_a_flow_advertises_what_is_inside_it(client):
    publish_fixture(client, "expense_approval")
    expense = next(
        row for row in flows(client) if row["process_id"] == "Process_expense_approval"
    )
    assert expense["name"] == "Expense Approval"
    assert expense["lanes"] == ["Submitter", "Approver"]
    assert expense["decisions"] == ["expense_route"]
    assert expense["service_operations"] == ["log/Write"]
    assert expense["gateways"] == ["exclusive"]
    assert expense["has_dmn"] is True
    assert [step["name"] for step in expense["steps"]] == [
        "Submit Expense Claim",
        "Approve Expense Claim",
    ]
    assert all(step["has_form"] for step in expense["steps"])


def test_expense_over_the_threshold_needs_an_approver(client):
    publish_fixture(client, "expense_approval")
    instance_id = start(client, "Process_expense_approval")

    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    assert submit["name"] == "Submit Expense Claim"

    # The form comes from the diagram, not from anything hardcoded here.
    detail = client.get(f"/tasks/{submit['id']}", headers=h(SUBMITTER)).json()
    assert detail["form"]["title"] == "Submit an expense claim"
    assert detail["form"]["required"] == ["amount", "purpose"]
    assert "cost_centre" in detail["form"]["properties"]

    complete(
        client,
        submit["id"],
        {"amount": 250, "purpose": "Conference ticket", "cost_centre": "Engineering"},
    )

    # The Approver lane belongs to the reviewer, so it is not in the
    # submitter's worklist at all.
    assert not [t for t in open_tasks(client) if t["instance_id"] == instance_id]
    approve = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    assert approve["name"] == "Approve Expense Claim"
    assert approve["lane"] == "Approver"

    result = complete(
        client,
        approve["id"],
        {"decision": "approved", "approver_note": "Fine"},
        REVIEWER,
    )
    assert result["instance_status"] == "complete"

    detail = instance(client, instance_id)
    assert detail["data"]["amount"] == 250
    assert detail["data"]["decision"] == "approved"
    # The service task ran and was logged.
    assert [call["operation_id"] for call in detail["activity"]] == ["log/Write"]
    assert detail["activity"][0]["outcome"] == "ok"


def test_expense_within_policy_skips_the_approver(client):
    publish_fixture(client, "expense_approval")
    instance_id = start(client, "Process_expense_approval")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    result = complete(
        client, submit["id"], {"amount": 40, "purpose": "Taxi", "cost_centre": "Sales"}
    )
    # The decision table routed past the approver and the script task decided.
    assert result["instance_status"] == "complete"
    detail = instance(client, instance_id)
    person_steps = [step for step in detail["progress"] if step["kind"] == "person"]
    assert [step["name"] for step in person_steps] == [
        "Submit Expense Claim",
        "Approve Expense Claim",
    ]
    # The approver step was never needed: the decision table routed past it.
    assert [step["state"] for step in person_steps] == ["done", "not_needed"]
    assert detail["activity"][0]["outcome"] == "ok"


def test_a_parallel_flow_opens_two_tasks_at_once(client):
    publish_fixture(client, "incident_response")
    instance_id = start(client, "Process_incident_response")
    report = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, report["id"], {"title": "Checkout 500s", "severity": "sev1"})

    # Engineering is the reviewer's, Support is the editor's.
    triage_tasks = [
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    ]
    comms_tasks = [
        t for t in open_tasks(client, EDITOR) if t["instance_id"] == instance_id
    ]
    waiting = triage_tasks + comms_tasks
    assert sorted(t["name"] for t in waiting) == [
        "Customer Communication",
        "Technical Triage",
    ]
    assert sorted(t["lane"] for t in waiting) == ["Engineering", "Support"]

    detail = instance(client, instance_id)
    assert sorted(detail["waiting_on"]) == ["Engineering", "Support"]

    triage = next(t for t in waiting if t["name"] == "Technical Triage")
    comms = next(t for t in waiting if t["name"] == "Customer Communication")

    # Finishing one leaves the other open: the join waits for both.
    complete(
        client,
        triage["id"],
        {"root_cause": "bad deploy", "mitigated": True},
        REVIEWER,
    )
    assert instance(client, instance_id)["status"] != "complete"

    result = complete(client, comms["id"], {"channel": "status page"}, EDITOR)
    assert result["instance_status"] == "complete"

    detail = instance(client, instance_id)
    assert detail["data"]["root_cause"] == "bad deploy"
    assert detail["data"]["channel"] == "status page"


def test_an_editor_can_publish_a_new_flow_and_anyone_can_run_it(client):
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
  id="Definitions_holiday" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_book_desk" name="Book A Desk" isExecutable="true">
    <bpmn:laneSet id="LaneSet_desk">
      <bpmn:lane id="Lane_staff" name="Staff">
        <bpmn:flowNodeRef>start</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>task_book</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>end_booked</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="start"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="task_book" name="Choose A Desk">
      <bpmn:extensionElements>
        <spiffworkflow:properties>
          <spiffworkflow:property name="formJsonSchemaFilename" value="desk.json" />
        </spiffworkflow:properties>
      </bpmn:extensionElements>
      <bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="end_booked"><bpmn:incoming>f2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="task_book" />
    <bpmn:sequenceFlow id="f2" sourceRef="task_book" targetRef="end_booked" />
  </bpmn:process>
</bpmn:definitions>"""
    forms = {
        "desk.json": {
            "title": "Choose a desk",
            "type": "object",
            "required": ["desk"],
            "properties": {"desk": {"type": "string", "title": "Desk"}},
        }
    }

    # A submitter may not publish.
    refused = client.post(
        "/flows", json={"bpmn": bpmn, "forms": forms}, headers=h(SUBMITTER)
    )
    assert refused.status_code == 403, refused.text

    created = client.post(
        "/flows",
        json={"bpmn": bpmn, "forms": forms, "lane_owners": {"Staff": ["submitter"]}},
        headers=h(ADMIN),
    )
    assert created.status_code == 201, created.text
    assert created.json()["process_id"] == "Process_book_desk"
    assert created.json()["lane_owners"] == {"Staff": ["submitter"]}

    # ...and now anybody who owns the lane can run it.
    instance_id = start(client, "Process_book_desk")
    task = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    assert task["name"] == "Choose A Desk"
    assert complete(client, task["id"], {"desk": "4B"})["instance_status"] == "complete"

    # The restricted lane really is restricted.
    assert not [
        t
        for t in open_tasks(client, REVIEWER)
        if t["process_id"] == "Process_book_desk"
    ]


def test_publishing_rejects_a_diagram_whose_forms_are_missing(client):
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core" id="D" targetNamespace="x">
  <bpmn:process id="Process_needs_form" isExecutable="true">
    <bpmn:startEvent id="s"><bpmn:outgoing>f</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="t" name="T">
      <bpmn:extensionElements><spiffworkflow:properties>
        <spiffworkflow:property name="formJsonSchemaFilename" value="nowhere.json" />
      </spiffworkflow:properties></bpmn:extensionElements>
      <bpmn:incoming>f</bpmn:incoming><bpmn:outgoing>g</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="e"><bpmn:incoming>g</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f" sourceRef="s" targetRef="t" />
    <bpmn:sequenceFlow id="g" sourceRef="t" targetRef="e" />
  </bpmn:process>
</bpmn:definitions>"""
    response = client.post("/flows", json={"bpmn": bpmn}, headers=h(ADMIN))
    assert response.status_code == 422, response.text
    assert "nowhere.json" in response.json()["message"]


def test_publishing_rejects_something_that_is_not_a_flow(client):
    response = client.post(
        "/flows", json={"bpmn": "<html>not bpmn</html>"}, headers=h(ADMIN)
    )
    assert response.status_code == 422, response.text


def test_permission_is_settled_before_the_file_is_looked_at(client):
    """A submitter gets 403 for rubbish input too, not a hint that it was parsed."""
    response = client.post(
        "/flows", json={"bpmn": "<html>not bpmn</html>"}, headers=h(SUBMITTER)
    )
    assert response.status_code == 403, response.text


def test_inspect_reports_a_diagram_without_publishing_it(client):
    bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core" id="D" targetNamespace="x">
  <bpmn:process id="Process_preview" isExecutable="true">
    <bpmn:startEvent id="s"><bpmn:outgoing>f</bpmn:outgoing></bpmn:startEvent>
    <bpmn:serviceTask id="svc" name="Call something">
      <bpmn:extensionElements>
        <spiffworkflow:serviceTaskOperator id="carrier_pigeon/Send" />
      </bpmn:extensionElements>
      <bpmn:incoming>f</bpmn:incoming><bpmn:outgoing>g</bpmn:outgoing>
    </bpmn:serviceTask>
    <bpmn:endEvent id="e"><bpmn:incoming>g</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f" sourceRef="s" targetRef="svc" />
    <bpmn:sequenceFlow id="g" sourceRef="svc" targetRef="e" />
  </bpmn:process>
</bpmn:definitions>"""
    report = client.post("/inspect", json={"bpmn": bpmn}, headers=h(ADMIN)).json()
    assert report["process_id"] == "Process_preview"
    # The console warns about an operation it cannot serve.
    assert report["unknown_operations"] == ["carrier_pigeon/Send"]
    assert client.get("/flows/Process_preview", headers=h(ADMIN)).status_code == 404


def test_a_reviewer_cannot_start_a_flow(client):
    """V1 roles are not a hierarchy: reviewer maps to `manager`, which has no
    process.start, so a reviewer cannot start a flow."""
    publish_fixture(client, "expense_approval")
    response = client.post(
        "/flows/Process_expense_approval/start", json={}, headers=h(REVIEWER)
    )
    assert response.status_code == 403, response.text


def test_operators_can_hold_release_and_cancel(client):
    publish_fixture(client, "incident_response")
    instance_id = start(client, "Process_incident_response")

    assert (
        client.post(f"/instances/{instance_id}/hold", headers=h(ADMIN)).json()[
            "status"
        ]
        == "suspended"
    )
    assert (
        client.post(f"/instances/{instance_id}/release", headers=h(ADMIN)).json()[
            "status"
        ]
        == "running"
    )
    assert (
        client.post(f"/instances/{instance_id}/cancel", headers=h(ADMIN)).json()[
            "status"
        ]
        == "terminated"
    )
    # A submitter may not.
    other = start(client, "Process_incident_response")
    assert client.post(f"/instances/{other}/hold", headers=h(SUBMITTER)).status_code == 403


def test_a_boundary_timer_moves_the_work_on(client):
    """Published with a two-second window so the poller fires inside the test."""
    publish_fixture(
        client,
        "access_request",
        edit=lambda bpmn: bpmn.replace("'PT10M'", "'PT2S'"),
    )

    instance_id = start(client, "Process_access_request")
    request_task = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(
        client,
        request_task["id"],
        {"system": "Production database", "access_level": "read", "reason": "oncall"},
    )

    def names_open():
        return [
            t["name"]
            for t in open_tasks(client, ADMIN, mine=False)
            if t["instance_id"] == instance_id
        ]

    assert names_open() == ["System Owner Review"]

    deadline = time.time() + 30
    while time.time() < deadline:
        if "Security Decides Instead" in names_open():
            break
        time.sleep(0.5)

    # The timer fired: the owner's review is gone and security has the work.
    assert names_open() == ["Security Decides Instead"], names_open()


def test_companies_are_isolated(client):
    publish_fixture(client, "expense_approval", tenant="northwind")
    publish_fixture(client, "expense_approval", tenant="initech")
    northwind_id = start(client, "Process_expense_approval")
    initech_id = start(client, "Process_expense_approval", ("initech", "submitter"))

    northwind = client.get("/instances", headers=h(SUBMITTER)).json()
    initech = client.get("/instances", headers=auth_headers(client, "initech", "submitter")).json()
    assert [row["id"] for row in northwind] == [northwind_id]
    assert [row["id"] for row in initech] == [initech_id]

    # A task id from the other company is not readable.
    assert (
        client.get(f"/instances/{initech_id}", headers=h(SUBMITTER)).status_code == 404
    )


def test_the_activity_log_lists_connector_calls(client):
    publish_fixture(client, "expense_approval")
    instance_id = start(client, "Process_expense_approval")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit["id"], {"amount": 10, "purpose": "Coffee"})

    log = client.get("/activity", headers=h(ADMIN)).json()
    assert log[0]["operation_id"] == "log/Write"
    assert log[0]["outcome"] == "ok"
    assert log[0]["instance_id"] == instance_id


def test_the_console_lists_the_operations_a_diagram_may_call(client):
    listed = client.get("/operations", headers=h(ADMIN)).json()
    assert {row["operation_id"] for row in listed} == {
        "log/Write",
        "log/Trace",
        "http/GetRequest",
        "http/PostRequest",
    }


def test_republishing_narrows_a_lane(client):
    """The library only ever widens lane membership; the app reconciles it.

    Published first with two owners, then again with one. The dropped owner must
    actually lose the work.
    """
    publish_fixture(
        client,
        "access_request",
        lanes={
            "Requester": ["submitter"],
            "System Owner": ["reviewer", "editor"],
            "Security": ["admin"],
        },
    )
    first = client.get("/flows/Process_access_request", headers=h(ADMIN)).json()
    assert first["lane_owners"]["System Owner"] == ["editor", "reviewer"]

    republished = publish_fixture(
        client,
        "access_request",
        edit=lambda bpmn: bpmn.replace("'PT10M'", "'PT9M'"),
        lanes={
            "Requester": ["submitter"],
            "System Owner": ["reviewer"],
            "Security": ["admin"],
        },
    )
    assert republished["lane_owners"]["System Owner"] == ["reviewer"]

    instance_id = start(client, "Process_access_request")
    submitted = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submitted["id"], {"system": "Production database"})

    # The remaining owner has it; the dropped one does not.
    assert [
        t["name"]
        for t in open_tasks(client, REVIEWER)
        if t["instance_id"] == instance_id
    ] == ["System Owner Review"]
    assert not [
        t
        for t in open_tasks(client, EDITOR)
        if t["instance_id"] == instance_id
    ]


def test_every_lane_must_have_an_owner(client):
    forms = json.loads(
        (FIXTURES / "expense_approval.forms.json").read_text(encoding="utf-8")
    )
    response = client.post(
        "/flows",
        json={
            "bpmn": (FIXTURES / "expense_approval.bpmn").read_text(encoding="utf-8"),
            "forms": forms,
            "lane_owners": {"Submitter": ["submitter"]},
        },
        headers=h(ADMIN),
    )
    assert response.status_code == 422, response.text
    assert "Approver" in response.json()["message"]


def test_publishing_reports_every_problem_at_once(client):
    response = client.post(
        "/flows",
        json={
            "bpmn": (FIXTURES / "expense_approval.bpmn").read_text(encoding="utf-8"),
            "forms": {},
            "lane_owners": {},
        },
        headers=h(ADMIN),
    )
    assert response.status_code == 422, response.text
    message = response.json()["message"]
    assert "form schemas" in message
    assert "Approver" in message and "Submitter" in message


def test_lane_owners_are_per_company(client):
    """The same lane name in two companies must not share owners."""
    publish_fixture(
        client,
        "expense_approval",
        tenant="northwind",
        lanes={"Submitter": ["submitter"], "Approver": ["reviewer"]},
    )
    publish_fixture(
        client,
        "expense_approval",
        tenant="initech",
        lanes={"Submitter": ["submitter"], "Approver": ["editor"]},
    )

    northwind = client.get("/flows/Process_expense_approval", headers=h(ADMIN)).json()
    initech = client.get(
        "/flows/Process_expense_approval",
        headers=auth_headers(client, "initech", "admin"),
    ).json()
    assert northwind["lane_owners"]["Approver"] == ["reviewer"]
    assert initech["lane_owners"]["Approver"] == ["editor"]


def test_one_person_fills_a_form_then_another_decides(client):
    """The plainest shape: submit, then somebody else approves or rejects.

    Both branches are checked, and so is the thing that makes it useful -- the
    reviewer can see what was submitted before deciding.
    """
    publish_fixture(client, "two_step_request")

    for verdict, expected in (("approved", "complete"), ("rejected", "complete")):
        instance_id = start(client, "Process_two_step_request")

        # The requester fills in the first form.
        submit_task = next(
            t for t in open_tasks(client) if t["instance_id"] == instance_id
        )
        assert submit_task["name"] == "Submit Request"
        form = client.get(f"/tasks/{submit_task['id']}", headers=h(SUBMITTER)).json()
        assert form["form"]["title"] == "Submit your request"
        assert form["form"]["required"] == ["subject", "details"]

        complete(
            client,
            submit_task["id"],
            {
                "subject": "New laptop",
                "details": "Mine will not charge",
                "urgency": "high",
            },
        )

        # It is now the approver's, and nobody else's.
        assert not [t for t in open_tasks(client) if t["instance_id"] == instance_id]
        review = next(
            t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
        )
        assert review["name"] == "Review Request"
        assert review["lane"] == "Approver"

        # The approver can see what was submitted before deciding.
        opened = client.get(f"/tasks/{review['id']}", headers=h(REVIEWER)).json()
        assert opened["known_data"]["subject"] == "New laptop"
        assert opened["known_data"]["urgency"] == "high"
        assert opened["form"]["properties"]["decision"]["enum"] == [
            "approved",
            "rejected",
        ]

        result = complete(
            client,
            review["id"],
            {"decision": verdict, "reviewer_comment": "noted"},
            REVIEWER,
        )
        assert result["instance_status"] == expected

        detail = instance(client, instance_id)
        assert detail["data"]["decision"] == verdict
        person_steps = [s for s in detail["progress"] if s["kind"] == "person"]
        assert [step["name"] for step in person_steps] == [
            "Submit Request",
            "Review Request",
        ]
        assert all(step["state"] == "done" for step in person_steps)
        # The branch not taken is shown as such rather than left out.
        ends = {s["name"]: s["state"] for s in detail["progress"] if s["kind"] == "end"}
        assert ends == (
            {"Approved": "done", "Rejected": "not_needed"}
            if verdict == "approved"
            else {"Approved": "not_needed", "Rejected": "done"}
        )


def test_a_run_shows_its_whole_shape_and_who_is_next(client):
    """The detail view answers "where is this and who owes the next move"."""
    publish_fixture(client, "two_step_request")
    instance_id = start(client, "Process_two_step_request")

    detail = instance(client, instance_id)
    # Every step is listed in the order a run reaches them, including the ones
    # nobody has got to yet.
    assert [(s["name"], s["kind"], s["state"]) for s in detail["progress"]] == [
        ("Request raised", "start", "done"),
        ("Submit Request", "person", "waiting"),
        ("Review Request", "person", "upcoming"),
        ("Approved?", "branch", "upcoming"),
        ("Approved", "end", "upcoming"),
        ("Rejected", "end", "upcoming"),
    ]
    # And the waiting step names the actual person, with why they have it.
    first = next(s for s in detail["progress"] if s["kind"] == "person")
    assert [p["name"] for p in first["people"]] == ["Sam Submitter"]
    assert first["people"][0]["why"] == "owns this lane"
    assert detail["next_action"] == "Waiting on Submit Request — Sam Submitter"

    submit_task = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit_task["id"], {"subject": "Chair", "details": "Broken"})

    detail = instance(client, instance_id)
    assert [
        (s["name"], s["state"]) for s in detail["progress"] if s["kind"] == "person"
    ] == [
        ("Submit Request", "done"),
        ("Review Request", "waiting"),
    ]
    submitted = next(s for s in detail["progress"] if s["name"] == "Submit Request")
    assert submitted["by"] == "Sam Submitter"
    assert submitted["at"]
    assert detail["next_action"] == "Waiting on Review Request — Riya Reviewer"

    # The list view carries the same answer without opening anything.
    listed = next(
        row
        for row in client.get("/instances", headers=h(ADMIN)).json()
        if row["id"] == instance_id
    )
    assert listed["waiting_step"] == "Review Request"
    assert listed["waiting_people"] == ["Riya Reviewer"]

    review = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(client, review["id"], {"decision": "approved"}, REVIEWER)
    assert instance(client, instance_id)["next_action"] == "Finished."


def test_a_parallel_run_names_both_people_waiting(client):
    publish_fixture(client, "incident_response")
    instance_id = start(client, "Process_incident_response")
    report = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, report["id"], {"title": "Outage", "severity": "sev1"})

    detail = instance(client, instance_id)
    waiting = [s for s in detail["progress"] if s["state"] == "waiting"]
    assert sorted(s["name"] for s in waiting) == [
        "Customer Communication",
        "Technical Triage",
    ]
    assert "Riya Reviewer" in detail["next_action"]
    assert "Erin Editor" in detail["next_action"]


def test_only_the_actions_the_engine_accepts_are_offered(client):
    """A finished run must not be offered Hold, Retry or Cancel.

    The rules are the library's own preconditions, not guesses: suspend needs a
    non-terminal, non-suspended run; resume needs a suspended one; terminate
    needs a non-terminal one; retry needs an errored one.
    """
    publish_fixture(client, "two_step_request")
    instance_id = start(client, "Process_two_step_request")

    def state():
        detail = instance(client, instance_id)
        return detail["status"], detail["allowed_actions"], detail["no_actions_reason"]

    status, actions, reason = state()
    assert status == "user_input_required"
    assert actions == ["hold", "cancel"]
    assert reason is None

    # On hold: release and cancel, but not hold again.
    client.post(f"/instances/{instance_id}/hold", headers=h(ADMIN))
    assert state()[1] == ["release", "cancel"]
    client.post(f"/instances/{instance_id}/release", headers=h(ADMIN))

    # Run it to completion.
    submit_task = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit_task["id"], {"subject": "Desk", "details": "Wobbly"})
    review = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(client, review["id"], {"decision": "approved"}, REVIEWER)

    status, actions, reason = state()
    assert status == "complete"
    assert actions == []
    assert reason == "This run has finished, so there is nothing to operate."


def test_operating_a_finished_run_says_why(client):
    publish_fixture(client, "two_step_request")
    instance_id = start(client, "Process_two_step_request")
    submit_task = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit_task["id"], {"subject": "Desk", "details": "Wobbly"})
    review = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(client, review["id"], {"decision": "approved"}, REVIEWER)

    for action, wording in (
        ("hold", "put on hold"),
        ("cancel", "cancelled"),
        ("retry", "retried"),
        ("release", "released"),
    ):
        response = client.post(f"/instances/{instance_id}/{action}", headers=h(ADMIN))
        assert response.status_code == 409, (action, response.text)
        assert response.json()["message"] == (
            f"This run is complete, so it cannot be {wording}."
        )


def test_a_cancelled_run_offers_nothing_either(client):
    publish_fixture(client, "two_step_request")
    instance_id = start(client, "Process_two_step_request")
    client.post(f"/instances/{instance_id}/cancel", headers=h(ADMIN))

    detail = instance(client, instance_id)
    assert detail["status"] == "terminated"
    assert detail["allowed_actions"] == []
    assert detail["no_actions_reason"].startswith("This run was cancelled")


def test_the_trace_shows_steps_no_person_ever_touches(client):
    """A run's shape is more than its user tasks.

    The engine keeps a row for every step it ran, so a service task, a decision
    and the gateway that routed past a step all show up -- which matters most for
    a flow with no user tasks at all, where the human tasks say nothing.
    """
    publish_fixture(client, "expense_approval")
    instance_id = start(client, "Process_expense_approval")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(
        client,
        submit["id"],
        {"amount": 250, "purpose": "Conference", "cost_centre": "ENG"},
    )
    approve = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(
        client, approve["id"], {"decision": "approved", "approver_note": "Fine"}, REVIEWER
    )

    progress = instance(client, instance_id)["progress"]
    kinds = {step["kind"] for step in progress}
    assert {"service", "decision"} <= kinds, kinds
    service = next(step for step in progress if step["kind"] == "service")
    assert service["state"] == "done"


MANUAL_TASK_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
    id="Definitions_manual" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_manual_demo" isExecutable="true">
    <bpmn:startEvent id="start"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="show" />
    <bpmn:manualTask id="show" name="Read This">
      <bpmn:extensionElements>
        <spiffworkflow:instructionsForEndUser>## Report

**Status:** {{ result.http_status }}

| Name |
{% for row in result.body %}
| {{ row.name }} |
{% endfor %}</spiffworkflow:instructionsForEndUser>
      </bpmn:extensionElements>
      <bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing>
    </bpmn:manualTask>
    <bpmn:sequenceFlow id="f2" sourceRef="show" targetRef="end" />
    <bpmn:endEvent id="end"><bpmn:incoming>f2</bpmn:incoming></bpmn:endEvent>
  </bpmn:process>
</bpmn:definitions>"""


def test_a_manual_task_is_a_person_step_and_keeps_its_instructions():
    """`manualTask` is a person step with no form, and the modeller's own text
    for it lives in `instructionsForEndUser`, which the library ignores."""
    flow = bpmn_inspect.inspect(MANUAL_TASK_BPMN)

    assert [(step.kind, step.name) for step in flow.steps] == [
        ("start", "Start"),
        ("person", "Read This"),
        ("end", "End"),
    ]
    assert flow.user_tasks[0].form_schema is None
    assert flow.user_tasks[0].instructions.startswith("## Report")


def test_instructions_are_rendered_against_what_the_run_collected():
    step = bpmn_inspect.inspect(MANUAL_TASK_BPMN).steps[1]
    rendered = main.render_instructions(
        step.instructions,
        {"result": {"http_status": 200, "body": [{"name": "Acme"}, {"name": "Bo"}]}},
    )

    assert "**Status:** 200" in rendered
    # No blank line between rows, or every markdown table falls apart.
    assert "| Acme |\n| Bo |" in rendered


def test_instructions_missing_their_data_render_blank_rather_than_failing():
    """Half a sentence beats an error on a screen somebody is trying to work from."""
    step = bpmn_inspect.inspect(MANUAL_TASK_BPMN).steps[1]

    rendered = main.render_instructions(step.instructions, {})

    assert "## Report" in rendered
    assert "**Status:**" in rendered


def test_a_broken_template_says_so_instead_of_raising():
    assert "could not be rendered" in main.render_instructions("{% for %}", {})


def test_the_capability_tour_runs_every_construct_the_library_supports(client):
    """One flow, every construct, driven to an end event.

    If the library gains or loses something, this is the test that notices. The
    escalation timer is shortened so the boundary event is exercised too; the
    published file leaves it at ten minutes.
    """
    publish_fixture(client, "capability_tour")
    instance_id = start(client, "Process_capability_tour", who=SUBMITTER)

    # userTask with a form
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    assert submit["name"] == "Submit Request"
    complete(
        client,
        submit["id"],
        {"subject": "Standing desk", "amount": 250, "urgency": "high"},
    )

    # scriptTask and the DMN both ran, and the exclusive gateway routed on them
    detail = instance(client, instance_id)
    assert detail["data"]["tier"] == "medium"
    assert detail["data"]["score"] == 25
    assert detail["data"]["needs_review"] is True

    # parallelGateway opened both branches at once, in different lanes
    waiting = sorted(
        t["name"] for t in open_tasks(client, ADMIN, mine=False)
        if t["instance_id"] == instance_id
    )
    assert waiting == ["Approve Request", "Check Budget"]

    approve = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(client, approve["id"], {"decision": "approved"}, REVIEWER)
    budget = next(
        t for t in open_tasks(client, EDITOR) if t["instance_id"] == instance_id
    )
    complete(client, budget["id"], {"budget_ok": True}, EDITOR)

    # The intermediate catch timer holds the run until the poller fires it, and
    # the service task on the other side needs the connectors installed there.
    deadline = time.time() + 40
    review = None
    while time.time() < deadline and review is None:
        review = next(
            (
                t for t in open_tasks(client, SUBMITTER)
                if t["instance_id"] == instance_id and t["name"] == "Review Outcome"
            ),
            None,
        )
        if review is None:
            time.sleep(0.5)
    assert review is not None, "the cooling-off timer never released the run"

    # manualTask: no form, and its instructions carry the run's own data
    opened = client.get(
        f"/tasks/{review['id']}", headers=h(SUBMITTER)
    ).json()
    assert opened["form"] is None
    assert "**Decision:** approved" in opened["instructions"]
    assert "| Tier | medium |" in opened["instructions"]

    complete(client, review["id"], {}, SUBMITTER)

    final = instance(client, instance_id)
    assert final["status"] == "complete"
    kinds = {step["kind"] for step in final["progress"] if step["state"] == "done"}
    assert {"start", "person", "script", "decision", "branch", "wait", "service", "end"} <= kinds

    # The service task ran, and the branch nobody took is marked as such
    assert [call["operation_id"] for call in final["activity"]] == ["log/Write"]
    states = {step["name"]: step["state"] for step in final["progress"]}
    assert states["Closed"] == "done"
    assert states["Rejected"] == "not_needed"
    assert states["Approve By Policy"] == "not_needed"


def test_the_tour_skips_every_person_when_policy_allows(client):
    """Within policy and not urgent: the DMN routes past both reviewers."""
    publish_fixture(client, "capability_tour")
    instance_id = start(client, "Process_capability_tour", who=SUBMITTER)
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit["id"], {"subject": "Mouse", "amount": 50, "urgency": "low"})

    detail = instance(client, instance_id)
    assert detail["data"]["needs_review"] is False
    assert detail["data"]["decision"] == "approved"
    assert detail["data"]["decided_by"] == "policy"
    states = {step["name"]: step["state"] for step in detail["progress"]}
    assert states["Approve Request"] == "upcoming"
    assert states["Approve By Policy"] == "done"


def test_a_boundary_timer_hands_the_approval_to_finance(client):
    """Nobody answers, so the timer cancels the approval and escalates it."""
    publish_fixture(
        client, "capability_tour", edit=lambda bpmn: bpmn.replace("'PT10M'", "'PT2S'")
    )
    instance_id = start(client, "Process_capability_tour", who=SUBMITTER)
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit["id"], {"subject": "Laptop", "amount": 800, "urgency": "normal"})

    deadline = time.time() + 40
    while time.time() < deadline:
        names = sorted(
            t["name"] for t in open_tasks(client, ADMIN, mine=False)
            if t["instance_id"] == instance_id
        )
        if "Escalated Approval" in names:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("the boundary timer never fired")

    assert "Approve Request" not in names
    escalated = next(
        t for t in open_tasks(client, EDITOR)
        if t["instance_id"] == instance_id and t["name"] == "Escalated Approval"
    )
    assert escalated["lane"] == "Finance"


def test_a_designer_can_delete_a_flow_without_losing_its_history(client):
    """Deleting takes the flow out of the catalogue. Runs that happened stay."""
    publish_fixture(client, "two_step_request")
    instance_id = start(client, "Process_two_step_request")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit["id"], {"subject": "Chair", "details": "Broken"})
    review = next(
        t for t in open_tasks(client, REVIEWER) if t["instance_id"] == instance_id
    )
    complete(client, review["id"], {"decision": "approved"}, REVIEWER)

    response = client.delete("/flows/Process_two_step_request", headers=h(ADMIN))
    assert response.status_code == 200, response.text
    assert response.json()["files_removed"] >= 1

    # Gone from the catalogue, and nobody can start it
    assert flows(client) == []
    assert client.post(
        "/flows/Process_two_step_request/start", json={}, headers=h(SUBMITTER)
    ).status_code == 404

    # The run it produced still opens, with its whole trace
    detail = instance(client, instance_id)
    assert detail["status"] == "complete"
    assert [s["name"] for s in detail["progress"] if s["kind"] == "person"] == [
        "Submit Request",
        "Review Request",
    ]


def test_deleting_a_flow_with_a_run_in_flight_is_refused(client):
    publish_fixture(client, "two_step_request")
    start(client, "Process_two_step_request")

    response = client.delete("/flows/Process_two_step_request", headers=h(ADMIN))

    assert response.status_code == 409, response.text
    assert "still going" in response.json()["technical"]
    assert flows(client) != []


@pytest.mark.parametrize("who", [REVIEWER, SUBMITTER])
def test_only_a_designer_may_delete_or_edit_a_flow(client, who):
    publish_fixture(client, "two_step_request")

    assert client.delete(
        "/flows/Process_two_step_request", headers=h(who)
    ).status_code == 403
    assert client.get(
        "/flows/Process_two_step_request/source", headers=h(who)
    ).status_code == 403
    assert flows(client) != []


def test_editing_a_flow_starts_from_what_is_published(client):
    """Editing is publishing again, so the screen fills itself from the flow."""
    publish_fixture(client, "expense_approval")

    source = client.get(
        "/flows/Process_expense_approval/source", headers=h(EDITOR)
    ).json()

    assert "<bpmn:process" in source["bpmn"]
    assert source["dmn"] is not None and "decisionTable" in source["dmn"]
    assert sorted(source["forms"]) == ["approve-expense.json", "submit-expense.json"]
    assert source["lane_owners"] == {
        "Submitter": ["submitter"],
        "Approver": ["reviewer"],
    }

    # Publishing it back is a new version of the same flow, not a second one
    published = client.post(
        "/flows",
        json={
            "bpmn": source["bpmn"].replace("Submit Expense Claim", "Submit A Claim"),
            "dmn": source["dmn"],
            "forms": source["forms"],
            "lane_owners": source["lane_owners"],
        },
        headers=h(EDITOR),
    ).json()
    assert published["process_id"] == "Process_expense_approval"
    listed = flows(client)
    assert len(listed) == 1
    assert listed[0]["versions"] == 2
    assert [step["name"] for step in listed[0]["steps"]][0] == "Submit A Claim"


def test_publishing_a_deleted_flow_brings_it_back(client):
    publish_fixture(client, "two_step_request")
    client.delete("/flows/Process_two_step_request", headers=h(ADMIN))
    assert flows(client) == []

    publish_fixture(client, "two_step_request")

    assert [row["process_id"] for row in flows(client)] == ["Process_two_step_request"]
