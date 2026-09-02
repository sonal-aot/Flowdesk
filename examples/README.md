# Example flows

Nothing here is bundled into the app — a flow exists only once somebody
publishes it. Publish these from the **Publish** tab, or let the tests do it.

| File | What it is for |
|---|---|
| `capability_tour.bpmn` | Everything the library can currently run, in one flow |
| `two_step_request.bpmn` | The smallest useful shape: one person fills a form, another decides |
| `expense_approval.bpmn` | A decision table routing past an approver |
| `incident_response.bpmn` | Two people working at once |
| `access_request.bpmn` | An approval that escalates when nobody answers |
| `http_connector_usage.bpmn` | m8flow's own connector template: a GET, then a manual task that displays the response |

A `.bpmn` uses the `.forms.json` and `.dmn` beside it, if they exist.

## The capability tour

`capability_tour.bpmn` + `capability_tour.dmn` + `capability_tour.forms.json`.
Three lanes — Requester, Approver, Finance — and every construct below has been
started and driven to an end event, on all four of its paths.

| Construct | In the diagram | Proves |
|---|---|---|
| `laneSet` / `lane` | Requester, Approver, Finance | Assignment: each lane's owner is who gets that step |
| `userTask` + form | Submit Request, Approve Request, Check Budget | JSON Schema forms named by `formJsonSchemaFilename` |
| `scriptTask` | Score Request, Approve By Policy | Python, evaluated against the run's data |
| `businessRuleTask` + DMN | Apply Policy | A decision table's output steering the flow |
| `exclusiveGateway` | Needs review?, Approved?, Decided | `conditionExpression`, and the same gateway used as a merge |
| `parallelGateway` | Review in parallel / Both done | Two branches open at once; the join waits for both |
| `boundaryEvent` timer | No answer in 10 minutes | Interrupting: cancels the approval and escalates it |
| `intermediateCatchEvent` timer | Cooling-off (5s) | A run parking itself until the host's poller releases it |
| `serviceTask` | Record Outcome, Trace Rejection | Connectors (`log/Write`, `log/Trace`) with Python parameters |
| `manualTask` + instructions | Review Outcome | A step with no form, whose `instructionsForEndUser` renders the run's data |
| Two end events | Closed, Rejected | Which way a run went is on the record |

### The four paths

Amount and urgency on the first form decide which one you get.

| Enter | What happens |
|---|---|
| **50, low** | Inside policy: the DMN routes past both reviewers, a script task approves it, and it still runs the timer, the service task and the manual task |
| **250, high** | Urgent: parallel review by the Approver and Finance, then approved |
| **900, normal** + reject | Parallel review, rejected at the gateway, `log/Trace`, ends at **Rejected** |
| **800, normal**, then wait | Nobody answers the approval; the boundary timer cancels it and hands it to Finance as **Escalated Approval** |

The escalation timer is `PT10M` so the ordinary path works. To watch it fire,
edit the flow and change `'PT10M'` to `'PT10S'` — the tests do exactly that.

### What is deliberately not in it

Not because the diagram avoids them — because the library does not support them,
or nothing here has proved that it does:

- **`callActivity` / `subProcess`** — never exercised by the library's own
  fixtures, and untested here
- **Message and signal events** — no correlation machinery in the library
- **`inclusiveGateway`** — parses, but no test anywhere takes two of its branches
- **Multi-instance / loop markers** — untried
- **A timer start event** — the library has a `timer_start` scheduler job type,
  so it exists, but a flow that starts itself has no place in a console where
  somebody presses Start

`instructionsForEndUser` is read by *this app* out of the stored diagram, not by
the library, which drops the element. See FINDINGS #12.
