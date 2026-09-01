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

## 9. A run's future is invisible; only its past is queryable — *medium*

"Where has this got to, and who owes the next move" is the first question anybody
asks about a running process. The second half the library answers well:
`human_task_user` records exactly which people may act on an open task and why
(`lane_owner`, `lane_assignment`, `process_initiator`, `manual`), which is more
than most engines expose.

The first half it cannot answer at all. A task exists only once control reaches
it, so a run sitting at step 1 of 4 has one row and no notion of the other three.
There is no query for "the steps of this definition" either (#4), so a host that
wants a progress view has to parse the diagram itself and match it against the
tasks that exist. Distinguishing "not reached yet" from "skipped down another
branch" then needs the instance status as well.

`human_task_user.added_by` deserves a mention in `doc/api.md` — it is the single
most useful field for a worklist UI and is not documented anywhere.

**Suggestion:** a read query returning a definition's task specs, so a host can
line up progress without a second BPMN parser. The information is already in the
parsed spec the runtime holds.

*Evidence:* `src/flowdesk/main.py`, `progress_for`;
`tests/test_flows.py::test_a_run_shows_its_whole_shape_and_who_is_next`

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
3. Populate `form_file_name` (#3), or remove the columns.
4. Add the four read queries a console needs (#4).
5. Make roles composable so a host can express its own (#7).
6. Add a safe user-update command (#8).
