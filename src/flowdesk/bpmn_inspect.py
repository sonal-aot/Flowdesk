"""Read a BPMN file well enough to run it from a generic console.

The console cannot hardcode anything about a flow, so it has to answer three
questions from the XML alone:

* what is the process id, and which lanes does it have (so the publisher can say
  who owns each one)
* which user tasks exist and which form does each one want -- the library stores
  a ``form_file_name`` column but never fills it in, so the reference has to be
  read here
* what else is in there -- decisions, service tasks, timers -- so the publisher
  can be told what the flow will need before they run it
"""

from __future__ import annotations

from dataclasses import dataclass, field

from defusedxml import ElementTree
from m8flow_bpmn_core.errors import ValidationError

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
SPIFF = "{http://spiffworkflow.org/bpmn/schema/1.0/core}"

FORM_SCHEMA_PROPERTY = "formJsonSchemaFilename"
FORM_UI_PROPERTY = "formUiSchemaFilename"


@dataclass(frozen=True, slots=True)
class UserTask:
    element_id: str
    name: str
    lane: str | None
    form_schema: str | None
    form_ui_schema: str | None
    #: `instructionsForEndUser`: what the modeller wants shown on this step. A
    #: Jinja template over the run's data, so it is rendered, not printed.
    instructions: str = ""


#: Every flow node worth showing in a run's trace, and what to call its kind.
#: Sequence flows, lanes and data objects are not steps, so they are absent.
STEP_KINDS: dict[str, str] = {
    "userTask": "person",
    "manualTask": "person",
    "serviceTask": "service",
    "scriptTask": "script",
    "businessRuleTask": "decision",
    "callActivity": "subflow",
    "subProcess": "subflow",
    "sendTask": "service",
    "receiveTask": "wait",
    "task": "task",
    "startEvent": "start",
    "endEvent": "end",
    "intermediateCatchEvent": "wait",
    "intermediateThrowEvent": "event",
    "boundaryEvent": "boundary",
    "exclusiveGateway": "branch",
    "parallelGateway": "branch",
    "inclusiveGateway": "branch",
    "eventBasedGateway": "branch",
}

#: What to call an unnamed node, rather than dressing up its element id.
UNNAMED: dict[str, str] = {
    "start": "Start",
    "end": "End",
    "branch": "Branch",
    "wait": "Wait",
    "boundary": "Timer",
    "event": "Event",
}


@dataclass(frozen=True, slots=True)
class Step:
    """One node of the diagram, in the order a run reaches it."""

    element_id: str
    name: str
    kind: str
    lane: str | None
    instructions: str = ""


@dataclass(frozen=True, slots=True)
class Flow:
    process_id: str
    name: str
    lanes: tuple[str, ...]
    user_tasks: tuple[UserTask, ...]
    steps: tuple[Step, ...]
    decisions: tuple[str, ...]
    service_operations: tuple[str, ...]
    timers: tuple[str, ...]
    gateways: tuple[str, ...]
    script_tasks: int = 0
    errors: tuple[str, ...] = field(default=())

    @property
    def form_files(self) -> tuple[str, ...]:
        names = {
            name
            for task in self.user_tasks
            for name in (task.form_schema, task.form_ui_schema)
            if name
        }
        return tuple(sorted(names))


class NotExecutable(ValidationError):
    """The file has no process anybody could start.

    Subclasses the library's ValidationError so it maps onto the same 422 as
    every other bad input, instead of escaping as a 500.
    """


def _properties(element) -> dict[str, str]:
    found: dict[str, str] = {}
    for holder in element.iter(f"{SPIFF}properties"):
        for prop in holder.findall(f"{SPIFF}property"):
            name = prop.get("name")
            if name:
                found[name] = prop.get("value") or ""
    return found


def _instructions(element) -> str:
    """`spiffworkflow:instructionsForEndUser`, the text to show on a step.

    The library ignores this element entirely, so a host that wants the modeller's
    own words on the screen has to read them here. See FINDINGS.
    """
    node = element.find(
        f"{BPMN}extensionElements/{SPIFF}instructionsForEndUser"
    )
    return (node.text or "").strip() if node is not None else ""


def _lane_of(element_id: str, lanes: dict[str, list[str]]) -> str | None:
    for lane_name, refs in lanes.items():
        if element_id in refs:
            return lane_name
    return None


def _in_run_order(steps: list[Step], process) -> list[Step]:
    """Order the nodes the way a run reaches them, following the sequence flows.

    Breadth-first from the start events. A node no arrow reaches -- an orphan, or
    a diagram we did not understand -- keeps its place at the end, so nothing is
    ever dropped just because the graph was odd.
    """
    outgoing: dict[str, list[str]] = {}
    for flow in process.findall(f"{BPMN}sequenceFlow"):
        source, target = flow.get("sourceRef"), flow.get("targetRef")
        if source and target:
            outgoing.setdefault(source, []).append(target)
    # A boundary event has no incoming arrow; it hangs off the step it interrupts.
    for element in process:
        host = element.get("attachedToRef")
        if host and element.get("id"):
            outgoing.setdefault(host, []).append(element.get("id", ""))

    by_id = {step.element_id: step for step in steps}
    queue = [step.element_id for step in steps if step.kind == "start"]
    seen: set[str] = set()
    order: list[Step] = []
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        if node in by_id:
            order.append(by_id[node])
        queue.extend(outgoing.get(node, []))

    order.extend(step for step in steps if step.element_id not in seen)
    return order


def inspect(bpmn_xml: str) -> Flow:
    """Summarise the first executable process in a BPMN file."""
    try:
        root = ElementTree.fromstring(bpmn_xml)
    except Exception as exc:  # noqa: BLE001 - any parse failure is one message
        raise NotExecutable(f"That does not look like BPMN XML: {exc}") from exc

    processes = root.findall(f"{BPMN}process")
    process = next(
        (p for p in processes if (p.get("isExecutable") or "").lower() == "true"),
        processes[0] if processes else None,
    )
    if process is None or not process.get("id"):
        raise NotExecutable("The file contains no process with an id")

    process_id = process.get("id", "")
    name = process.get("name") or _readable(process_id)

    lanes: dict[str, list[str]] = {}
    for lane in process.iter(f"{BPMN}lane"):
        lane_name = lane.get("name")
        if not lane_name:
            continue
        lanes.setdefault(lane_name, []).extend(
            ref.text.strip()
            for ref in lane.findall(f"{BPMN}flowNodeRef")
            if ref.text
        )

    user_tasks: list[UserTask] = []
    for tag in ("userTask", "manualTask"):
        for element in process.findall(f"{BPMN}{tag}"):
            element_id = element.get("id") or ""
            props = _properties(element)
            user_tasks.append(
                UserTask(
                    element_id=element_id,
                    name=element.get("name") or _readable(element_id),
                    lane=_lane_of(element_id, lanes),
                    form_schema=props.get(FORM_SCHEMA_PROPERTY) or None,
                    form_ui_schema=props.get(FORM_UI_PROPERTY) or None,
                    instructions=_instructions(element),
                )
            )

    # A modeller writes elements in whatever order they drew them, so document
    # order is not the order a run goes through them. Follow the arrows instead.
    steps: list[Step] = []
    for element in process:
        kind = STEP_KINDS.get(element.tag.removeprefix(BPMN))
        element_id = element.get("id") or ""
        if kind is None or not element_id:
            continue
        steps.append(
            Step(
                element_id=element_id,
                name=element.get("name") or UNNAMED.get(kind) or _readable(element_id),
                kind=kind,
                lane=_lane_of(element_id, lanes),
                instructions=_instructions(element),
            )
        )

    steps = _in_run_order(steps, process)

    decisions = [
        node.text.strip()
        for node in process.iter(f"{SPIFF}calledDecisionId")
        if node.text
    ]
    service_operations = [
        operator.get("id", "")
        for operator in process.iter(f"{SPIFF}serviceTaskOperator")
        if operator.get("id")
    ]

    timers: list[str] = []
    for holder_tag, label in (
        ("startEvent", "start"),
        ("intermediateCatchEvent", "wait"),
        ("boundaryEvent", "boundary"),
    ):
        for element in process.findall(f"{BPMN}{holder_tag}"):
            definition = element.find(f"{BPMN}timerEventDefinition")
            if definition is None:
                continue
            spec = next(
                (
                    (child.text or "").strip().strip("'\"")
                    for child in definition
                    if child.text
                ),
                "",
            )
            timers.append(f"{label}: {spec}" if spec else label)

    gateways = [
        f"{tag.removesuffix('Gateway')}"
        for tag in ("exclusiveGateway", "parallelGateway", "inclusiveGateway")
        for _ in process.findall(f"{BPMN}{tag}")
    ]

    errors: list[str] = []
    if not user_tasks and not service_operations:
        errors.append("This flow has no tasks, so nothing would ever happen.")
    if not process.findall(f"{BPMN}startEvent"):
        errors.append("This flow has no start event, so it cannot be started.")

    return Flow(
        process_id=process_id,
        name=name,
        lanes=tuple(lanes),
        user_tasks=tuple(user_tasks),
        steps=tuple(steps),
        decisions=tuple(dict.fromkeys(decisions)),
        service_operations=tuple(dict.fromkeys(service_operations)),
        timers=tuple(timers),
        gateways=tuple(gateways),
        script_tasks=len(process.findall(f"{BPMN}scriptTask")),
        errors=tuple(errors),
    )


def _readable(identifier: str) -> str:
    """`Process_two_step_leave_approval` -> `Two step leave approval`."""
    text = identifier.removeprefix("Process_").replace("_", " ").replace("-", " ")
    text = " ".join(part for part in text.split() if not _looks_random(part))
    return text[:1].upper() + text[1:] if text else identifier


def _looks_random(word: str) -> bool:
    """Modellers append ids like `e7wrlma` or `96f6665`; they are noise in a title."""
    if len(word) < 5:
        return False
    if any(character.isdigit() for character in word):
        return True
    return not any(vowel in word for vowel in "aeiou")
