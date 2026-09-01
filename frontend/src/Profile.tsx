import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { ApiError, api, token, type Me } from './api'
import { PageHead } from './screens'

/**
 * Your own profile: display name, email and password.
 *
 * Name and email live on the library's `user` table — there is no user
 * management API, so the app writes those two fields itself. Changing a password
 * signs every other session out, and hands this one a fresh token so it stays
 * signed in.
 */
export function Profile({
  me,
  onChanged,
  onError,
}: {
  me: Me
  onChanged: () => void
  onError: (error: unknown) => void
}) {
  const [name, setName] = useState(me.name)
  const [email, setEmail] = useState(me.email)
  const [savedDetails, setSavedDetails] = useState<string | null>(null)
  const [savingDetails, setSavingDetails] = useState(false)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [savedPassword, setSavedPassword] = useState<string | null>(null)
  const [savingPassword, setSavingPassword] = useState(false)
  const [passwordProblem, setPasswordProblem] = useState<string | null>(null)

  useEffect(() => {
    setName(me.name)
    setEmail(me.email)
  }, [me.name, me.email])

  const detailsChanged = name !== me.name || email !== me.email
  const passwordReady =
    current.length > 0 && next.length >= 8 && next === confirm && next !== current

  async function saveDetails(event: React.FormEvent) {
    event.preventDefault()
    setSavingDetails(true)
    setSavedDetails(null)
    try {
      await api.updateProfile({ name, email })
      setSavedDetails('Saved.')
      onChanged()
    } catch (error) {
      onError(error)
    } finally {
      setSavingDetails(false)
    }
  }

  async function savePassword(event: React.FormEvent) {
    event.preventDefault()
    setSavingPassword(true)
    setSavedPassword(null)
    setPasswordProblem(null)
    try {
      const result = await api.changePassword(current, next)
      // The old token died with the old password; keep this session alive.
      token.write(result.token)
      setCurrent('')
      setNext('')
      setConfirm('')
      setSavedPassword('Password changed. Any other sessions have been signed out.')
    } catch (error) {
      setPasswordProblem(
        error instanceof ApiError ? error.message : String(error),
      )
    } finally {
      setSavingPassword(false)
    }
  }

  return (
    <>
      <PageHead title="Profile" subtitle={`${me.username} · ${me.company}`} />

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h2" gutterBottom>
            Your details
          </Typography>
          <form onSubmit={saveDetails}>
            <Stack spacing={2} sx={{ maxWidth: 420 }}>
              <TextField
                size="small"
                label="Name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                helperText="How you appear on tasks and in run history"
              />
              <TextField
                size="small"
                label="Email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={savingDetails || !detailsChanged}
                >
                  {savingDetails ? 'Saving…' : 'Save details'}
                </Button>
                {savedDetails && (
                  <Typography variant="body2" sx={{ color: 'success.main' }}>
                    {savedDetails}
                  </Typography>
                )}
              </Stack>
            </Stack>
          </form>
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h2" gutterBottom>
            Password
          </Typography>
          {passwordProblem && (
            <Alert severity="error" sx={{ mb: 2, maxWidth: 420 }}>
              {passwordProblem}
            </Alert>
          )}
          {savedPassword && (
            <Alert severity="success" sx={{ mb: 2, maxWidth: 420 }}>
              {savedPassword}
            </Alert>
          )}
          <form onSubmit={savePassword}>
            <Stack spacing={2} sx={{ maxWidth: 420 }}>
              <TextField
                size="small"
                type="password"
                label="Current password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
              <TextField
                size="small"
                type="password"
                label="New password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                error={next.length > 0 && next.length < 8}
                helperText="At least 8 characters"
              />
              <TextField
                size="small"
                type="password"
                label="Repeat new password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                error={confirm.length > 0 && confirm !== next}
                helperText={
                  confirm.length > 0 && confirm !== next ? 'These do not match' : ' '
                }
              />
              <Box>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={savingPassword || !passwordReady}
                >
                  {savingPassword ? 'Changing…' : 'Change password'}
                </Button>
              </Box>
            </Stack>
          </form>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h2" gutterBottom>
            Your access
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1.5 }}>
            {me.title} in {me.company}. Roles are set by an administrator, not
            here.
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }} useFlexGap>
            <Chip size="small" label={`role: ${me.role}`} color="primary" />
            <Chip
              size="small"
              variant="outlined"
              label={`workflow engine role: ${me.library_role}`}
            />
            {me.can_publish && <Chip size="small" variant="outlined" label="publish flows" />}
            {me.can_operate && <Chip size="small" variant="outlined" label="operate runs" />}
            {me.can_view_all && (
              <Chip size="small" variant="outlined" label="see everyone's runs" />
            )}
          </Stack>
        </CardContent>
      </Card>
    </>
  )
}
