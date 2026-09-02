import { useCallback, useEffect, useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Drawer,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlineOutlined'
import EditIcon from '@mui/icons-material/Edit'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import HourglassTopIcon from '@mui/icons-material/HourglassTop'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import DoNotDisturbAltIcon from '@mui/icons-material/DoNotDisturbAlt'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  STATUS_COLOR,
  api,
  type ActivityRow,
  type FlowSource,
  type FlowSummary,
  type InstanceDetail,
  type InstanceRow,
  type Me,
  type ProgressStep,
  type TaskDetail,
  type TaskRow,
} from './api'
import { Acknowledge, FreeForm, Instructions, TaskForm } from './TaskForm'

type Fail = (error: unknown) => void

export function PageHead({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children?: React.ReactNode
}) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 2, mb: 2.5 }}>
      <Box>
        <Typography variant="h1">{title}</Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary">
            {subtitle}
          </Typography>
        )}
      </Box>
      <Stack direction="row" spacing={1}>
        {children}
      </Stack>
    </Stack>
  )
}

function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      size="small"
      label={status.replace(/_/g, ' ')}
      color={STATUS_COLOR[status] ?? 'default'}
      variant={STATUS_COLOR[status] ? 'filled' : 'outlined'}
    />
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 5, textAlign: 'center', borderStyle: 'dashed' }}
    >
      <Typography color="text.secondary">{children}</Typography>
    </Paper>
  )
}

/* ---------------------------------------------------------------------- Flows */

export function Flows({
  me,
  reloadKey,
  onStarted,
  onEdit,
  onChanged,
  onError,
}: {
  me: Me
  reloadKey: number
  onStarted: (id: number) => void
  onEdit: (source: FlowSource) => void
  onChanged: () => void
  onError: Fail
}) {
  const [rows, setRows] = useState<FlowSummary[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [removing, setRemoving] = useState<FlowSummary | null>(null)

  useEffect(() => {
    let stale = false
    api
      .flows()
      .then((data) => !stale && setRows(data))
      .catch((error) => !stale && onError(error))
    return () => {
      stale = true
    }
  }, [reloadKey])

  async function edit(flow: FlowSummary) {
    setBusy(flow.process_id)
    try {
      onEdit(await api.flowSource(flow.process_id))
    } catch (error) {
      onError(error)
    } finally {
      setBusy(null)
    }
  }

  async function remove(flow: FlowSummary) {
    setBusy(flow.process_id)
    try {
      await api.deleteFlow(flow.process_id)
      setRemoving(null)
      onChanged()
    } catch (error) {
      onError(error)
    } finally {
      setBusy(null)
    }
  }

  async function begin(flow: FlowSummary) {
    setBusy(flow.process_id)
    try {
      onStarted((await api.start(flow.process_id)).id)
    } catch (error) {
      onError(error)
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHead
        title="Flows"
        subtitle={
          rows === null
            ? 'Loading…'
            : `${rows.length} flow${rows.length === 1 ? '' : 's'} published here` +
              (me.can_start ? '' : ' · you can view these, not start them')
        }
      />
      {rows?.length === 0 && (
        <Empty>
          No flows have been published in this company yet. An admin or editor
          can add one from Publish.
        </Empty>
      )}

      <Stack spacing={1.5}>
        {(rows ?? []).map((flow) => (
          <Card key={flow.process_id} variant="outlined">
            <CardContent>
              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
                <Box>
                  <Typography variant="h2">{flow.name}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                    {flow.process_id}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1}>
                  {me.can_publish && (
                    <>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<EditIcon />}
                        disabled={busy === flow.process_id}
                        onClick={() => edit(flow)}
                      >
                        Edit
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteOutlineIcon />}
                        disabled={busy === flow.process_id}
                        onClick={() => setRemoving(flow)}
                      >
                        Delete
                      </Button>
                    </>
                  )}
                  {me.can_start && (
                    <Button
                      variant="contained"
                      startIcon={<PlayArrowIcon />}
                      disabled={busy === flow.process_id}
                      onClick={() => begin(flow)}
                    >
                      {busy === flow.process_id ? 'Starting…' : 'Start'}
                    </Button>
                  )}
                </Stack>
              </Stack>

              {flow.steps.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, mb: 1.5 }}>
                  No step in this flow waits for a person, so it runs start to
                  finish the moment it is started.
                </Typography>
              ) : (
              <Table size="small" sx={{ mt: 1.5, mb: 1.5 }}>
                <TableBody>
                  {flow.steps.map((step, index) => (
                    <TableRow key={index}>
                      <TableCell sx={{ width: 32, color: 'text.secondary' }}>
                        {index + 1}
                      </TableCell>
                      <TableCell>{step.name}</TableCell>
                      <TableCell align="right">
                        <Typography variant="caption" color="text.secondary">
                          {step.lane ?? 'no lane'}
                          {step.has_form ? ' · has a form' : ' · no form'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              )}

              <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
                {flow.lanes.map((lane) => (
                  <Chip
                    key={lane}
                    size="small"
                    variant="outlined"
                    label={`${lane}: ${
                      (flow.lane_owners[lane] ?? []).join(', ') || 'everyone'
                    }`}
                  />
                ))}
                {flow.has_dmn && (
                  <Chip size="small" variant="outlined" label="decision table" />
                )}
                {flow.gateways.map((gateway) => (
                  <Chip
                    key={gateway}
                    size="small"
                    variant="outlined"
                    label={`${gateway} gateway`}
                  />
                ))}
                {flow.timers.map((timer) => (
                  <Chip key={timer} size="small" variant="outlined" label={`timer ${timer}`} />
                ))}
                {flow.service_operations.map((operation) => (
                  <Chip
                    key={operation}
                    size="small"
                    variant="outlined"
                    label={operation}
                    sx={{ fontFamily: 'monospace' }}
                  />
                ))}
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Dialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Delete “{removing?.name}”?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            It comes off this list, its files go, and nobody can start it again.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Runs that already happened stay on the Runs tab with their full
            history. A run still in flight will stop this — cancel that first.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 2.5 }}>
            <Button
              variant="contained"
              color="error"
              disabled={busy !== null}
              onClick={() => removing && remove(removing)}
            >
              {busy !== null ? 'Deleting…' : 'Delete'}
            </Button>
            <Button onClick={() => setRemoving(null)}>Keep it</Button>
          </Stack>
        </DialogContent>
      </Dialog>
    </>
  )
}

/* ----------------------------------------------------------------------- Work */

export function Work({
  reloadKey,
  onChanged,
  onError,
}: {
  reloadKey: number
  onChanged: () => void
  onError: Fail
}) {
  const [rows, setRows] = useState<TaskRow[] | null>(null)
  const [mine, setMine] = useState(true)
  const [open, setOpen] = useState<TaskDetail | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.tasks(mine).then(setRows).catch(onError)
  }, [mine])

  useEffect(() => {
    load()
    // A timer can hand work over without anybody clicking anything.
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [load, reloadKey])

  async function submit(values: Record<string, unknown>) {
    if (open === null) return
    setBusy(true)
    try {
      await api.completeTask(open.id, values)
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
      <PageHead
        title="My work"
        subtitle={
          rows === null
            ? 'Loading…'
            : rows.length === 0
              ? 'Nothing waiting on you'
              : `${rows.length} task${rows.length === 1 ? '' : 's'}`
        }
      >
        <TextField
          select
          size="small"
          value={mine ? 'mine' : 'all'}
          onChange={(event) => setMine(event.target.value === 'mine')}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="mine">Assigned to me</MenuItem>
          <MenuItem value="all">Everything open</MenuItem>
        </TextField>
      </PageHead>

      {rows?.length === 0 && <Empty>No open tasks. Start a flow from Flows.</Empty>}

      <Stack spacing={1}>
        {(rows ?? []).map((task) => (
          <Card key={task.id} variant="outlined">
            <CardContent
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 2,
                '&:last-child': { pb: 2 },
              }}
            >
              <Box>
                <Typography sx={{ fontWeight: 600 }}>{task.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {task.flow} · run #{task.instance_id}
                  {task.lane ? ` · ${task.lane}` : ''}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                {task.claimed_by && (
                  <Chip size="small" variant="outlined" label={task.claimed_by} />
                )}
                <Button
                  variant="outlined"
                  onClick={async () => {
                    try {
                      setOpen(await api.task(task.id))
                    } catch (error) {
                      onError(error)
                    }
                  }}
                >
                  Open
                </Button>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Dialog
        open={open !== null}
        onClose={() => setOpen(null)}
        fullWidth
        maxWidth={open?.instructions ? 'md' : 'sm'}
      >
        {open && (
          <>
            <DialogTitle sx={{ pb: 0.5 }}>
              {open.name}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                run #{open.instance_id} · {open.lane ?? 'no lane'}
              </Typography>
            </DialogTitle>
            <DialogContent>
              {open.instructions && <Instructions text={open.instructions} />}
              {Object.keys(open.known_data).length > 0 && (
                <>
                  <Typography
                    variant="overline"
                    sx={{ color: 'text.secondary', display: 'block' }}
                  >
                    Submitted earlier
                  </Typography>
                <TableContainer
                  component={Paper}
                  variant="outlined"
                  sx={{ mb: 2, maxHeight: 180, overflowY: 'auto' }}
                >
                  <Table size="small">
                    <TableBody>
                      {Object.entries(open.known_data).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell sx={{ color: 'text.secondary' }}>{key}</TableCell>
                          <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {asText(value)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                </>
              )}
              {open.form ? (
                <TaskForm schema={open.form} busy={busy} onSubmit={submit} />
              ) : open.instructions ? (
                <Acknowledge busy={busy} onSubmit={submit} />
              ) : (
                <FreeForm busy={busy} onSubmit={submit} />
              )}
            </DialogContent>
          </>
        )}
      </Dialog>
    </>
  )
}

/* ----------------------------------------------------------------------- Runs */

const STATUSES = [
  'all',
  'user_input_required',
  'waiting',
  'complete',
  'suspended',
  'terminated',
  'error',
]

export function Runs({
  me,
  reloadKey,
  focus,
  onChanged,
  onError,
}: {
  me: Me
  reloadKey: number
  focus: number | null
  onChanged: () => void
  onError: Fail
}) {
  const [rows, setRows] = useState<InstanceRow[] | null>(null)
  const [status, setStatus] = useState('all')
  const [open, setOpen] = useState<InstanceDetail | null>(null)

  useEffect(() => {
    let stale = false
    api
      .instances('all', status === 'all' ? undefined : status)
      .then((data) => !stale && setRows(data))
      .catch((error) => !stale && onError(error))
    return () => {
      stale = true
    }
  }, [status, reloadKey])

  const show = useCallback(async (id: number) => {
    try {
      setOpen(await api.instance(id))
    } catch (error) {
      onError(error)
    }
  }, [])

  useEffect(() => {
    if (focus !== null) show(focus)
  }, [focus, show])

  async function act(id: number, action: string) {
    try {
      await api.lifecycle(id, action)
      onChanged()
      await show(id)
    } catch (error) {
      onError(error)
    }
  }

  return (
    <>
      <PageHead
        title="Runs"
        subtitle={
          rows === null
            ? 'Loading…'
            : me.can_view_all
              ? `${rows.length} shown`
              : `${rows.length} started by you`
        }
      >
        <TextField
          select
          size="small"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          sx={{ minWidth: 200 }}
        >
          {STATUSES.map((option) => (
            <MenuItem key={option} value={option}>
              {option === 'all' ? 'Any status' : option.replace(/_/g, ' ')}
            </MenuItem>
          ))}
        </TextField>
      </PageHead>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Run</TableCell>
              <TableCell>Flow</TableCell>
              <TableCell>Waiting on</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(rows ?? []).map((row) => (
              <TableRow
                key={row.id}
                hover
                onClick={() => show(row.id)}
                sx={{ cursor: 'pointer' }}
              >
                <TableCell>
                  <Typography variant="body2" sx={{ color: 'primary.main', fontWeight: 600 }}>
                    #{row.id}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    {row.started_by}
                  </Typography>
                </TableCell>
                <TableCell>
                  {row.summary}
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontFamily: "monospace" }}>
                    {row.process_id}
                  </Typography>
                </TableCell>
                <TableCell>
                  {row.waiting_step ? (
                    <>
                      <Typography variant="body2">{row.waiting_step}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {row.waiting_people.join(', ') ||
                          row.waiting_on.join(', ') ||
                          'nobody assigned'}
                      </Typography>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      —
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <StatusChip status={row.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {rows?.length === 0 && (
        <Box sx={{ mt: 2 }}>
          <Empty>Nothing matches that filter.</Empty>
        </Box>
      )}

      {/* Above the app bar, so the panel is full height and nothing hovers over
          it. Otherwise the fixed bar covers the header and its close button. */}
      <Drawer
        anchor="right"
        open={open !== null}
        onClose={() => setOpen(null)}
        sx={{ zIndex: (theme) => theme.zIndex.drawer + 2 }}
      >
        <Box sx={{ width: { xs: '100vw', sm: 420 } }}>
          <Box sx={{ p: 3 }}>
          {open && (
            <>
              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
                <StatusChip status={open.status} />
                <IconButton size="small" onClick={() => setOpen(null)}>
                  <CloseIcon sx={{ fontSize: "small" }} />
                </IconButton>
              </Stack>
              <Typography variant="h1" sx={{ mt: 1 }}>
                Run #{open.id}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {open.summary}
              </Typography>

              <Paper
                variant="outlined"
                sx={{ mt: 2, p: 1.5, bgcolor: 'background.default' }}
              >
                <Typography variant="overline" sx={{ color: 'text.secondary' }}>
                  Next action
                </Typography>
                <Typography variant="body2">{open.next_action}</Typography>
              </Paper>

              <Section title="The flow">
                <Stack spacing={0}>
                  {open.progress.map((step, index) => (
                    <StepLine
                      key={index}
                      step={step}
                      last={index === open.progress.length - 1}
                    />
                  ))}
                </Stack>
              </Section>

              {Object.keys(open.data).length > 0 && (
                <Section title="Data collected">
                  <Table size="small">
                    <TableBody>
                      {Object.entries(open.data).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell sx={{ color: 'text.secondary' }}>{key}</TableCell>
                          <TableCell
                            sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                          >
                            {asText(value)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Section>
              )}

              {open.activity.length > 0 && (
                <Section title="Service tasks">
                  {open.activity.map((call, index) => (
                    <Stack key={index} direction="row" sx={{ justifyContent: "space-between", py: 0.5 }}>
                      <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                        {call.operation_id}
                      </Typography>
                      <Chip
                        size="small"
                        label={call.outcome}
                        color={call.outcome === 'ok' ? 'success' : 'error'}
                      />
                    </Stack>
                  ))}
                </Section>
              )}

              <Section title="Events">
                {open.events.map((event, index) => (
                  <Box key={index} sx={{ py: 0.35 }}>
                    <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                      {event.event}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {event.at}
                      {event.by ? ` · ${event.by}` : ''}
                    </Typography>
                  </Box>
                ))}
              </Section>

              {!me.can_operate && (
                <Section title="Operate">
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    Holding, cancelling or retrying a run needs the admin role.
                    You are signed in as {me.role}.
                  </Typography>
                </Section>
              )}
              {me.can_operate && (
                <Section title="Operate">
                  {open.allowed_actions.length === 0 ? (
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      {open.no_actions_reason}
                    </Typography>
                  ) : (
                    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
                      {open.allowed_actions.includes('hold') && (
                        <Button size="small" variant="outlined" onClick={() => act(open.id, 'hold')}>
                          Hold
                        </Button>
                      )}
                      {open.allowed_actions.includes('release') && (
                        <Button size="small" variant="outlined" onClick={() => act(open.id, 'release')}>
                          Release
                        </Button>
                      )}
                      {open.allowed_actions.includes('retry') && (
                        <Button size="small" variant="outlined" onClick={() => act(open.id, 'retry')}>
                          Retry
                        </Button>
                      )}
                      {open.allowed_actions.includes('cancel') && (
                        <Button
                          size="small"
                          variant="outlined"
                          color="error"
                          onClick={() => act(open.id, 'cancel')}
                        >
                          Cancel
                        </Button>
                      )}
                    </Stack>
                  )}
                </Section>
              )}
            </>
          )}
          </Box>
        </Box>
      </Drawer>
    </>
  )
}

const STEP_LOOK: Record<
  ProgressStep['state'],
  { icon: React.ReactNode; color: string; note: string }
> = {
  done: {
    icon: <CheckCircleIcon fontSize="small" color="success" />,
    color: 'success.main',
    note: 'done',
  },
  waiting: {
    icon: <HourglassTopIcon fontSize="small" color="info" />,
    color: 'info.main',
    note: 'waiting now',
  },
  upcoming: {
    icon: <RadioButtonUncheckedIcon fontSize="small" sx={{ color: 'text.disabled' }} />,
    color: 'text.disabled',
    note: 'still to come',
  },
  not_needed: {
    icon: <DoNotDisturbAltIcon fontSize="small" sx={{ color: 'text.disabled' }} />,
    color: 'text.disabled',
    note: 'not needed — the run went another way',
  },
  error: {
    icon: <ErrorOutlineIcon fontSize="small" color="error" />,
    color: 'error.main',
    note: 'failed here',
  },
}

/** What each kind of step is, said plainly. A person step needs no label. */
const KIND_NOTE: Partial<Record<ProgressStep['kind'], string>> = {
  service: 'called a service',
  script: 'ran automatically',
  decision: 'decision table',
  subflow: 'sub-flow',
  branch: 'branch',
  wait: 'waited',
  boundary: 'timer',
  start: 'start',
  end: 'end',
}

/** Anything a step or a run collected, as text. */
function asText(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

const MAX_SHOWN = 4000

const PRODUCED: Partial<Record<ProgressStep['kind'], string>> = {
  person: 'what was filled in',
  service: 'what it returned',
  decision: 'what it decided',
}

/** What a step added to the run. A service task's response can be enormous, so
 *  it stays folded away until somebody asks for it. */
function StepData({ value, kind }: { value: unknown; kind: ProgressStep['kind'] }) {
  const text = asText(value)
  return (
    <Box component="details" sx={{ mt: 0.75 }}>
      <Box
        component="summary"
        sx={{ cursor: 'pointer', fontSize: 12, color: 'text.secondary' }}
      >
        {PRODUCED[kind] ?? 'what it produced'} (
        {text.length.toLocaleString()} characters)
      </Box>
      <Box
        component="pre"
        sx={{
          mt: 0.5,
          mb: 0,
          p: 1,
          maxHeight: 260,
          overflow: 'auto',
          bgcolor: 'action.hover',
          borderRadius: 1,
          fontSize: 11,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {text.slice(0, MAX_SHOWN)}
        {text.length > MAX_SHOWN ? '\n… truncated' : ''}
      </Box>
    </Box>
  )
}

/** One step of the flow: where it is, who did it or who owes it. */
function StepLine({ step, last }: { step: ProgressStep; last: boolean }) {
  const look = STEP_LOOK[step.state]
  const dim = step.state === 'upcoming' || step.state === 'not_needed'
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
      <Stack sx={{ alignItems: 'center', pt: 0.25 }}>
        {look.icon}
        {!last && (
          <Box
            sx={{
              width: '2px',
              flexGrow: 1,
              minHeight: 22,
              bgcolor: 'divider',
              my: 0.25,
            }}
          />
        )}
      </Stack>
      <Box sx={{ pb: last ? 0 : 1.5, minWidth: 0 }}>
        <Typography
          variant="body2"
          sx={{ fontWeight: step.state === 'waiting' ? 600 : 500, color: dim ? 'text.secondary' : 'text.primary' }}
        >
          {step.name}
        </Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
          {[
            KIND_NOTE[step.kind],
            step.lane,
            step.state === 'done'
              ? step.by
                ? `done by ${step.by}${step.at ? ` · ${step.at}` : ''}`
                : `done${step.at ? ` · ${step.at}` : ''}`
              : look.note,
          ]
            .filter(Boolean)
            .join(' · ')}
        </Typography>
        {step.data !== null && step.data !== undefined && (
          <StepData value={step.data} kind={step.kind} />
        )}
        {step.state === 'waiting' && (
          <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap' }} useFlexGap>
            {step.people.length > 0 ? (
              step.people.map((person: { name: string; why: string }) => (
                <Chip
                  key={person.name}
                  size="small"
                  color="info"
                  variant="outlined"
                  label={person.name}
                  title={person.why}
                />
              ))
            ) : (
              <Typography variant="caption" sx={{ color: 'warning.main' }}>
                Nobody is assigned to this step
              </Typography>
            )}
          </Stack>
        )}
      </Box>
    </Stack>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.08em', display: "block" }}>
        {title}
      </Typography>
      {children}
    </Box>
  )
}

/* ------------------------------------------------------------------- Activity */

export function Activity({
  reloadKey,
  onError,
}: {
  reloadKey: number
  onError: Fail
}) {
  const [rows, setRows] = useState<ActivityRow[] | null>(null)
  const load = useCallback(() => {
    api.activity().then(setRows).catch(onError)
  }, [])

  useEffect(() => {
    load()
  }, [load, reloadKey])

  return (
    <>
      <PageHead
        title="Activity"
        subtitle="Every service-task call this workspace's flows have made"
      >
        <Tooltip title="Refresh">
          <IconButton onClick={load}>
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </PageHead>

      {rows?.length === 0 && <Empty>No service tasks have run yet.</Empty>}

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableBody>
            {(rows ?? []).map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                    {row.operation_id}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    {row.at}
                    {row.instance_id ? ` · run #${row.instance_id}` : ''} · {row.detail}
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      mt: 0.5,
                      p: 1,
                      bgcolor: 'background.default',
                      borderRadius: 1,
                      fontSize: 12,
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {row.parameters}
                  </Box>
                </TableCell>
                <TableCell align="right" sx={{ verticalAlign: 'top' }}>
                  <Chip
                    size="small"
                    label={row.outcome}
                    color={row.outcome === 'ok' ? 'success' : 'error'}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  )
}
