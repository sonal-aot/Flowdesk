import Form from '@rjsf/mui'
import validator from '@rjsf/validator-ajv8'
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
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

/* --------------------------------------------------------- instructions */

/** `**bold**`, the only inline markup these templates use. */
function inline(text: string, key: number) {
  return (
    <span key={key}>
      {text.split('**').map((part, index) =>
        index % 2 === 1 ? <strong key={index}>{part}</strong> : part,
      )}
    </span>
  )
}

function cells(row: string): string[] {
  return row
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim())
}

const SEPARATOR = /^[\s|:-]+$/

/**
 * A step's `instructionsForEndUser`, rendered.
 *
 * The modeller writes these as markdown with Jinja in it; the server fills in
 * the run's data, and this shows the result. Deliberately not a markdown
 * implementation -- headings, bold and tables are what these templates use, and
 * anything else falls through as text.
 *
 * ponytail: hand-rolled subset. If a template needs links, lists or code, pull
 * in a real renderer rather than growing this.
 */
export function Instructions({ text }: { text: string }) {
  const lines = text.replace(/\r/g, '').split('\n')
  const blocks: React.ReactNode[] = []
  let paragraph: string[] = []

  function flush() {
    if (paragraph.length === 0) return
    blocks.push(
      <Typography key={blocks.length} variant="body2" sx={{ mb: 1 }}>
        {paragraph.map((line, index) => inline(line, index))}
      </Typography>,
    )
    paragraph = []
  }

  for (let at = 0; at < lines.length; at += 1) {
    const line = lines[at]

    if (line.trim() === '') {
      flush()
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      flush()
      blocks.push(
        <Typography
          key={blocks.length}
          variant={heading[1].length <= 2 ? 'h2' : 'body2'}
          sx={{ mt: blocks.length ? 1.5 : 0, mb: 0.75, fontWeight: 600 }}
        >
          {heading[2]}
        </Typography>,
      )
      continue
    }

    if (line.trimStart().startsWith('|')) {
      flush()
      const rows: string[] = []
      while (at < lines.length && lines[at].trimStart().startsWith('|')) {
        if (!SEPARATOR.test(lines[at])) rows.push(lines[at])
        at += 1
      }
      at -= 1
      const [header, ...body] = rows
      blocks.push(
        <TableContainer
          key={blocks.length}
          component={Paper}
          variant="outlined"
          sx={{ mb: 1.5, maxHeight: 320 }}
        >
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {cells(header ?? '').map((cell, index) => (
                  <TableCell key={index} sx={{ fontWeight: 600 }}>
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {body.map((row, rowIndex) => (
                <TableRow key={rowIndex}>
                  {cells(row).map((cell, index) => (
                    <TableCell key={index}>{inline(cell, index)}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>,
      )
      continue
    }

    paragraph.push(line)
  }
  flush()

  return <Box sx={{ mb: 2 }}>{blocks}</Box>
}

/** A step that only has to be read and acknowledged -- a BPMN manual task. */
export function Acknowledge({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => void
}) {
  return (
    <Button
      variant="contained"
      disabled={busy}
      onClick={() => onSubmit({})}
      sx={{ mt: 1 }}
    >
      {busy ? 'Saving…' : 'Done'}
    </Button>
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
