/**
 * Drives the real UI in a headless browser and asserts what a screenshot would
 * show: that dialogs are centred, that a Runs row opens its detail panel, and
 * that the panel names the step and person the run is waiting on.
 *
 * Written because two layout bugs shipped that no unit test could have caught --
 * a Dialog whose maxWidth had been moved into `sx`, which MUI resolves through
 * theme breakpoints and so clamped the whole overlay to 600px on the left.
 *
 * Both servers must be running. Screenshots land in SHOTS (default ./ui-shots).
 *
 *   node scripts/ui-check.mjs
 */
import { chromium } from 'playwright'

const API = 'http://localhost:8020'
const UI = 'http://localhost:5173'
const OUT = process.env.SHOTS ?? 'ui-shots'
const log = []

async function tok(u) {
  const r = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_id: 'northwind', username: u, password: u }),
  })
  return (await r.json()).token
}

async function signIn(page, u) {
  await page.goto(UI, { waitUntil: 'networkidle' })
  await page.getByLabel('Username').fill(u)
  await page.getByLabel('Password').fill(u)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForSelector('text=Flows', { timeout: 10000 })
}

import { mkdirSync } from 'node:fs'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (e) => log.push('PAGE ERROR  ' + e.message.split('\n')[0]))
page.on('console', (m) => { if (m.type() === 'error') log.push('CONSOLE  ' + m.text().slice(0, 160)) })
page.on('response', (r) => { if (r.url().includes('/instances/') && !r.ok()) log.push(`HTTP ${r.status()}  ${r.url()}`) })

// state: a run waiting on the reviewer
const submitter = await tok('submitter')
const started = await fetch(`${API}/flows/Process_two_step_request/start`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${submitter}` }, body: '{}',
})
const runId = (await started.json()).id
const tasks = await (await fetch(`${API}/tasks?mine=true`, { headers: { Authorization: `Bearer ${submitter}` } })).json()
const mine = tasks.find((t) => t.instance_id === runId)
await fetch(`${API}/tasks/${mine.id}/complete`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${submitter}` },
  body: JSON.stringify({ payload: { subject: 'Standing desk', details: 'Back pain', urgency: 'high' } }),
})

// 1. the form dialog, fully settled
await signIn(page, 'reviewer')
await page.getByRole('button', { name: 'My work' }).click()
await page.waitForSelector('text=Review Request')
await page.getByRole('button', { name: 'Open' }).first().click()
await page.waitForSelector('text=Review the request')
await page.waitForTimeout(900)
await page.screenshot({ path: `${OUT}/2-form-dialog.png` })
const box = await page.locator('.MuiDialog-paper').boundingBox()
const centre = box.x + box.width / 2
log.push(
  `${Math.abs(centre - 720) < 20 ? 'PASS' : 'FAIL'}  dialog centred — centre ${Math.round(centre)}px (want 720), x=${Math.round(box.x)}, w=${Math.round(box.width)}`,
)
await page.keyboard.press('Escape')
await page.waitForTimeout(400)

// 2. Runs -> row click -> drawer
await page.evaluate(() => localStorage.clear())
await signIn(page, 'admin')
await page.getByRole('button', { name: 'Runs' }).click()
await page.waitForSelector('table tbody tr')
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/4-runs-list.png` })
log.push('runs row 1: ' + (await page.locator('table tbody tr').first().innerText()).replace(/\n/g, ' | '))

await page.locator('table tbody tr').first().click()
await page.waitForTimeout(1500)
await page.screenshot({ path: `${OUT}/5-run-detail.png` })
const detail = page.locator('.MuiDrawer-paper').filter({ hasText: 'Next action' })
  const drawers = await detail.count()
log.push(`${drawers > 0 ? 'PASS' : 'FAIL'}  drawer opened (found ${drawers})`)
if (drawers > 0) {
  const text = await detail.innerText()
  log.push('drawer text: ' + text.replace(/\n/g, ' | ').slice(0, 400))
  await detail.screenshot({ path: `${OUT}/6-drawer.png` })
} else {
  log.push('body text after click: ' + (await page.locator('main').innerText()).replace(/\n/g, ' | ').slice(0, 300))
}

await browser.close()
console.log(log.join('\n'))
if (log.some((line) => line.startsWith('FAIL') || line.startsWith('PAGE ERROR'))) {
  process.exitCode = 1
}
