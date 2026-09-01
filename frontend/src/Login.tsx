import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import { ApiError, api, token, type Company } from './api'

/**
 * Sign-in screen.
 *
 * m8flow authenticates through Keycloak; there is no identity provider here, so
 * this is a password form against the app's own credential table. The demo
 * accounts are listed underneath because the passwords are demo values — a real
 * deployment would have neither the list nor this form.
 */
export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const [companies, setCompanies] = useState<Company[]>([])
  const [company, setCompany] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .companies()
      .then((rows) => {
        setCompanies(rows)
        setCompany(rows[0]?.company_id ?? '')
      })
      .catch((error: ApiError) => setProblem(error.message))
  }, [])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setProblem(null)
    try {
      const result = await api.login(company, username, password)
      token.write(result.token)
      onSignedIn()
    } catch (error) {
      setProblem(
        error instanceof ApiError
          ? error.status === 403
            ? 'That company, username or password is not right.'
            : error.message
          : String(error),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        p: 3,
        bgcolor: 'background.default',
      }}
    >
      <Box sx={{ width: '100%', maxWidth: 420 }}>
        <Card variant="outlined">
          <CardContent sx={{ p: 4 }}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 0.5 }}>
              <AccountTreeIcon color="primary" />
              <Typography variant="h1">Flowdesk</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Sign in to publish and run workflows.
            </Typography>

            {problem && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {problem}
              </Alert>
            )}

            <form onSubmit={submit}>
              <Stack spacing={2}>
                <TextField
                  select
                  size="small"
                  label="Company"
                  value={company}
                  onChange={(event) => setCompany(event.target.value)}
                >
                  {companies.map((row) => (
                    <MenuItem key={row.company_id} value={row.company_id}>
                      {row.company}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  size="small"
                  label="Username"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
                <TextField
                  size="small"
                  type="password"
                  label="Password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={busy || !company || !username || !password}
                >
                  {busy ? 'Signing in…' : 'Sign in'}
                </Button>
              </Stack>
            </form>
          </CardContent>
        </Card>

      </Box>
    </Box>
  )
}
