/** Client for the Flowdesk API. */

const BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8020'
const STORED = 'flowdesk.account'

export interface Account {
  company_id: string
  company: string
  username: string
  name: string
  title: string
  role: string
  initials: string
}

export interface Me {
  name: string
  username: string
  title: string
  role: string
  company: string
  company_id: string
  can_publish: boolean
  can_operate: boolean
  open_tasks: number
  people: { username: string; name: string }[]
}

export interface Step {
  name: string
  lane: string | null
  has_form: boolean
}

export interface FlowSummary {
  process_id: string
  name: string
  version_id: number
  lanes: string[]
  lane_owners: Record<string, string[]>
  steps: Step[]
  decisions: string[]
  service_operations: string[]
  timers: string[]
  gateways: string[]
  script_tasks: number
  has_dmn: boolean
  versions: number | { version_id: number; published_at: number }[]
  files?: { filename: string; kind: string; bytes: number }[]
}

export interface TaskRow {
  id: number
  name: string
  lane: string | null
  instance_id: number
  process_id: string
  flow: string
  summary: string | null
  claimed_by: string | null
}

/** The subset of JSON Schema the form renderer understands. */
export interface FormSchema {
  title?: string
  description?: string
  required?: string[]
  properties?: Record<string, FormField>
}

export interface FormField {
  type?: string
  title?: string
  description?: string
  enum?: string[]
  format?: string
  default?: unknown
  minimum?: number
  maximum?: number
}

export interface TaskDetail {
  id: number
  name: string
  element_id: string
  lane: string | null
  instance_id: number
  process_id: string
  summary: string | null
  claimed_by: string | null
  completed: boolean
  form: FormSchema | null
  known_data: Record<string, string>
}

export interface InstanceRow {
  id: number
  process_id: string
  summary: string | null
  status: string
  started_by: string | null
  waiting_on: string[]
  open_steps: number
}

export interface InstanceDetail extends InstanceRow {
  data: Record<string, string>
  events: { event: string; by: string | null; at: string }[]
  steps: {
    id: number
    name: string
    lane: string | null
    done: boolean
    by: string | null
    claimed_by: string | null
  }[]
  activity: { operation_id: string; outcome: string; detail: string; at: string }[]
}

export interface InspectReport {
  process_id: string
  name: string
  lanes: string[]
  steps: { name: string; lane: string | null; form_schema: string | null }[]
  decisions: string[]
  service_operations: string[]
  unknown_operations: string[]
  timers: string[]
  gateways: string[]
  script_tasks: number
  form_files: string[]
  problems: string[]
  people: string[]
}

export interface ActivityRow {
  id: number
  instance_id: number | null
  operation_id: string
  parameters: string
  outcome: string
  detail: string
  at: string
}

export class ApiError extends Error {
  readonly status: number
  readonly technical: string

  constructor(status: number, message: string, technical: string) {
    super(message)
    this.status = status
    this.technical = technical
  }
}

export type Who = { company_id: string; username: string }

export const session = {
  read(): Who | null {
    try {
      const raw = localStorage.getItem(STORED)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },
  write(account: Account) {
    try {
      localStorage.setItem(
        STORED,
        JSON.stringify({
          company_id: account.company_id,
          username: account.username,
        }),
      )
    } catch {
      // A private window still works, just not across reloads.
    }
  },
  clear() {
    try {
      localStorage.removeItem(STORED)
    } catch {
      // ignore
    }
  },
}

async function call<T>(who: Who | null, path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(who ? { 'X-Tenant-Id': who.company_id, 'X-User': who.username } : {}),
        ...(init.headers ?? {}),
      },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is it running?', `fetch ${BASE}`)
  }
  const body = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.message ?? 'Something went wrong.',
      body?.technical ?? JSON.stringify(body?.detail ?? body ?? {}),
    )
  }
  return body as T
}

export const api = {
  accounts: () => call<Account[]>(null, '/accounts'),
  me: (who: Who) => call<Me>(who, '/me'),

  flows: (who: Who) => call<FlowSummary[]>(who, '/flows'),
  flow: (who: Who, processId: string) =>
    call<FlowSummary>(who, `/flows/${processId}`),
  diagram: (who: Who, processId: string) =>
    call<{ bpmn: string }>(who, `/flows/${processId}/diagram`),
  operations: (who: Who) =>
    call<{ operation_id: string; description: string }[]>(who, '/operations'),
  inspect: (who: Who, bpmn: string) =>
    call<InspectReport>(who, '/inspect', {
      method: 'POST',
      body: JSON.stringify({ bpmn }),
    }),
  publish: (
    who: Who,
    payload: {
      bpmn: string
      name?: string
      dmn?: string | null
      forms: Record<string, unknown>
      lane_owners: Record<string, string[]>
    },
  ) =>
    call<FlowSummary>(who, '/flows', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  start: (who: Who, processId: string) =>
    call<{ id: number; status: string }>(who, `/flows/${processId}/start`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  tasks: (who: Who, mine: boolean) =>
    call<TaskRow[]>(who, `/tasks?mine=${mine}`),
  task: (who: Who, id: number) => call<TaskDetail>(who, `/tasks/${id}`),
  completeTask: (who: Who, id: number, payload: Record<string, unknown>) =>
    call<{ id: number; instance_id: number; instance_status: string }>(
      who,
      `/tasks/${id}/complete`,
      { method: 'POST', body: JSON.stringify({ payload }) },
    ),

  instances: (who: Who, scope: string, status?: string) =>
    call<InstanceRow[]>(
      who,
      `/instances?scope=${scope}${status ? `&status=${status}` : ''}`,
    ),
  instance: (who: Who, id: number) => call<InstanceDetail>(who, `/instances/${id}`),
  lifecycle: (who: Who, id: number, action: string) =>
    call<{ id: number; status: string }>(who, `/instances/${id}/${action}`, {
      method: 'POST',
    }),
  scheduleRetry: (who: Who, id: number, inSeconds: number) =>
    call<{ id: number; retry_in_seconds: number }>(
      who,
      `/instances/${id}/schedule-retry`,
      { method: 'POST', body: JSON.stringify({ in_seconds: inSeconds }) },
    ),

  activity: (who: Who) => call<ActivityRow[]>(who, '/activity'),
}
