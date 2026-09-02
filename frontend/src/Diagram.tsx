import { useEffect, useRef, useState } from 'react'
import { Alert, Box } from '@mui/material'
import BpmnViewer from 'bpmn-js/lib/NavigatedViewer'
import 'bpmn-js/dist/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn.css'
import type { ProgressStep } from './api'

/**
 * The diagram, as it was drawn — and where a run has got to on it.
 *
 * bpmn-js is what the modeller and m8flow both use, so a diagram looks the same
 * here as wherever it was drawn. `NavigatedViewer` is the read-only build with
 * pan and zoom and no editing.
 *
 * Progress is painted by marking elements and colouring them in CSS: the viewer
 * owns the SVG, so reaching into it to set attributes would be undone on the
 * next redraw.
 */

const MARKER: Record<ProgressStep['state'], string> = {
  done: 'flowdesk-done',
  waiting: 'flowdesk-waiting',
  upcoming: 'flowdesk-upcoming',
  not_needed: 'flowdesk-skipped',
  error: 'flowdesk-error',
}

export function Diagram({
  bpmn,
  progress = [],
  height = 380,
}: {
  bpmn: string
  /** Optional: colour each element by where this run has got to. */
  progress?: ProgressStep[]
  height?: number | string
}) {
  const host = useRef<HTMLDivElement | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  useEffect(() => {
    if (!host.current || !bpmn.trim()) return
    const viewer = new BpmnViewer({ container: host.current })
    let stale = false

    viewer
      .importXML(bpmn)
      .then(() => {
        if (stale) return
        // bpmn-js types `get` as unknown; these two are all we use.
        const canvas = viewer.get('canvas') as {
          zoom: (how: string, centre: string) => void
          addMarker: (elementId: string, marker: string) => void
        }
        canvas.zoom('fit-viewport', 'auto')
        for (const step of progress) {
          try {
            canvas.addMarker(step.element_id, MARKER[step.state])
          } catch {
            // An element in the trace that is not in this version of the
            // diagram. Nothing to colour; nothing to fix.
          }
        }
      })
      .catch((error: Error) => {
        if (!stale) setProblem(error.message)
      })

    return () => {
      stale = true
      viewer.destroy()
    }
  }, [bpmn, progress])

  if (problem) {
    return <Alert severity="warning">This diagram could not be drawn: {problem}</Alert>
  }

  return (
    <Box
      ref={host}
      sx={{
        height,
        width: '100%',
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        overflow: 'hidden',
        // The viewer draws plain SVG; these say what state each element is in.
        '& .flowdesk-done .djs-visual > :nth-of-type(1)': {
          stroke: '#2e7d32 !important',
          fill: '#e8f5e9 !important',
        },
        '& .flowdesk-waiting .djs-visual > :nth-of-type(1)': {
          stroke: '#0288d1 !important',
          fill: '#e1f5fe !important',
          strokeWidth: '3px !important',
        },
        '& .flowdesk-error .djs-visual > :nth-of-type(1)': {
          stroke: '#c62828 !important',
          fill: '#ffebee !important',
        },
        '& .flowdesk-skipped': { opacity: 0.35 },
        '& .flowdesk-upcoming': { opacity: 0.55 },
        // A connection's arrow is a path, not a shape, so it is left alone.
        '& .djs-connection .djs-visual > :nth-of-type(1)': { fill: 'none !important' },
      }}
    />
  )
}
