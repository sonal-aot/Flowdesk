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
import HourglassTopIcon from '@mui/icons-material/HourglassTop'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import DoNotDisturbAltIcon from '@mui/icons-material/DoNotDisturbAlt'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  STATUS_COLOR,
  api,
  type ActivityRow,
  type FlowSummary,
  type InstanceDetail,
  type InstanceRow,
  type Me,
  type ProgressStep,
  type TaskDetail,
  type TaskRow,
} from './api'
import { FreeForm, TaskForm } from './TaskForm'

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
  reloadKey,
  onStarted,
  onError,
}: {
  reloadKey: number
  onStarted: (id: number) => void
  onError: Fail
}) {
  const [rows, setRows] = useState<FlowSummary[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

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
            : `${rows.length} flow${rows.length === 1 ? '' : 's'} published here`
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
                <Button
                  variant="contained"
                  startIcon={<PlayArrowIcon />}
                  disabled={busy === flow.process_id}
                  onClick={() => begin(flow)}
                >
                  {busy === flow.process_id ? 'Starting…' : 'Start'}
                </Button>
              </Stack>

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

      <Dialog open={open !== null} onClose={() => setOpen(null)} fullWidth sx={{ maxWidth: "sm" }}>
        {open && (
          <>
            <DialogTitle sx={{ pb: 0.5 }}>
              {open.name}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                run #{open.instance_id} · {open.lane ?? 'no lane'}
              </Typography>
            </DialogTitle>
            <DialogContent>
              {Object.keys(open.known_data).length > 0 && (
                <TableContainer
                  component={Paper}
                  variant="outlined"
                  sx={{ mb: 2, maxHeight: 160 }}
                >
                  <Table size="small">
                    <TableBody>
                      {Object.entries(open.known_data).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell sx={{ color: 'text.secondary' }}>{key}</TableCell>
                          <TableCell>{value}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
              {open.form ? (
                <TaskForm schema={open.form} busy={busy} onSubmit={submit} />
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
              <TableRow key={row.id} hover>
                <TableCell>
                  <Button size="small" onClick={() => show(row.id)}>
                    #{row.id}
                  </Button>
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
                  <Typography variant="body2" color="text.secondary">
                    {row.waiting_on.join(', ') || '—'}
                  </Typography>
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

      <Drawer anchor="right" open={open !== null} onClose={() => setOpen(null)}>
        <Box sx={{ width: { xs: '100vw', sm: 420 }, p: 3 }}>
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
                          <TableCell>{value}</TableCell>
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

              {me.can_operate && (
                <Section title="Operate">
                  <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                    {open.status === 'suspended' ? (
                      <Button size="small" variant="outlined" onClick={() => act(open.id, 'release')}>
                        Release
                      </Button>
                    ) : (
                      <Button size="small" variant="outlined" onClick={() => act(open.id, 'hold')}>
                        Hold
                      </Button>
                    )}
                    <Button size="small" variant="outlined" onClick={() => act(open.id, 'retry')}>
                      Retry
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={() => act(open.id, 'cancel')}
                    >
                      Cancel
                    </Button>
                  </Stack>
                </Section>
              )}
            </>
          )}
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
          {step.lane ? `${step.lane} · ` : ''}
          {step.state === 'done'
            ? `done by ${step.by}${step.at ? ` · ${step.at}` : ''}`
            : look.note}
        </Typography>
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
