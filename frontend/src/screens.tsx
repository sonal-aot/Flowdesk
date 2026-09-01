import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ActivityRow,
  type FlowSummary,
  type InstanceDetail,
  type InstanceRow,
  type Me,
  type TaskDetail,
  type TaskRow,
  type Who,
} from './api'
import { FreeForm, JsonForm } from './JsonForm'

type Fail = (error: unknown) => void
type Tone = 'good' | 'bad' | 'warn' | 'wait' | 'neutral'

const TONE_BY_STATUS: Record<string, Tone> = {
  complete: 'good',
  error: 'bad',
  terminated: 'bad',
  suspended: 'warn',
  user_input_required: 'wait',
  waiting: 'wait',
  running: 'wait',
  not_started: 'neutral',
}

export function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`pill tone-${tone}`}>{children}</span>
}

function Status({ status }: { status: string }) {
  return (
    <Pill tone={TONE_BY_STATUS[status] ?? 'neutral'}>{status.replace(/_/g, ' ')}</Pill>
  )
}

/* ---------------------------------------------------------------------- Flows */

export function Flows({
  who,
  reloadKey,
  onStarted,
  onError,
}: {
  who: Who
  reloadKey: number
  onStarted: (instanceId: number) => void
  onError: Fail
}) {
  const [rows, setRows] = useState<FlowSummary[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    api
      .flows(who)
      .then((data) => !stale && setRows(data))
      .catch((error) => !stale && onError(error))
    return () => {
      stale = true
    }
  }, [who, reloadKey])

  async function begin(flow: FlowSummary) {
    setBusy(flow.process_id)
    try {
      const started = await api.start(who, flow.process_id)
      onStarted(started.id)
    } catch (error) {
      onError(error)
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Flows</h1>
          <p className="muted">
            {rows === null
              ? 'Loading…'
              : `${rows.length} flow${rows.length === 1 ? '' : 's'} published here`}
          </p>
        </div>
      </div>

      {rows?.length === 0 && (
        <div className="empty">
          <p>No flows are published yet. A designer can publish one.</p>
        </div>
      )}

      <div className="cards">
        {(rows ?? []).map((flow) => (
          <div className="card" key={flow.process_id}>
            <div className="approval-head">
              <div>
                <strong>{flow.name}</strong>
                <div className="muted small mono">{flow.process_id}</div>
              </div>
              <button
                className="primary"
                disabled={busy === flow.process_id}
                onClick={() => begin(flow)}
              >
                {busy === flow.process_id ? 'Starting…' : 'Start'}
              </button>
            </div>

            <ol className="steps">
              {flow.steps.map((step, index) => (
                <li key={index}>
                  <span>{step.name}</span>
                  <span className="muted small">
                    {step.lane ?? 'no lane'}
                    {step.has_form ? ' · has a form' : ' · no form'}
                  </span>
                </li>
              ))}
            </ol>

            <div className="chips">
              {flow.lanes.map((lane) => (
                <span className="badge" key={lane}>
                  {lane}: {(flow.lane_owners[lane] ?? []).join(', ') || 'everyone'}
                </span>
              ))}
              {flow.has_dmn && <span className="badge">decision table</span>}
              {flow.gateways.map((gateway) => (
                <span className="badge" key={gateway}>
                  {gateway} gateway
                </span>
              ))}
              {flow.timers.map((timer) => (
                <span className="badge" key={timer}>
                  timer {timer}
                </span>
              ))}
              {flow.service_operations.map((operation) => (
                <span className="badge mono" key={operation}>
                  {operation}
                </span>
              ))}
              {flow.script_tasks > 0 && (
                <span className="badge">{flow.script_tasks} script task(s)</span>
              )}
              {typeof flow.versions === 'number' && flow.versions > 1 && (
                <span className="badge">{flow.versions} versions</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

/* ----------------------------------------------------------------------- Work */

export function Work({
  who,
  reloadKey,
  onChanged,
  onError,
}: {
  who: Who
  reloadKey: number
  onChanged: () => void
  onError: Fail
}) {
  const [rows, setRows] = useState<TaskRow[] | null>(null)
  const [mine, setMine] = useState(true)
  const [open, setOpen] = useState<TaskDetail | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api
      .tasks(who, mine)
      .then(setRows)
      .catch(onError)
  }, [who, mine])

  useEffect(() => {
    load()
    // A timer can hand work over without anybody clicking anything.
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [load, reloadKey])

  async function openTask(id: number) {
    try {
      setOpen(await api.task(who, id))
    } catch (error) {
      onError(error)
    }
  }

  async function submit(values: Record<string, unknown>) {
    if (open === null) return
    setBusy(true)
    try {
      await api.completeTask(who, open.id, values)
      setOpen(null)
      onChanged()
    } catch (error) {
      onError(error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>My work</h1>
          <p className="muted">
            {rows === null
              ? 'Loading…'
              : rows.length === 0
                ? 'Nothing waiting on you'
                : `${rows.length} task${rows.length === 1 ? '' : 's'}`}
          </p>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={!mine}
            onChange={(event) => setMine(!event.target.checked)}
          />
          show everything open
        </label>
      </div>

      {rows?.length === 0 && (
        <div className="empty">
          <p>No open tasks. Start a flow from the Flows tab.</p>
        </div>
      )}

      <div className="cards">
        {(rows ?? []).map((task) => (
          <button key={task.id} className="card row-card" onClick={() => openTask(task.id)}>
            <div className="row-main">
              <strong>{task.name}</strong>
              <span className="muted">
                {task.flow} · run #{task.instance_id}
                {task.lane ? ` · ${task.lane}` : ''}
              </span>
            </div>
            {task.claimed_by ? (
              <Pill tone="neutral">claimed by {task.claimed_by}</Pill>
            ) : (
              <Pill tone="wait">open</Pill>
            )}
          </button>
        ))}
      </div>

      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(null)}>
          <div className="modal wide" onClick={(event) => event.stopPropagation()}>
            <div>
              <strong>{open.name}</strong>
              <div className="muted small">
                run #{open.instance_id} · {open.lane ?? 'no lane'}
              </div>
            </div>

            {Object.keys(open.known_data).length > 0 && (
              <details className="known">
                <summary>What the flow already knows</summary>
                <table>
                  <tbody>
                    {Object.entries(open.known_data).map(([key, value]) => (
                      <tr key={key}>
                        <th>{key}</th>
                        <td>{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}

            {open.form ? (
              <JsonForm schema={open.form} busy={busy} onSubmit={submit} />
            ) : (
              <FreeForm busy={busy} onSubmit={submit} />
            )}

            <button className="ghost" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ Instances */

const STATUSES = [
  'all',
  'user_input_required',
  'waiting',
  'complete',
  'suspended',
  'terminated',
  'error',
]

export function Instances({
  who,
  me,
  reloadKey,
  focus,
  onChanged,
  onError,
}: {
  who: Who
  me: Me
  reloadKey: number
  focus: number | null
  onChanged: () => void
  onError: Fail
}) {
  const [rows, setRows] = useState<InstanceRow[] | null>(null)
  const [status, setStatus] = useState('all')
  const [scope, setScope] = useState('all')
  const [open, setOpen] = useState<InstanceDetail | null>(null)

  useEffect(() => {
    let stale = false
    api
      .instances(who, scope, status === 'all' ? undefined : status)
      .then((data) => !stale && setRows(data))
      .catch((error) => !stale && onError(error))
    return () => {
      stale = true
    }
  }, [who, scope, status, reloadKey])

  const show = useCallback(
    async (id: number) => {
      try {
        setOpen(await api.instance(who, id))
      } catch (error) {
        onError(error)
      }
    },
    [who],
  )

  useEffect(() => {
    if (focus !== null) show(focus)
  }, [focus, show])

  async function act(id: number, action: string) {
    try {
      await api.lifecycle(who, id, action)
      onChanged()
      await show(id)
    } catch (error) {
      onError(error)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p className="muted">
            {rows === null ? 'Loading…' : `${rows.length} shown`}
          </p>
        </div>
        <div className="actions">
          <select value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="all">Everyone's</option>
            <option value="mine">Started by me</option>
          </select>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            {STATUSES.map((option) => (
              <option key={option} value={option}>
                {option === 'all' ? 'Any status' : option.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th>Run</th>
            <th>Flow</th>
            <th>Waiting on</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {(rows ?? []).map((row) => (
            <tr key={row.id}>
              <td>
                <button className="link" onClick={() => show(row.id)}>
                  #{row.id}
                </button>
                <div className="muted small">{row.started_by}</div>
              </td>
              <td>
                {row.summary}
                <div className="muted small mono">{row.process_id}</div>
              </td>
              <td className="muted">{row.waiting_on.join(', ') || '—'}</td>
              <td>
                <Status status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows?.length === 0 && (
        <div className="empty">
          <p>Nothing matches that filter.</p>
        </div>
      )}

      {open && (
        <div className="drawer-backdrop" onClick={() => setOpen(null)}>
          <aside className="drawer" onClick={(event) => event.stopPropagation()}>
            <button className="close" onClick={() => setOpen(null)} aria-label="Close">
              ×
            </button>
            <Status status={open.status} />
            <h2>Run #{open.id}</h2>
            <p className="muted">{open.summary}</p>
            <p className="muted small mono">{open.process_id}</p>

            <h3>Steps</h3>
            <ol className="timeline">
              {open.steps.map((step) => (
                <li key={step.id} className={step.done ? 'tone-good' : 'tone-wait'}>
                  <span>
                    {step.name}
                    {step.lane ? ` · ${step.lane}` : ''}
                  </span>
                  <span className="muted small">
                    {step.done ? `done by ${step.by}` : 'open'}
                  </span>
                </li>
              ))}
            </ol>

            {Object.keys(open.data).length > 0 && (
              <>
                <h3>Data collected</h3>
                <table>
                  <tbody>
                    {Object.entries(open.data).map(([key, value]) => (
                      <tr key={key}>
                        <th>{key}</th>
                        <td>{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {open.activity.length > 0 && (
              <>
                <h3>Service tasks</h3>
                <ul className="mails">
                  {open.activity.map((call, index) => (
                    <li key={index}>
                      <span className="mono">{call.operation_id}</span>
                      <span className="muted small">
                        {call.outcome} · {call.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <h3>Events</h3>
            <ol className="timeline">
              {open.events.map((event, index) => (
                <li key={index} className="tone-neutral">
                  <span className="mono">{event.event}</span>
                  <span className="muted small">
                    {event.at}
                    {event.by ? ` · ${event.by}` : ''}
                  </span>
                </li>
              ))}
            </ol>

            {me.can_operate && (
              <>
                <h3>Operate</h3>
                <div className="actions">
                  {open.status === 'suspended' ? (
                    <button onClick={() => act(open.id, 'release')}>Release</button>
                  ) : (
                    <button onClick={() => act(open.id, 'hold')}>Hold</button>
                  )}
                  <button onClick={() => act(open.id, 'retry')}>Retry</button>
                  <button className="danger" onClick={() => act(open.id, 'cancel')}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </aside>
        </div>
      )}
    </>
  )
}

/* ------------------------------------------------------------------- Activity */

export function Activity({
  who,
  reloadKey,
  onError,
}: {
  who: Who
  reloadKey: number
  onError: Fail
}) {
  const [rows, setRows] = useState<ActivityRow[] | null>(null)

  useEffect(() => {
    let stale = false
    api
      .activity(who)
      .then((data) => !stale && setRows(data))
      .catch((error) => !stale && onError(error))
    return () => {
      stale = true
    }
  }, [who, reloadKey])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Service task activity</h1>
          <p className="muted">Every connector call this workspace's flows made</p>
        </div>
      </div>
      {rows?.length === 0 && (
        <div className="empty">
          <p>No service tasks have run yet.</p>
        </div>
      )}
      <table className="grid">
        <tbody>
          {(rows ?? []).map((row) => (
            <tr key={row.id}>
              <td>
                <span className="mono">{row.operation_id}</span>
                <div className="muted small">
                  {row.at}
                  {row.instance_id ? ` · run #${row.instance_id}` : ''} · {row.detail}
                </div>
                <pre className="mail-body">{row.parameters}</pre>
              </td>
              <td className="right">
                <Pill tone={row.outcome === 'ok' ? 'good' : 'bad'}>{row.outcome}</Pill>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
