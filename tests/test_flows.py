"""Running the bundled flows, and publishing new ones."""

from __future__ import annotations

import time

from conftest import headers

DESIGNER = ("northwind", "designer")
ANALYST = ("northwind", "analyst")
REVIEWER = ("northwind", "reviewer")


def h(who):
    return headers(*who)


def flows(client, who=ANALYST):
    response = client.get("/flows", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def start(client, process_id, who=ANALYST):
    response = client.post(f"/flows/{process_id}/start", json={}, headers=h(who))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def open_tasks(client, who=ANALYST, mine=True):
    response = client.get(f"/tasks?mine={str(mine).lower()}", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def complete(client, task_id, payload, who=ANALYST):
    response = client.post(
        f"/tasks/{task_id}/complete", json={"payload": payload}, headers=h(who)
    )
    assert response.status_code == 200, response.text
    return response.json()


def instance(client, instance_id, who=ANALYST):
    response = client.get(f"/instances/{instance_id}", headers=h(who))
    assert response.status_code == 200, response.text
    return response.json()


def test_the_bundled_flows_are_published_to_every_company(client):
    listed = flows(client)
    assert [row["process_id"] for row in listed] == [
        "Process_access_request",
        "Process_expense_approval",
        "Process_incident_response",
    ]
    # Published once per company, not shared between them.
    assert len(flows(client, ("initech", "analyst"))) == 3


def test_a_flow_advertises_what_is_inside_it(client):
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
    instance_id = start(client, "Process_expense_approval")

    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    assert submit["name"] == "Submit Expense Claim"

    # The form comes from the diagram, not from anything hardcoded here.
    detail = client.get(f"/tasks/{submit['id']}", headers=h(ANALYST)).json()
    assert detail["form"]["title"] == "Submit an expense claim"
    assert detail["form"]["required"] == ["amount", "purpose"]
    assert "cost_centre" in detail["form"]["properties"]

    complete(
        client,
        submit["id"],
        {"amount": 250, "purpose": "Conference ticket", "cost_centre": "Engineering"},
    )

    approve = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    assert approve["name"] == "Approve Expense Claim"
    assert approve["lane"] == "Approver"

    result = complete(
        client, approve["id"], {"decision": "approved", "approver_note": "Fine"}
    )
    assert result["instance_status"] == "complete"

    detail = instance(client, instance_id)
    assert detail["data"]["amount"] == "250"
    assert detail["data"]["decision"] == "approved"
    # The service task ran and was logged.
    assert [call["operation_id"] for call in detail["activity"]] == ["log/Write"]
    assert detail["activity"][0]["outcome"] == "ok"


def test_expense_within_policy_skips_the_approver(client):
    instance_id = start(client, "Process_expense_approval")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    result = complete(
        client, submit["id"], {"amount": 40, "purpose": "Taxi", "cost_centre": "Sales"}
    )
    # The decision table routed past the approver and the script task decided.
    assert result["instance_status"] == "complete"
    detail = instance(client, instance_id)
    assert [step["name"] for step in detail["steps"]] == ["Submit Expense Claim"]
    assert detail["activity"][0]["outcome"] == "ok"


def test_a_parallel_flow_opens_two_tasks_at_once(client):
    instance_id = start(client, "Process_incident_response")
    report = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, report["id"], {"title": "Checkout 500s", "severity": "sev1"})

    waiting = [t for t in open_tasks(client) if t["instance_id"] == instance_id]
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
    complete(client, triage["id"], {"root_cause": "bad deploy", "mitigated": True})
    assert instance(client, instance_id)["status"] != "complete"

    result = complete(client, comms["id"], {"channel": "status page"})
    assert result["instance_status"] == "complete"

    detail = instance(client, instance_id)
    assert detail["data"]["root_cause"] == "bad deploy"
    assert detail["data"]["channel"] == "status page"


def test_a_designer_can_publish_a_new_flow_and_anyone_can_run_it(client):
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

    # An analyst may not publish -- the library refuses process_definition.import.
    refused = client.post(
        "/flows", json={"bpmn": bpmn, "forms": forms}, headers=h(ANALYST)
    )
    assert refused.status_code == 403, refused.text

    created = client.post(
        "/flows",
        json={"bpmn": bpmn, "forms": forms, "lane_owners": {"Staff": ["analyst"]}},
        headers=h(DESIGNER),
    )
    assert created.status_code == 201, created.text
    assert created.json()["process_id"] == "Process_book_desk"
    assert created.json()["lane_owners"] == {"Staff": ["analyst"]}

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
    response = client.post("/flows", json={"bpmn": bpmn}, headers=h(DESIGNER))
    assert response.status_code == 422, response.text
    assert "nowhere.json" in response.json()["message"]


def test_publishing_rejects_something_that_is_not_a_flow(client):
    response = client.post(
        "/flows", json={"bpmn": "<html>not bpmn</html>"}, headers=h(DESIGNER)
    )
    assert response.status_code == 422, response.text


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
    report = client.post("/inspect", json={"bpmn": bpmn}, headers=h(DESIGNER)).json()
    assert report["process_id"] == "Process_preview"
    # The console warns about an operation it cannot serve.
    assert report["unknown_operations"] == ["carrier_pigeon/Send"]
    assert client.get("/flows/Process_preview", headers=h(DESIGNER)).status_code == 404


def test_a_reviewer_cannot_start_a_flow(client):
    """V1 roles are not a hierarchy: `manager` has no process.start."""
    response = client.post(
        "/flows/Process_expense_approval/start", json={}, headers=h(REVIEWER)
    )
    assert response.status_code == 403, response.text


def test_operators_can_hold_release_and_cancel(client):
    instance_id = start(client, "Process_incident_response")

    assert (
        client.post(f"/instances/{instance_id}/hold", headers=h(DESIGNER)).json()[
            "status"
        ]
        == "suspended"
    )
    assert (
        client.post(f"/instances/{instance_id}/release", headers=h(DESIGNER)).json()[
            "status"
        ]
        == "running"
    )
    assert (
        client.post(f"/instances/{instance_id}/cancel", headers=h(DESIGNER)).json()[
            "status"
        ]
        == "terminated"
    )
    # An analyst may not.
    other = start(client, "Process_incident_response")
    assert client.post(f"/instances/{other}/hold", headers=h(ANALYST)).status_code == 403


def test_a_boundary_timer_moves_the_work_on(client):
    """Published with a two-second window so the poller fires inside the test."""
    original = client.get(
        "/flows/Process_access_request/diagram", headers=h(DESIGNER)
    ).json()["bpmn"]
    hurried = original.replace("'PT10M'", "'PT2S'")
    forms = {
        "request-access.json": {
            "type": "object",
            "properties": {"system": {"type": "string"}},
        },
        "owner-review.json": {
            "type": "object",
            "properties": {"verdict": {"type": "string"}},
        },
    }
    published = client.post(
        "/flows",
        json={
            "bpmn": hurried,
            "forms": forms,
            "lane_owners": {
                "Requester": ["analyst"],
                "System Owner": ["reviewer"],
                "Security": ["auditor"],
            },
        },
        headers=h(DESIGNER),
    )
    assert published.status_code == 201, published.text

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
            for t in open_tasks(client, DESIGNER, mine=False)
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
    northwind_id = start(client, "Process_expense_approval")
    initech_id = start(client, "Process_expense_approval", ("initech", "analyst"))

    northwind = client.get("/instances", headers=h(ANALYST)).json()
    initech = client.get("/instances", headers=headers("initech", "analyst")).json()
    assert [row["id"] for row in northwind] == [northwind_id]
    assert [row["id"] for row in initech] == [initech_id]

    # A task id from the other company is not readable.
    assert (
        client.get(f"/instances/{initech_id}", headers=h(ANALYST)).status_code == 404
    )


def test_the_activity_log_lists_connector_calls(client):
    instance_id = start(client, "Process_expense_approval")
    submit = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, submit["id"], {"amount": 10, "purpose": "Coffee"})

    log = client.get("/activity", headers=h(DESIGNER)).json()
    assert log[0]["operation_id"] == "log/Write"
    assert log[0]["outcome"] == "ok"
    assert log[0]["instance_id"] == instance_id


def test_the_console_lists_the_operations_a_diagram_may_call(client):
    listed = client.get("/operations", headers=h(DESIGNER)).json()
    assert {row["operation_id"] for row in listed} == {
        "log/Write",
        "log/Trace",
        "http/GetRequest",
        "http/PostRequest",
    }


def test_republishing_does_not_revoke_a_lane(client):
    """A library behaviour worth pinning: lane ownership only ever widens.

    The bundled flows are published with every account owning every lane. Naming
    a narrower set on a later publish does NOT take anybody off the lane, so a
    leaver cannot be removed by republishing. See FINDINGS.md.
    """
    bpmn = client.get(
        "/flows/Process_access_request/diagram", headers=h(DESIGNER)
    ).json()["bpmn"]
    forms = {
        "request-access.json": {"type": "object"},
        "owner-review.json": {"type": "object"},
    }
    published = client.post(
        "/flows",
        json={
            "bpmn": bpmn.replace("'PT10M'", "'PT9M'"),
            "forms": forms,
            "lane_owners": {"System Owner": ["reviewer"]},
        },
        headers=h(DESIGNER),
    )
    assert published.status_code == 201
    assert published.json()["lane_owners"]["System Owner"] == ["reviewer"]

    instance_id = start(client, "Process_access_request")
    first = next(t for t in open_tasks(client) if t["instance_id"] == instance_id)
    complete(client, first["id"], {"system": "Production database"})

    # Everybody still sees the owner review, despite the narrowed list.
    still_visible = [
        who
        for who in (ANALYST, REVIEWER, ("northwind", "auditor"))
        if [
            t
            for t in open_tasks(client, who)
            if t["instance_id"] == instance_id
        ]
    ]
    assert len(still_visible) == 3, still_visible
