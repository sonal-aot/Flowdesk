import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { api, type InspectReport, type Me } from './api'
import { PageHead } from './screens'

/**
 * Publishing screen, for accounts with the publish capability.
 *
 * A diagram is inspected before it is published, so the publisher sees what the
 * console found — lanes, steps, which forms it asks for, which service
 * operations it calls and whether any are unknown here — and can supply the
 * missing pieces before anything is imported.
 */
export function Publish({
  me,
  onPublished,
  onError,
}: {
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
      .operations()
      .then((rows) => setOperations(rows.map((row) => row.operation_id)))
      .catch(() => setOperations([]))
  }, [])

  async function inspect(text: string) {
    setBpmn(text)
    setReport(null)
    setDone(null)
    if (!text.trim()) return
    try {
      const found = await api.inspect(text)
      setReport(found)
      setName(found.name)
      setOwners(Object.fromEntries(found.lanes.map((lane) => [lane, found.people])))
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
      const parsed: Record<string, unknown> = {}
      for (const [filename, text] of Object.entries(forms)) {
        if (!text.trim()) continue
        try {
          parsed[filename] = JSON.parse(text)
        } catch {
          throw new Error(`${filename} is not valid JSON`)
        }
      }
      const published = await api.publish({
        bpmn,
        name: name || undefined,
        dmn: dmn.trim() || null,
        forms: parsed,
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
    return <Alert severity="info">Publishing flows needs the admin or editor role.</Alert>
  }

  return (
    <>
      <PageHead
        title="Publish a flow"
        subtitle={`Upload a BPMN diagram. Anybody in ${me.company} will be able to start it.`}
      />

      <Alert severity="warning" sx={{ mb: 2 }}>
        <strong>Publishing a flow runs its code.</strong> A diagram's script tasks
        execute Python inside this server, and its service tasks make real
        outbound calls. Only publish diagrams you trust — this permission is as
        powerful as server access.
      </Alert>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h2" gutterBottom>
            1 · The diagram
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap sx={{ mb: 2, flexWrap: "wrap" }}>
            <Button component="label" variant="outlined" startIcon={<UploadFileIcon />}>
              Choose a .bpmn file
              <input
                hidden
                type="file"
                accept=".bpmn,.xml"
                onChange={async (event) => {
                  const file = event.target.files?.[0]
                  if (file) await inspect(await file.text())
                }}
              />
            </Button>
            <Button component="label" variant="outlined" startIcon={<UploadFileIcon />}>
              Add a .dmn file
              <input
                hidden
                type="file"
                accept=".dmn,.xml"
                onChange={async (event) => {
                  const file = event.target.files?.[0]
                  if (file) setDmn(await file.text())
                }}
              />
            </Button>
          </Stack>
          <TextField
            fullWidth
            multiline
            minRows={5}
            size="small"
            placeholder="…or paste the BPMN XML here"
            value={bpmn}
            onChange={(event) => setBpmn(event.target.value)}
            onBlur={() => inspect(bpmn)}
            sx={{ '& textarea': { fontFamily: 'monospace', fontSize: 12 } }}
          />
          {dmn && (
            <Typography variant="body2" color="success.main" sx={{ mt: 1 }}>
              Decision table attached ({dmn.length} bytes).
            </Typography>
          )}
        </CardContent>
      </Card>

      {report && (
        <>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h2" gutterBottom>
                2 · What the console found
              </Typography>
              {report.problems.length > 0 && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {report.problems.join(' ')}
                </Alert>
              )}
              <TextField
                fullWidth
                size="small"
                label="Name people will see"
                value={name}
                onChange={(event) => setName(event.target.value)}
                sx={{ mb: 1 }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                {report.process_id}
              </Typography>

              <Table size="small" sx={{ mt: 1.5, mb: 1.5 }}>
                <TableBody>
                  {report.steps.map((step, index) => (
                    <TableRow key={index}>
                      <TableCell sx={{ width: 32, color: 'text.secondary' }}>
                        {index + 1}
                      </TableCell>
                      <TableCell>{step.name}</TableCell>
                      <TableCell align="right">
                        <Typography variant="caption" color="text.secondary">
                          {step.lane ?? 'no lane'}
                          {step.form_schema ? ` · form ${step.form_schema}` : ' · no form'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                {report.decisions.map((decision) => (
                  <Chip key={decision} size="small" variant="outlined" label={`decision ${decision}`} />
                ))}
                {report.gateways.map((gateway) => (
                  <Chip key={gateway} size="small" variant="outlined" label={`${gateway} gateway`} />
                ))}
                {report.timers.map((timer) => (
                  <Chip key={timer} size="small" variant="outlined" label={`timer ${timer}`} />
                ))}
                {report.service_operations.map((operation) => (
                  <Chip
                    key={operation}
                    size="small"
                    variant="outlined"
                    color={report.unknown_operations.includes(operation) ? 'error' : 'default'}
                    label={operation}
                    sx={{ fontFamily: 'monospace' }}
                  />
                ))}
                {report.script_tasks > 0 && (
                  <Chip size="small" variant="outlined" label={`${report.script_tasks} script task(s)`} />
                )}
              </Stack>

              {report.decisions.length > 0 && !dmn && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  This diagram calls a decision table. Attach the .dmn file above,
                  or it will fail when it reaches that step.
                </Alert>
              )}
              {report.unknown_operations.length > 0 && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  No connector here serves {report.unknown_operations.join(', ')}.
                  Available: {operations.join(', ')}.
                </Alert>
              )}
            </CardContent>
          </Card>

          {report.lanes.length > 0 && (
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h2" gutterBottom>
                  3 · Who picks up each lane
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Leave everybody selected and anyone can do any step.
                </Typography>
                {report.lanes.map((lane) => (
                  <Stack key={lane} direction="row" spacing={1.5} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", py: 1, borderTop: 1, borderColor: "divider" }}>
                    <Typography sx={{ minWidth: 120, fontWeight: 600 }}>
                      {lane}
                    </Typography>
                    <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                      {report.people.map((person) => (
                        <Chip
                          key={person}
                          size="small"
                          label={person}
                          color={(owners[lane] ?? []).includes(person) ? 'primary' : 'default'}
                          variant={(owners[lane] ?? []).includes(person) ? 'filled' : 'outlined'}
                          onClick={() => toggleOwner(lane, person)}
                        />
                      ))}
                    </Stack>
                  </Stack>
                ))}
              </CardContent>
            </Card>
          )}

          {Object.keys(forms).length > 0 && (
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h2" gutterBottom>
                  4 · Forms the diagram asks for
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Paste a JSON Schema for each. A step with no schema falls back
                  to a free-form editor.
                </Typography>
                <Stack spacing={2}>
                  {Object.keys(forms).map((filename) => (
                    <TextField
                      key={filename}
                      fullWidth
                      multiline
                      minRows={3}
                      size="small"
                      label={filename}
                      placeholder='{"type":"object","properties":{"note":{"type":"string"}}}'
                      value={forms[filename]}
                      onChange={(event) =>
                        setForms({ ...forms, [filename]: event.target.value })
                      }
                      sx={{ '& textarea': { fontFamily: 'monospace', fontSize: 12 } }}
                    />
                  ))}
                </Stack>
              </CardContent>
            </Card>
          )}

          <Card variant="outlined">
            <CardContent>
              <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
                <Button
                  variant="contained"
                  disabled={busy || report.problems.length > 0}
                  onClick={publish}
                >
                  {busy ? 'Publishing…' : 'Publish this flow'}
                </Button>
                {done && (
                  <Typography variant="body2" color="success.main">
                    {done}
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
          <Box sx={{ height: 24 }} />
        </>
      )}
    </>
  )
}
