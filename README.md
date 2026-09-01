# Flowdesk

A workflow console. Designers publish BPMN diagrams; everybody else picks a flow,
starts it and works through its tasks.

Nothing about any particular flow is compiled in, and nothing is bundled. The
console reads what it needs out of the diagram — lanes, steps, which form each
step wants, which decisions and service tasks it calls — and the engine runs
whatever it is given. Upload a diagram nobody has seen before and it is runnable
immediately.

Built on [`m8flow-bpmn-core`](../m8flow-bpmn-core), consumed as a built wheel.

## Running it

```bash
# backend on :8020
uv sync
uv run flowdesk

# frontend on :5173
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** and sign in with any account from
[Signing in](#signing-in) below.

**The console starts empty.** No flows are bundled — nothing exists until an
`admin` or `editor` publishes one, and what they publish belongs to their company
alone. See [Your first flow](#your-first-flow).

| Variable | Default |
|---|---|
| `FLOWDESK_DATABASE_URL` | `sqlite+pysqlite:///./flowdesk.db` |
| `FLOWDESK_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `FLOWDESK_SECRET_KEY` | `flowdesk-development-secret` — signs session tokens |
| `FLOWDESK_SESSION_HOURS` | `12` |
| `VITE_API_BASE` | `http://127.0.0.1:8020` |

Starting over: stop the backend, delete `flowdesk.db`, start again.

## Who can do what

| Account | Publish flows | Start a flow | Do tasks | Hold / cancel / retry | See everyone's runs |
|---|---|---|---|---|---|
| `admin` — Alex Admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| `editor` — Erin Editor | ✓ | ✓ | ✓ | | ✓ |
| `reviewer` — Riya Reviewer | | | ✓ | | ✓ |
| `submitter` — Sam Submitter | | ✓ | ✓ | | own only |

Two of those rows are the library's doing and two are this app's:

- **`reviewer` cannot start a flow** because V1 RBAC grants `process.start` to
  `user` and `admin` but not to `manager`. The engine refuses it.
- **`editor` cannot hold or cancel a run** even though the engine would allow it.
  Publishing is admin-only in the library, so an editor has to hold the library's
  *admin* role — which also grants suspend/resume/terminate. Keeping an editor out
  of the lifecycle is a check this app adds. The library's three roles cannot
  express four product roles; see FINDINGS #7.

## Signing in

Pick a **company**, then a username and password.

### Demo accounts

**Both companies have all four accounts, and every password is the same as the
username.** So `admin` / `admin`, `editor` / `editor`, and so on.

| Company | Username | Password | Person | Job title |
|---|---|---|---|---|
| Northwind Traders | `admin` | `admin` | Alex Admin | Workspace Administrator |
| Northwind Traders | `editor` | `editor` | Erin Editor | Process Designer |
| Northwind Traders | `reviewer` | `reviewer` | Riya Reviewer | Approver |
| Northwind Traders | `submitter` | `submitter` | Sam Submitter | Team Member |
| Initech | `admin` | `admin` | Alex Admin | Workspace Administrator |
| Initech | `editor` | `editor` | Erin Editor | Process Designer |
| Initech | `reviewer` | `reviewer` | Riya Reviewer | Approver |
| Initech | `submitter` | `submitter` | Sam Submitter | Team Member |

The two companies share the same four usernames deliberately: they are separate
accounts with separate data, so if tenant scoping ever leaked it would show up as
the wrong person's work rather than a tidy error. Signing in as Northwind's
`admin` shows nothing belonging to Initech.

**Which account to use for what:**

| To try this | Sign in as |
|---|---|
| Browse and start a flow, fill in a form | `submitter` |
| Approve something — the second step of a flow | `reviewer` |
| Upload a new BPMN diagram | `editor` |
| Hold, cancel or retry a run; see the activity log | `admin` |

A quick tour: sign in as `submitter`, start **Expense Approval**, enter an amount
over 100, submit. Sign out, sign in as `reviewer`, and the approval is waiting in
**My work**. Enter 100 or less instead and the decision table approves it without
a reviewer at all.

### Your profile

Anybody can change their own **name**, **email** and **password** from the user
menu in the top-right → *Profile*. Roles are not editable there — an
administrator sets those.

Changing a password signs every other session out, and the session doing the
changing gets a fresh token so it stays signed in. New passwords must be at
least 8 characters.

If you change a demo password and want the documented ones back: stop the
backend, delete `flowdesk.db`, start it again.

### How the login works

There is no identity provider here, so logins are a password form against the
app's own credential table: PBKDF2 hashes, and an HMAC-signed token carrying the
tenant, the username and an expiry. **The tenant is inside the signed token**, so
a caller cannot name a tenant of their choosing — which matters, because the
library trusts whatever tenant id it is handed on the read side.

Sessions last 12 hours (`FLOWDESK_SESSION_HOURS`) and the token is kept in
`localStorage`, so a reload does not sign you out.

These are demo credentials in a demo app. Swapping this for real OIDC means
replacing `resolve_token` and the login route, and `FLOWDESK_SECRET_KEY` must be
set to something private in anything resembling a real deployment.

> **Publishing a flow runs its code.** A diagram's script tasks execute Python
> inside the server process, and its service tasks make real outbound calls. That
> makes the publish permission as powerful as server access — see FINDINGS #1.

## Screens

| | |
|---|---|
| **Flows** | Every published flow, with what is inside it — steps and lanes, decision tables, gateways, timers, service operations — and a Start button |
| **My work** | Your open tasks. Opening one renders its form from the JSON Schema the diagram asked for, or a free-form editor if it named none |
| **Runs** | Every instance, filterable by status. Click a row for the detail panel — see below |
| **Publish** | Designers only: upload a diagram, see what the console found in it, assign lane owners, supply form schemas, publish |
| **Activity** | Every connector call the workspace's flows have made |
| **Profile** | Your own name, email and password (user menu, top-right) |

### Following a run

The **Runs** list names the step and the person each run is waiting on, without
opening anything. Click any row for the detail panel, which shows:

- **Next action** — one line: *"Waiting on Review Request — Riya Reviewer"*
- **The flow** — every step of the diagram in order, marked done / waiting now /
  still to come, with who did each one and when, and for the waiting step the
  actual people who can act on it and why they have it
- Data collected so far, service-task calls, the full engine event log, and hold
  / release / retry / cancel for operators

Steps a run never reached are shown as *not needed — the run went another way*,
so a flow that skipped its approver reads correctly rather than looking stuck.

**What comes from where.** Who owes the next move is the library's own data:
`human_task_user` records exactly which people may act on an open task and why
(`lane_owner`, `process_initiator`, and so on). The steps a run has *not reached
yet* exist nowhere in the database — the engine only materialises a task when
control arrives at it — so the console reads the shape out of the stored diagram
and matches it against the tasks that exist. That is the one gap the app fills.

The shell follows m8flow's: MUI, a collapsible icon rail, a light/dark switch and
the company shown in the header — all persisted in localStorage. Task forms use
`@rjsf/mui`, the same react-jsonschema-form setup m8flow renders its forms with,
so a schema that works there works here.

## Your first flow

Sign in as `admin` or `editor`, go to **Publish**, and upload a `.bpmn` file. The
console reads the diagram and shows you what it found; you then assign each lane
and supply a JSON Schema for any form the diagram names.

Four example diagrams ship in [`examples/`](./examples), ready to upload:

| File | Shape |
|---|---|
| `two_step_request.bpmn` | **Start here.** One person fills a form, somebody else approves or rejects it. Two lanes, two forms, one gateway |
| `expense_approval.bpmn` + `.dmn` | Adds a decision table: small claims skip the approver entirely |
| `incident_response.bpmn` | Two people work in parallel; the flow waits for both |
| `access_request.bpmn` | If the reviewer does not respond in time, the work escalates to another lane |

Each has a matching `.forms.json` holding the schemas its steps ask for — paste
the relevant one into the form boxes on the publish screen.

### A form, then an approval

That is the commonest shape and `two_step_request.bpmn` is exactly it:

```
Requester   Submit Request ──┐        (form: subject, details, urgency, needed by)
                             ↓
Approver                Review Request  (form: approved / rejected + comment)
                             ↓
                        Approved? ──── approved ──→ done
                                  └──── rejected ──→ done
```

Publish it with **Requester → submitter** and **Approver → reviewer**, then:

1. Sign in as `submitter`, **Flows → Start**, fill the form, submit.
2. It leaves your worklist entirely and appears in the reviewer's.
3. Sign in as `reviewer`, open the task — **what the requester submitted is shown
   above the decision form**, so you can see what you are approving.
4. Approve or reject. The gateway routes on `decision` and the run completes.

To build your own, that diagram is the template. The three things that make it
work are:

- **A lane per person** — the lane is what decides whose worklist a step lands in.
- **`formJsonSchemaFilename`** on each user task, naming the schema you upload
  with it.
- **A field name shared between the form and the gateway** — the review form
  writes `decision`, and the sequence flows test `decision == "approved"`.
  Anything a form collects becomes available to later steps.

Add more steps by adding more user tasks and lanes; the console needs no changes.

### Lanes decide who sees what

Every lane must be assigned to at least one person before a flow can be
published; nothing is pre-selected, and publishing is refused until each lane has
an owner. Only those people see that step's tasks.

Assignments are **exact**. Republishing with a narrower list genuinely removes
the people you dropped — which the library does not do on its own, so the app
reconciles the lane groups itself (FINDINGS #2).

One caveat from how the library models lanes: a lane's group is keyed on the
lane *name*, so two flows in the same company that both use a lane called
"Approver" share one set of owners. Give lanes distinct names if two flows need
different approvers.

### Flows are per company

A published flow exists only in the company that published it. Signing in to
Initech shows nothing Northwind published, and its ids are not even resolvable
there — starting one returns 404. Publishing the same diagram in both companies
gives two independent flows with their own lane owners and their own runs.

## Service task connectors

Diagrams call operations by m8flow's `<connector>/<command>` convention, served
in-process:

| Operation | |
|---|---|
| `log/Write`, `log/Trace` | Records the task's parameters in the activity log |
| `http/GetRequest`, `http/PostRequest` | Real outbound HTTP over the standard library |

The publish screen warns when a diagram calls an operation no connector here
serves, before it is imported. Adding a connector is a class with two methods —
see [`connectors.py`](src/flowdesk/connectors.py).

## Layout

| Path | |
|---|---|
| `src/flowdesk/main.py` | The API: flows, runs, tasks, activity |
| `src/flowdesk/auth.py` | Password hashing and signed session tokens |
| `frontend/src/Profile.tsx` | Editing your own name, email and password |
| `src/flowdesk/seed.py` | Companies, the four accounts, roles and capabilities |
| `src/flowdesk/bpmn_inspect.py` | Reads lanes, steps, forms, decisions and timers out of a diagram |
| `src/flowdesk/connectors.py` | The service-task connectors and their registry scope |
| `src/flowdesk/store.py` | App-owned tables: published files and the activity log |
| `src/flowdesk/lane_owners.py` | Makes lane membership match exactly what the publisher assigned |
| `examples/` | Example diagrams to upload, with their form schemas |
| `frontend/src/theme.ts` | MUI theme shaped after m8flow's own |
| `frontend/src/App.tsx` | App shell: collapsible icon nav, theme switch, user menu |
| `frontend/src/Login.tsx` | Sign-in |
| `frontend/src/TaskForm.tsx` | `@rjsf/mui` form from the diagram's JSON Schema, with a free-form fallback |
| `frontend/src/Publish.tsx` | The publishing screen |

## Tests

```bash
uv run pytest                    # 50 tests
cd frontend && npm run build     # type-check and production build
cd frontend && node scripts/ui-check.mjs   # drives the real UI in a browser
```

The last one needs both servers running. It signs in, opens a task form, checks
the dialog is actually centred, clicks a Runs row and asserts the detail panel
names the step and person the run is waiting on — then leaves screenshots in
`frontend/ui-shots/`. It exists because two layout bugs shipped that no unit
test could catch.

Covers all four example diagrams end to end — DMN routing both ways, a parallel
join waiting for both branches, a boundary timer actually firing — plus
publishing a brand-new flow and running it, every permission boundary, lane
assignment actually restricting and narrowing, company isolation, and the login
path: wrong passwords, tampered
tokens, expired tokens, the fact that a failed login says the same thing whether
or not the account exists, and profile editing — including that changing a
password invalidates other sessions and cannot move you between companies.

## Findings

[FINDINGS.md](./FINDINGS.md) — six findings specific to building a *generic* host,
including one critical security issue and one authorization defect.
