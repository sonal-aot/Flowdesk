import Form from '@rjsf/mui'
import validator from '@rjsf/validator-ajv8'
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material'
import { useState } from 'react'
import type { FormSchema } from './api'

/**
 * A task's form, rendered from the JSON Schema published with the diagram.
 *
 * m8flow uses react-jsonschema-form with the MUI theme for exactly this, so the
 * same schemas render the same way here. The library keeps no form definitions,
 * so the schema comes from the files uploaded alongside the BPMN.
 */
export function TaskForm({
  schema,
  busy,
  onSubmit,
}: {
  schema: FormSchema
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => void
}) {
  return (
    <Box sx={{ '& .MuiFormControl-root': { mb: 1 } }}>
      <Form
        schema={schema as object}
        validator={validator}
        disabled={busy}
        onSubmit={({ formData }) => onSubmit(formData ?? {})}
        showErrorList={false}
      >
        <Button type="submit" variant="contained" disabled={busy} sx={{ mt: 1 }}>
          {busy ? 'Submitting…' : 'Submit'}
        </Button>
      </Form>
    </Box>
  )
}

/** Free-form editor, for a step whose diagram named no form. */
export function FreeForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => void
}) {
  const [rows, setRows] = useState([{ key: '', value: '' }])

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
      <Alert severity="info" sx={{ mb: 2 }}>
        This step's diagram names no form, so set whatever the flow expects.
        Numbers and true/false are converted.
      </Alert>
      <Stack spacing={1}>
        {rows.map((row, index) => (
          <Stack direction="row" spacing={1} key={index}>
            <TextField
              size="small"
              label="name"
              value={row.key}
              onChange={(event) => update(index, { key: event.target.value })}
              fullWidth
            />
            <TextField
              size="small"
              label="value"
              value={row.value}
              onChange={(event) => update(index, { value: event.target.value })}
              fullWidth
            />
          </Stack>
        ))}
      </Stack>
      <Button type="submit" variant="contained" disabled={busy} sx={{ mt: 2 }}>
        {busy ? 'Submitting…' : 'Submit'}
      </Button>
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

export function FormTitle({ schema }: { schema: FormSchema }) {
  if (!schema.title) return null
  return (
    <Typography variant="body2" color="text.secondary">
      {schema.title}
    </Typography>
  )
}
