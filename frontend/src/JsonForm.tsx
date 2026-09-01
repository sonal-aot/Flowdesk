import { useState } from 'react'
import type { FormField, FormSchema } from './api'

/**
 * Renders a task's form from its JSON Schema.
 *
 * The library keeps no form definitions, so the schema comes from the files
 * uploaded alongside the diagram. When a diagram names no form -- or names one
 * nobody supplied -- the caller falls back to the free-form editor below, which
 * means any uploaded flow is runnable even with no forms at all.
 */
export function JsonForm({
  schema,
  busy,
  onSubmit,
}: {
  schema: FormSchema
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => void
}) {
  const properties = schema.properties ?? {}
  const required = new Set(schema.required ?? [])
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(
      Object.entries(properties)
        .filter(([, field]) => field.default !== undefined)
        .map(([key, field]) => [key, field.default]),
    ),
  )

  const missing = [...required].filter((key) => {
    const value = values[key]
    return value === undefined || value === '' || value === null
  })

  function set(key: string, value: unknown) {
    setValues({ ...values, [key]: value })
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(values)
      }}
    >
      {schema.title && <h3 className="form-title">{schema.title}</h3>}
      {schema.description && <p className="muted">{schema.description}</p>}

      {Object.entries(properties).map(([key, field]) => (
        <Field
          key={key}
          name={key}
          field={field}
          required={required.has(key)}
          value={values[key]}
          onChange={(value) => set(key, value)}
        />
      ))}

      {Object.keys(properties).length === 0 && (
        <p className="muted">This form has no fields.</p>
      )}

      <div className="modal-actions">
        <button className="primary" type="submit" disabled={busy || missing.length > 0}>
          {busy ? 'Submitting…' : 'Submit'}
        </button>
      </div>
      {missing.length > 0 && (
        <p className="note">Still needed: {missing.join(', ')}</p>
      )}
    </form>
  )
}

function Field({
  name,
  field,
  required,
  value,
  onChange,
}: {
  name: string
  field: FormField
  required: boolean
  value: unknown
  onChange: (value: unknown) => void
}) {
  const label = (
    <>
      {field.title ?? name}
      {required && <span className="req"> *</span>}
    </>
  )

  if (field.type === 'boolean') {
    return (
      <label className="check">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
    )
  }

  if (field.enum) {
    return (
      <label>
        {label}
        <select
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose…</option>
          {field.enum.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        {field.description && <span className="muted small">{field.description}</span>}
      </label>
    )
  }

  const numeric = field.type === 'integer' || field.type === 'number'
  return (
    <label>
      {label}
      <input
        type={numeric ? 'number' : field.format === 'date' ? 'date' : 'text'}
        value={value === undefined || value === null ? '' : String(value)}
        min={field.minimum}
        max={field.maximum}
        step={field.type === 'integer' ? 1 : undefined}
        onChange={(event) => {
          const raw = event.target.value
          if (!numeric) return onChange(raw)
          if (raw === '') return onChange(undefined)
          onChange(field.type === 'integer' ? parseInt(raw, 10) : Number(raw))
        }}
      />
      {field.description && <span className="muted small">{field.description}</span>}
    </label>
  )
}

/** Free-form key/value editor, for a task whose diagram named no form. */
export function FreeForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => void
}) {
  const [rows, setRows] = useState<{ key: string; value: string }[]>([
    { key: '', value: '' },
  ])

  function update(index: number, patch: Partial<{ key: string; value: string }>) {
    const next = rows.map((row, position) =>
      position === index ? { ...row, ...patch } : row,
    )
    if (next[next.length - 1].key !== '') next.push({ key: '', value: '' })
    setRows(next)
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(
          Object.fromEntries(
            rows
              .filter((row) => row.key.trim())
              .map((row) => [row.key.trim(), coerce(row.value)]),
          ),
        )
      }}
    >
      <h3 className="form-title">Task data</h3>
      <p className="muted">
        This step's diagram names no form, so set whatever the flow expects.
        Numbers and true/false are converted.
      </p>
      {rows.map((row, index) => (
        <div className="field-pair" key={index}>
          <input
            placeholder="name"
            value={row.key}
            onChange={(event) => update(index, { key: event.target.value })}
          />
          <input
            placeholder="value"
            value={row.value}
            onChange={(event) => update(index, { value: event.target.value })}
          />
        </div>
      ))}
      <div className="modal-actions">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Submitting…' : 'Submit'}
        </button>
      </div>
    </form>
  )
}

function coerce(raw: string): unknown {
  const text = raw.trim()
  if (text === 'true') return true
  if (text === 'false') return false
  if (text !== '' && !Number.isNaN(Number(text))) return Number(text)
  return raw
}
