import { useEffect, useState } from 'react'
import { api, type InspectReport, type Me, type Who } from './api'

/**
 * Publishing screen, for designers.
 *
 * A diagram is inspected before it is published, so the designer sees what the
 * console found -- lanes, steps, which forms it asks for, which service
 * operations it calls and whether any of them are unknown here -- and can supply
 * the missing pieces before anything is imported.
 */
export function Publish({
  who,
  me,
  onPublished,
  onError,
}: {
  who: Who
  me: Me
  onPublished: () => void
  onError: (error: unknown) => void
}) {
  const [bpmn, setBpmn] = useState('')
  const [dmn, setDmn] = useState('')
  const [name, setName] = useState('')
  const [report, setReport] = useState<InspectReport | null>(null)
  const [forms, setForms] = useState<Record<string, string>>({})
  const [owners, setOwners] = useState<Record<string, string[]>>({})
  const [operations, setOperations] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    api
      .operations(who)
      .then((rows) => setOperations(rows.map((row) => row.operation_id)))
      .catch(() => setOperations([]))
  }, [who])

  async function readFile(file: File): Promise<string> {
    return await file.text()
  }

  async function inspect(text: string) {
    setBpmn(text)
    setReport(null)
    setDone(null)
    if (!text.trim()) return
    try {
      const found = await api.inspect(who, text)
      setReport(found)
      setName(found.name)
      setOwners(
        Object.fromEntries(found.lanes.map((lane) => [lane, found.people])),
      )
      setForms(
        Object.fromEntries(
          found.form_files
            .filter((file) => !file.endsWith('uischema.json'))
            .map((file) => [file, forms[file] ?? '']),
        ),
      )
    } catch (error) {
      onError(error)
    }
  }

  function toggleOwner(lane: string, username: string) {
    const current = owners[lane] ?? []
    setOwners({
      ...owners,
      [lane]: current.includes(username)
        ? current.filter((person) => person !== username)
        : [...current, username],
    })
  }

  async function publish() {
    setBusy(true)
    setDone(null)
    try {
      const parsedForms: Record<string, unknown> = {}
      for (const [filename, text] of Object.entries(forms)) {
        if (!text.trim()) continue
        try {
          parsedForms[filename] = JSON.parse(text)
        } catch {
          throw new Error(`${filename} is not valid JSON`)
        }
      }
      const published = await api.publish(who, {
        bpmn,
        name: name || undefined,
        dmn: dmn.trim() || null,
        forms: parsedForms,
        lane_owners: owners,
      })
      setDone(`Published “${published.name}”. Anybody can start it now.`)
      onPublished()
    } catch (error) {
      onError(error)
    } finally {
      setBusy(false)
    }
  }

  if (!me.can_publish) {
    return (
      <div className="empty">
        <p>Publishing flows needs the designer role.</p>
      </div>
    )
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Publish a flow</h1>
          <p className="muted">
            Upload a BPMN diagram. Anybody in {me.company} will be able to start it.
          </p>
        </div>
      </div>

      <div className="alert warn-alert">
        <div>
          <strong>Publishing a flow runs its code</strong>
          <span>
            A diagram's script tasks execute Python inside this server, and its
            service tasks make real outbound calls. Only publish diagrams you
            trust — this permission is as powerful as server access.
          </span>
        </div>
      </div>

      <div className="card">
        <h2>1 · The diagram</h2>
        <div className="actions">
          <label className="filebtn">
            Choose a .bpmn file
            <input
              type="file"
              accept=".bpmn,.xml"
              onChange={async (event) => {
                const file = event.target.files?.[0]
                if (file) await inspect(await readFile(file))
              }}
            />
          </label>
          <label className="filebtn">
            Add a .dmn file
            <input
              type="file"
              accept=".dmn,.xml"
              onChange={async (event) => {
                const file = event.target.files?.[0]
                if (file) setDmn(await readFile(file))
              }}
            />
          </label>
        </div>
        <textarea
          className="code"
          rows={6}
          placeholder="…or paste the BPMN XML here"
          value={bpmn}
          onChange={(event) => setBpmn(event.target.value)}
          onBlur={() => inspect(bpmn)}
        />
        {dmn && <p className="ok">Decision table attached ({dmn.length} bytes).</p>}
      </div>

      {report && (
        <>
          <div className="card">
            <h2>2 · What the console found</h2>
            {report.problems.length > 0 && (
              <div className="alert">
                <div>
                  <strong>This diagram cannot run</strong>
                  <span>{report.problems.join(' ')}</span>
                </div>
              </div>
            )}
            <label>
              Name people will see
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <p className="muted small mono">{report.process_id}</p>

            <ol className="steps">
              {report.steps.map((step, index) => (
                <li key={index}>
                  <span>{step.name}</span>
                  <span className="muted small">
                    {step.lane ?? 'no lane'}
                    {step.form_schema ? ` · form ${step.form_schema}` : ' · no form'}
                  </span>
                </li>
              ))}
            </ol>

            <div className="chips">
              {report.decisions.map((decision) => (
                <span className="badge" key={decision}>
                  decision {decision}
                </span>
              ))}
              {report.gateways.map((gateway) => (
                <span className="badge" key={gateway}>
                  {gateway} gateway
                </span>
              ))}
              {report.timers.map((timer) => (
                <span className="badge" key={timer}>
                  timer {timer}
                </span>
              ))}
              {report.service_operations.map((operation) => (
                <span
                  className={`badge mono ${
                    report.unknown_operations.includes(operation) ? 'bad' : ''
                  }`}
                  key={operation}
                >
                  {operation}
                </span>
              ))}
              {report.script_tasks > 0 && (
                <span className="badge">{report.script_tasks} script task(s)</span>
              )}
            </div>

            {report.decisions.length > 0 && !dmn && (
              <p className="note warn">
                This diagram calls a decision table. Attach the .dmn file above or
                it will fail when it reaches that step.
              </p>
            )}
            {report.unknown_operations.length > 0 && (
              <p className="note warn">
                No connector here serves{' '}
                {report.unknown_operations.join(', ')}. Available:{' '}
                {operations.join(', ')}.
              </p>
            )}
          </div>

          {report.lanes.length > 0 && (
            <div className="card">
              <h2>3 · Who picks up each lane</h2>
              <p className="muted">
                Leave everybody selected and anyone can do any step.
              </p>
              {report.lanes.map((lane) => (
                <div className="lane-row" key={lane}>
                  <strong>{lane}</strong>
                  <div className="chips">
                    {report.people.map((person) => (
                      <button
                        key={person}
                        className={
                          (owners[lane] ?? []).includes(person) ? 'chip on' : 'chip'
                        }
                        onClick={() => toggleOwner(lane, person)}
                      >
                        {person}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {Object.keys(forms).length > 0 && (
            <div className="card">
              <h2>4 · Forms the diagram asks for</h2>
              <p className="muted">
                Paste a JSON Schema for each. A step with no schema falls back to a
                free-form editor.
              </p>
              {Object.keys(forms).map((filename) => (
                <label key={filename}>
                  <span className="mono">{filename}</span>
                  <textarea
                    className="code"
                    rows={4}
                    placeholder='{"type":"object","properties":{"note":{"type":"string"}}}'
                    value={forms[filename]}
                    onChange={(event) =>
                      setForms({ ...forms, [filename]: event.target.value })
                    }
                  />
                </label>
              ))}
            </div>
          )}

          <div className="card">
            <div className="modal-actions">
              <button
                className="primary"
                disabled={busy || report.problems.length > 0}
                onClick={publish}
              >
                {busy ? 'Publishing…' : 'Publish this flow'}
              </button>
            </div>
            {done && <p className="ok">{done}</p>}
          </div>
        </>
      )}
    </>
  )
}
