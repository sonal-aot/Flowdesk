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

Open **http://localhost:5173** and pick an account. Three example flows are
published into both companies on startup, so there is something to run
immediately.

| Variable | Default |
|---|---|
| `FLOWDESK_DATABASE_URL` | `sqlite+pysqlite:///./flowdesk.db` |
| `FLOWDESK_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `VITE_API_BASE` | `http://127.0.0.1:8020` |

Starting over: stop the backend, delete `flowdesk.db`, start again.

## Who can do what

Roles are the library's own V1 RBAC — the engine enforces them, not this app.

| Account | Role | Publish flows | Start a flow | Do tasks | Hold / cancel / retry |
|---|---|---|---|---|---|
| Dana Designer | admin | ✓ | ✓ | ✓ | ✓ |
| Amir Analyst | user | | ✓ | ✓ | |
| Rosa Reviewer | manager | | | ✓ | |
| Aki Auditor | manager | | | ✓ | |

`reviewer` being unable to start a flow is the library's behaviour, not a choice:
V1 grants `process.start` to `user` and `admin` but not to `manager`.

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
| `src/flowdesk/bpmn_inspect.py` | Reads lanes, steps, forms, decisions and timers out of a diagram |
| `src/flowdesk/connectors.py` | The service-task connectors and their registry scope |
| `src/flowdesk/store.py` | App-owned tables: published files and the activity log |
| `src/flowdesk/seeds/` | The three bundled flows, with decision table and form schemas |
| `frontend/src/JsonForm.tsx` | Renders a task form from JSON Schema, with a free-form fallback |
| `frontend/src/Publish.tsx` | The publishing screen |

## Tests

```bash
uv run pytest                    # 17 tests
cd frontend && npm run build     # type-check and production build
```

Covers all three bundled flows end to end — DMN routing both ways, a parallel
join waiting for both branches, a boundary timer actually firing — plus
publishing a brand-new flow and running it, permission boundaries, lane
restriction, and company isolation.

## Findings

[FINDINGS.md](./FINDINGS.md) — six findings specific to building a *generic* host,
including one critical security issue and one authorization defect.
