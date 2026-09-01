import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import { ApiError, api, token, type Company, type DemoAccount } from './api'

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
  const [accounts, setAccounts] = useState<DemoAccount[]>([])
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
    api.demoAccounts().then(setAccounts).catch(() => setAccounts([]))
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

  function useAccount(name: string) {
    setUsername(name)
    setPassword(name)
    setProblem(null)
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
      <Stack spacing={2} sx={{ width: '100%', maxWidth: 460 }}>
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

        <Card variant="outlined">
          <CardContent>
            <Typography variant="h2" gutterBottom>
              Demo accounts
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Each password is the same as the username. Every company has all
              four.
            </Typography>
            <Divider sx={{ mb: 1 }} />
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Account</TableCell>
                  <TableCell>Can</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {accounts.map((row) => (
                  <TableRow key={row.username} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {row.username}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {row.name} · {row.title}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {row.capabilities}
                      </Typography>
                      <Box sx={{ mt: 0.5 }}>
                        <Chip
                          label={`engine role: ${row.library_role}`}
                          size="small"
                          variant="outlined"
                        />
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => useAccount(row.username)}>
                        Use
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  )
}
