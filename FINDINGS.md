# m8flow-bpmn-core — Integration Findings, app #2

Sample app #2 of **M8F-421**: Flowdesk, a generic workflow console. Designers
publish arbitrary BPMN; everybody else picks a flow and runs it. Consumes
`m8flow-bpmn-core` 0.1.0 **as a built wheel**.

App #1 (TimeOff) was a single-purpose app with one hardcoded diagram, and its 21
findings are in that repo. This app hardcodes nothing about any flow, which
surfaces a different class of problem: what a host needs from the library when it
does not know the process in advance.

Every finding below has a test or a reproduction in this repo.

---

## 1. Publishing a diagram is arbitrary code execution — *critical*

A BPMN script task executes Python in the host process, unsandboxed. Reproduced
end to end through the API: a published diagram containing

```xml
<bpmn:scriptTask id="probe">
  <bpmn:script>open("/tmp/probe.txt", "w").write("...")</bpmn:script>
</bpmn:scriptTask>
```

wrote that file to disk when an ordinary user started the flow. `__import__("os")`
also resolves. So `process_definition.import` is not a workflow permission — it is
**remote code execution as the server**, and anybody who can reach the flow can
trigger it.

This matters most for exactly the product this app is: a console where "designers
can add new flows" is the whole point. In m8flow terms, whoever can publish a
process model owns the backend.

**What this app does about it:** the publish screen says so plainly, and
publishing stays behind the library's admin-only check. That is mitigation, not a
fix.

**Suggestions**, roughly in order of value:

1. Say this explicitly in `doc/api.md` and `doc/gaps.md`. Right now nothing warns
   an implementer, and the natural reading of "designers upload BPMN" is that it
   is a data operation.
2. Offer a restricted script engine — SpiffWorkflow supports supplying one — and
   make it the default, with the permissive engine opt-in.
3. Consider running script tasks out of process for hosts that accept untrusted
   diagrams.

*Evidence:* reproduced via `POST /flows` then `POST /flows/{id}/start`

---

## 2. Lane ownership can be widened but never revoked — *high*

`_sync_lane_owner_group_assignments` only ever adds. Publishing a new version
with a **narrower** lane-owner list does not take anybody off the lane, so a host
cannot remove a leaver, or correct an over-permissive first publish, by
republishing.

There is no public API for group membership, so the app now reconciles the
library's own `user_group_assignment` rows itself: after every import it makes
each lane's membership exactly the set that was named, adding what is missing and
deleting what is not. It only touches rows for users of the publishing tenant.

Two details of the lane model that made this delicate:

* **A lane's group id is a hash of the lane name alone** —
  `resolve_lane_assignment_id` — so the group is global. A lane called "Approver"
  is one group shared by every company *and* by every flow that uses that name.
  Two flows in one company with the same lane name therefore cannot have
  different owners.
* Task assignment intersects that group with the tenant's own users
  (`_users_in_lane_group` filters by tenant), so work never actually crosses
  companies. The global group is a modelling smell rather than a leak — but it is
  why the reconciliation has to be careful to delete only its own tenant's rows.

**Suggestion:** make the sync reconcile, scope lane groups per tenant (and
ideally per process model), and expose lane membership through a public command
so hosts are not editing library tables to do something this routine.

*Evidence:* `src/flowdesk/lane_owners.py`;
`tests/test_flows.py::test_republishing_narrows_a_lane`,
`::test_lane_owners_are_per_company`

---

## 3. `form_file_name` exists but is never populated — *medium*

`HumanTaskModel` has `form_file_name` and `ui_form_file_name` columns, and the
BPMN carries `formJsonSchemaFilename` in `spiffworkflow:properties`. The library
writes `None` to both, unconditionally
(`workflow_runtime.py:1909`), and never reads the extension property.

A generic console therefore has to parse the diagram itself to find out which
form a task wants — which means re-implementing part of the BPMN parser in the
host, and keeping it in step with whatever the modeller emits.

**Suggestion:** populate the columns from the extension properties. The schema
already has the right shape; only the wiring is missing. Half-present features
are worse than absent ones, because an implementer reasonably assumes the column
is filled in.

*Evidence:* `src/flowdesk/bpmn_inspect.py` exists entirely to work around this

---

## 4. Nothing in the public API lists what is published — *medium*

There is no query for process definitions. A console whose main screen is "here
are the flows you can start" cannot be built on the public API at all: this app
imports `BpmnProcessDefinitionModel` and writes its own `select()`.

Related gaps in the read surface, all needed by an operations screen:

* no query for a definition by identifier, or for its versions
* no query for task history (only `GetPendingTasksQuery`, which returns open work)
* `ListProcessInstancesQuery` takes a status but has no pagination or ordering, so
  a host must fetch every instance and sort in memory

**Suggestion:** a small read-side addition — `ListProcessDefinitionsQuery`,
`GetProcessDefinitionQuery`, `GetProcessInstanceTasksQuery` — would let a console
stay on the public contract.

*Evidence:* `src/flowdesk/main.py`, `definitions_for`

---

## 5. Process instance ids are how a caller names a flow, but definitions are not — *low*

Starting an instance needs `bpmn_process_definition_id` (a database id) **and**
`bpmn_process_id` (the id inside the XML). A console has both, but the pairing is
easy to get wrong and nothing validates that the two refer to the same process —
mismatching them fails deep inside the runtime rather than at the command
boundary.

**Suggestion:** derive `bpmn_process_id` from the definition, or validate the pair
up front.

*Evidence:* `src/flowdesk/main.py`, `start_flow`

---

## 7. Three library roles cannot express four product roles — *medium*

This app has four roles: admin, editor, reviewer, submitter. The library has
exactly three — `user`, `manager`, `admin` — and `process_definition.import` is
admin-only. So an **editor**, whose whole job is publishing flows, must be given
the library's *admin* role, which also grants suspend, resume, terminate and
retry.

The product wants an editor who publishes but does not operate running
instances. The library has no way to say that, so the app keeps its own
capability set and checks it before every lifecycle call. The engine would
happily allow what the app forbids, which means the two permission models can
drift apart — and only one of them is enforced by the engine.

**Suggestion:** let a host grant individual command keys to a role without
handing over the whole admin set. `grant_command_permissions_to_group` already
does exactly this; it is just not reachable through a public API, and
`ensure_v1_role` overwrites nothing when re-run, so there is no supported way to
build a custom role.

*Evidence:* `src/flowdesk/seed.py` capability sets;
`tests/test_auth.py::test_an_editor_publishes_but_does_not_operate`

---

## 10. Lifecycle preconditions are enforced but not published — *low*

Each lifecycle command has a precondition, and they differ in ways that are not
guessable: suspend needs a non-terminal, non-suspended run; resume needs a
suspended one; terminate needs a non-terminal one; **retry needs an errored one
specifically**, even though `error` is itself a terminal status. The model has
`has_terminal_status()` and `terminal_statuses()` but nothing that answers "what
can I do to this instance now".

A UI that offers a button the engine will refuse is a bug, so a host has to
either read the service source (which is what we did -- the rules are at
`process_instances.py:264, 361, 407, 521`) or discover them by catching
`InvalidStateError` in production.

**Suggestion:** put `can_suspend()`, `can_resume()`, `can_terminate()` and
`can_retry()` on `ProcessInstanceModel` next to the predicates already there, or
document the four preconditions in `doc/api.md`.

*Evidence:* `src/flowdesk/main.py`, `allowed_actions`;
`tests/test_flows.py::test_only_the_actions_the_engine_accepts_are_offered`

---

## 9. A run's whole shape is recorded, and no query returns it — *medium*

**Corrects an earlier reading of this finding.** The first version said a run's
future steps did not exist in the database. They do. `task` holds a row for every
step of a run from the moment it starts, joined to `task_definition` for the
element id, name and type, and its `state` column is SpiffWorkflow's own:
`COMPLETED`, `READY`, `FUTURE`, `MAYBE`, `TERMINATED`. That is a complete and
authoritative answer to "where has this got to", including steps not yet reached
and branches that will never be taken.

What is missing is any way to *ask* for it. No query in `api` returns tasks —
`GetPendingTasksQuery` returns only open human tasks — so a host that wants a
progress view has to import `TaskModel` and `TaskDefinitionModel` and query them
itself, which is exactly what this app now does.

Two things a caller still has to supply:

* **Order.** `task` records what ran, not where it sits in the diagram, and
  `start_in_seconds` is the same value for every step of a fast run. Reading the
  diagram's sequence flows is the only way to put the steps in the order a person
  would recognise (`bpmn_inspect._in_run_order`).
* **"Never happened" vs "not yet".** On a finished run, a branch that was not
  taken is often still `MAYBE`, not `TERMINATED`, so the run's status has to be
  overlaid on the step's state.

The related half the library answers well: `human_task_user` records exactly
which people may act on an open task and why (`lane_owner`, `lane_assignment`,
`process_initiator`, `manual`), which is more than most engines expose.
`human_task_user.added_by` deserves a mention in `doc/api.md` — it is the single
most useful field for a worklist UI and is documented nowhere.

**Suggestion:** a read query returning a run's steps with their states, and a
definition's task specs (#4). Both are already in the tables; only the door is
missing.

*Evidence:* `src/flowdesk/main.py`, `engine_states` and `progress_for`;
`tests/test_flows.py::test_the_trace_shows_steps_no_person_ever_touches`

---

## 11. `task.json_data` is dead: SpiffWorkflow stores deltas — *medium*

`TaskModel` has a `json_data_hash`, and `_upsert_task_model_from_payload` fills it
from the serialised task's `data` key. Under SpiffWorkflow 3's serialiser that key
is `{}` for every task of every run, because a task's contribution is recorded as
a **delta** against its parent:

```json
{"task_spec": "Activity_0qpzdpu", "state": 64, "data": {},
 "delta": {"updates": {"spiff__Activity_0qpzdpu_result": {"http_status": 200, "body": [...]}},
           "deletions": []}}
```

Every `task.json_data_hash` in this app's database is
`44136fa355b3678a…`, the sha256 of `{}`. The column is not wrong so much as
inert.

The data is not lost -- the delta survives inside `task.properties_json`, which
the library stores verbatim -- so a host can read
`properties_json["delta"]["updates"]` and get exactly what each step contributed:
a form's fields, a script's variables, a service call's response. That is a
better answer than anything the API offers, and it is reachable only by knowing
SpiffWorkflow's serialisation format.

The public route, `GetProcessInstanceMetadataQuery`, returns only what a host has
itself written to metadata, and stringifies it. A flow whose only step is an HTTP
call reports no data at all through it while the response sits in the database in
full. Worse, on a *running* instance the workflow-level `data` is empty too: the
value is only in the delta until the run completes, so "show the user what the
service call returned" is impossible through the public API at exactly the moment
it matters.

**Suggestion:** either populate `task.json_data` with the task's effective data
(parent's data plus its delta), or drop the column and expose a query that
returns a run's steps with what each contributed.

*Evidence:* `src/flowdesk/main.py`, `engine_states`; every `json_data_hash` in
`flowdesk.db` equals the hash of `{}`

---

## 12. `instructionsForEndUser` is parsed and ignored — *medium*

`spiffworkflow:instructionsForEndUser` is how a modeller says what a step should
show the person doing it. It is the entire content of a BPMN manual task, and
m8flow's own connector templates lean on it: the "http connector usage" template
in *Workflows - QA* is a GET followed by a manual task whose instructions render
the response as a markdown table.

The string `instructionsForEndUser` does not appear anywhere in
`m8flow-bpmn-core`. The element parses without complaint and is dropped, so a
host is handed a manual task named "Display Response" with no way to learn what
it is meant to display. This app now reads the element out of the stored diagram
itself and renders it with Jinja against the run's collected data, which is the
convention those templates are written to.

The engine handles the manual task itself correctly — the run stops at
`user_input_required`, a human task is created, and completing it with an empty
payload finishes the run. It is only the modeller's text that is lost.

**Suggestion:** carry `instructionsForEndUser` onto the task, ideally rendered.
The parser already walks the extension elements to find
`serviceTaskOperator`; this is the same trip.

*Evidence:* `src/flowdesk/bpmn_inspect.py`, `_instructions`;
`src/flowdesk/main.py`, `render_instructions`;
`tests/test_flows.py::test_a_manual_task_is_a_person_step_and_keeps_its_instructions`

---

## 13. The connector registry is a context manager, so every path has to remember it — *high*

`service_task_registry_scope` installs connectors for the duration of a block.
That is a clean seam, and it is also a trap: **every** code path that can advance
a workflow has to install them, not just the request handlers.

A timer is an ordinary way to arrive at a service task. The host's scheduler
poller — which is what the library asks for, since it never decides when a timer
fires — runs `run_due_scheduler_jobs` far away from any request, and this app had
no registry installed there. The result:

```
NotFoundError: No service task connector is registered for 'log'
ServiceTaskExecutionError: Service task 'log/Write' failed for process instance 23
```

Nothing in the app's tests could have caught it: every other flow reaches its
service tasks from a request. Only the shape "wait on a timer, then call a
service" goes through the poller, and the capability tour is the first flow here
with it. The run went to `error` and stayed there.

The fix is four lines — poll per tenant inside `service_tasks(session, tenant)` —
but finding it took reading the traceback in the server log, because the failure
surfaces nowhere near the cause.

**Suggestion:** let a registry be *registered* for a process, not only scoped
around a call — or have `run_due_scheduler_jobs` take the registry as an
argument, so the type system asks the question. Failing that,
`doc/api.md` should say plainly that the scheduler needs the same connectors as
the request path.

*Evidence:* `src/flowdesk/scheduler.py`, `run_due_jobs_once`;
`tests/test_flows.py::test_the_capability_tour_runs_every_construct_the_library_supports`
(fails without it)

---

## 8. Editing a user means writing the library's own table — *medium*

Letting somebody change their display name or email address is an ordinary
requirement, and there is no API for it: `doc/gaps.md` lists user create, update
and delete as missing. So the app imports `UserModel` and assigns to it
directly.

That works, but it puts the host inside the library's schema for a routine
operation, and it is quietly dangerous: `UserModel.service` is the field the
library string-parses to decide tenant membership (#3 in app #1's findings). A
host that exposes "edit your profile" over the whole model — the obvious
implementation — would let anybody move themselves into another company by
editing one text field. This app allows exactly two fields for that reason.

Credentials are the app's problem too, which is reasonable, but it means every
host reimplements password hashing and session handling.

**Suggestion:** an `UpdateUserCommand` covering the safe fields, with `service`
and `service_id` not settable through it. Even a documented note saying "these
two fields are security-critical, do not expose them" would help.

*Evidence:* `src/flowdesk/main.py`, `update_profile`;
`tests/test_profile.py::test_editing_a_profile_does_not_move_you_between_companies`

---

## 6. Confirmed again from app #1

These reproduced here unchanged, which suggests they are structural rather than
particular to one app:

* **Service-task failures cannot be audited from inside the caller's
  transaction.** Same buffer-then-write-after-rollback dance as TimeOff
  (`src/flowdesk/connectors.py`).
* **Script-task variables never reach process metadata.** The expense flow's
  script sets `decision = "approved"`; it never appears in the instance data, so
  the console cannot show what the automatic branch decided.
* **V1 roles are not a hierarchy.** `reviewer` (manager) cannot start a flow while
  `analyst` (user) can — pinned in
  `tests/test_flows.py::test_a_reviewer_cannot_start_a_flow`.
* **The read side has no authorization.** Every query trusts the tenant id it is
  given, so `identity.py` remains load-bearing.

---

## What worked well

* **A completely generic host is possible.** Three bundled flows plus anything a
  designer uploads run through one code path, with no per-flow code. The library
  genuinely does not care what the diagram contains.
* **BPMN coverage held up.** Exclusive and parallel gateways, DMN decision
  tables, script tasks, interrupting boundary timers and service tasks all worked
  first try, including a parallel join that correctly waited for both branches.
* **The connector seam is excellent.** Two connectors serving four operations,
  registered per request, with no library changes.
* **The error hierarchy carried the whole API.** Mapping `BpmnCoreError`
  subclasses onto status codes covers every failure the console can produce.

---

## Ranked asks for the library team

1. Document — and ideally sandbox — script-task execution (#1). It changes what
   the publish permission means.
2. Make lane ownership revocable (#2).
3. Make the connector registry impossible to forget on the scheduler path (#13).
4. Populate `form_file_name` (#3), or remove the columns.
5. Add the read queries a console needs: what is published (#4), a run's steps
   and their states (#9), and what each step contributed (#11). All three are
   already in the tables; a host has to import the ORM models and understand
   SpiffWorkflow's delta format to reach them.
6. Carry `instructionsForEndUser` through to the task (#12) — without it a manual
   task is a step with no content.
7. Make roles composable so a host can express its own (#7).
8. Add a safe user-update command (#8).
9. Publish the lifecycle preconditions (#10).
