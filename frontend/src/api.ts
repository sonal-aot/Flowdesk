/** Client for the Flowdesk API. Identity is a bearer token from /auth/login. */

const BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8020'
const TOKEN_KEY = 'flowdesk.token'

export interface Company {
  company_id: string
  company: string
}

export interface Me {
  name: string
  username: string
  email: string
  title: string
  role: string
  library_role: string
  company: string
  company_id: string
  can_start: boolean
  can_publish: boolean
  can_operate: boolean
  can_configure: boolean
  can_view_all: boolean
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

export interface FormSchema {
  title?: string
  description?: string
  required?: string[]
  properties?: Record<string, unknown>
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
  waiting_step: string
  waiting_people: string[]
  open_steps: number
}

export type StepState = 'done' | 'waiting' | 'upcoming' | 'not_needed'

export interface ProgressStep {
  name: string
  lane: string | null
  state: StepState
  task_id: number | null
  by: string | null
  at: string | null
  people: { name: string; why: string }[]
}

export interface InstanceDetail extends InstanceRow {
  data: Record<string, string>
  events: { event: string; by: string | null; at: string }[]
  progress: ProgressStep[]
  next_action: string
  allowed_actions: string[]
  no_actions_reason: string | null
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

export const token = {
  read(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  write(value: string) {
    try {
      localStorage.setItem(TOKEN_KEY, value)
    } catch {
      // A private window still works, just not across reloads.
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      // ignore
    }
  },
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const bearer = token.read()
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
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
  companies: () => call<Company[]>('/companies'),
  login: (company_id: string, username: string, password: string) =>
    call<{ token: string; expires_at: number }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ company_id, username, password }),
    }),

  me: () => call<Me>('/me'),

  updateProfile: (changes: { name?: string; email?: string }) =>
    call<{ name: string; email: string; username: string }>('/me', {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  changePassword: (current_password: string, new_password: string) =>
    call<{ token: string; expires_at: number }>('/me/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),

  flows: () => call<FlowSummary[]>('/flows'),
  flow: (processId: string) => call<FlowSummary>(`/flows/${processId}`),
  diagram: (processId: string) =>
    call<{ bpmn: string }>(`/flows/${processId}/diagram`),
  operations: () =>
    call<{ operation_id: string; description: string }[]>('/operations'),
  inspect: (bpmn: string) =>
    call<InspectReport>('/inspect', { method: 'POST', body: JSON.stringify({ bpmn }) }),
  publish: (payload: {
    bpmn: string
    name?: string
    dmn?: string | null
    forms: Record<string, unknown>
    lane_owners: Record<string, string[]>
  }) => call<FlowSummary>('/flows', { method: 'POST', body: JSON.stringify(payload) }),
  start: (processId: string) =>
    call<{ id: number; status: string }>(`/flows/${processId}/start`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  tasks: (mine: boolean) => call<TaskRow[]>(`/tasks?mine=${mine}`),
  task: (id: number) => call<TaskDetail>(`/tasks/${id}`),
  completeTask: (id: number, payload: Record<string, unknown>) =>
    call<{ id: number; instance_id: number; instance_status: string }>(
      `/tasks/${id}/complete`,
      { method: 'POST', body: JSON.stringify({ payload }) },
    ),

  instances: (scope: string, status?: string) =>
    call<InstanceRow[]>(
      `/instances?scope=${scope}${status ? `&status=${status}` : ''}`,
    ),
  instance: (id: number) => call<InstanceDetail>(`/instances/${id}`),
  lifecycle: (id: number, action: string) =>
    call<{ id: number; status: string }>(`/instances/${id}/${action}`, {
      method: 'POST',
    }),

  activity: () => call<ActivityRow[]>('/activity'),
}

export const STATUS_COLOR: Record<
  string,
  'success' | 'error' | 'warning' | 'info' | 'default'
> = {
  complete: 'success',
  error: 'error',
  terminated: 'error',
  suspended: 'warning',
  user_input_required: 'info',
  waiting: 'info',
  running: 'info',
  not_started: 'default',
}
