# Flowdesk

A workflow console. Designers publish BPMN diagrams; everybody else picks a flow,
starts it and works through its tasks.

Nothing about any particular flow is compiled in. The console reads what it needs
out of the diagram — lanes, steps, which form each step wants, which decisions
and service tasks it calls — and the engine runs whatever it is given. Upload a
diagram nobody has seen before and it is runnable immediately.

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
[Signing in](#signing-in) below. Three example flows are published into both
companies on startup, so there is something to run immediately.

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
| **Runs** | Every instance, filterable by status. The detail panel shows steps, collected data, service-task calls and the full event log, plus hold / release / retry / cancel for operators |
| **Publish** | Designers only: upload a diagram, see what the console found in it, assign lane owners, supply form schemas, publish |
| **Activity** | Every connector call the workspace's flows have made |
| **Profile** | Your own name, email and password (user menu, top-right) |

The shell follows m8flow's: MUI, a collapsible icon rail, a light/dark switch and
the company shown in the header — all persisted in localStorage. Task forms use
`@rjsf/mui`, the same react-jsonschema-form setup m8flow renders its forms with,
so a schema that works there works here.

## The bundled flows

| Flow | Exercises |
|---|---|
| Expense Approval | DMN decision table, exclusive gateway, script task, service task, two forms |
| Incident Response | Parallel gateway split and join, three lanes, three forms |
| Access Request | Interrupting boundary timer escalating to another lane |

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
| `src/flowdesk/seeds/` | The three bundled flows, with decision table and form schemas |
| `frontend/src/theme.ts` | MUI theme shaped after m8flow's own |
| `frontend/src/App.tsx` | App shell: collapsible icon nav, theme switch, user menu |
| `frontend/src/Login.tsx` | Sign-in |
| `frontend/src/TaskForm.tsx` | `@rjsf/mui` form from the diagram's JSON Schema, with a free-form fallback |
| `frontend/src/Publish.tsx` | The publishing screen |

## Tests

```bash
uv run pytest                    # 43 tests
cd frontend && npm run build     # type-check and production build
```

Covers all three bundled flows end to end — DMN routing both ways, a parallel
join waiting for both branches, a boundary timer actually firing — plus
publishing a brand-new flow and running it, every permission boundary, lane
restriction, company isolation, and the login path: wrong passwords, tampered
tokens, expired tokens, the fact that a failed login says the same thing whether
or not the account exists, and profile editing — including that changing a
password invalidates other sessions and cannot move you between companies.

## Findings

[FINDINGS.md](./FINDINGS.md) — six findings specific to building a *generic* host,
including one critical security issue and one authorization defect.
