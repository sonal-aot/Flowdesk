import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AppBar,
  Alert,
  Box,
  Chip,
  CssBaseline,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  ThemeProvider,
  Toolbar,
  Tooltip,
  Typography,
  createTheme,
  useMediaQuery,
} from '@mui/material'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import AssignmentIndIcon from '@mui/icons-material/AssignmentInd'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import HubIcon from '@mui/icons-material/Hub'
import LightModeIcon from '@mui/icons-material/LightMode'
import LogoutIcon from '@mui/icons-material/Logout'
import MenuIcon from '@mui/icons-material/Menu'
import SchemaIcon from '@mui/icons-material/Schema'
import TimelineIcon from '@mui/icons-material/Timeline'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { ApiError, api, token, type Me } from './api'
import { Login } from './Login'
import { Publish } from './Publish'
import { Activity, Flows, Runs, Work } from './screens'
import { NAV_RAIL_WIDTH, NAV_WIDTH, createFlowdeskTheme } from './theme'

type Page = 'flows' | 'work' | 'runs' | 'publish' | 'activity'

const THEME_KEY = 'flowdesk.theme'
const NAV_KEY = 'flowdesk.navCollapsed'

function readStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export default function App() {
  const [mode, setMode] = useState<'light' | 'dark'>(
    () => readStored(THEME_KEY, 'light') as 'light' | 'dark',
  )
  const theme = useMemo(() => createTheme(createFlowdeskTheme(mode)), [mode])
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))

  const [signedIn, setSignedIn] = useState(() => token.read() !== null)
  const [me, setMe] = useState<Me | null>(null)
  const [page, setPage] = useState<Page>('flows')
  const [collapsed, setCollapsed] = useState(() => readStored(NAV_KEY, 'false') === 'true')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [problem, setProblem] = useState<ApiError | null>(null)
  const [showTechnical, setShowTechnical] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [focusRun, setFocusRun] = useState<number | null>(null)
  const [userMenu, setUserMenu] = useState<HTMLElement | null>(null)

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  const fail = useCallback((raw: unknown) => {
    setShowTechnical(false)
    setProblem(
      raw instanceof ApiError
        ? raw
        : new ApiError(0, String((raw as Error)?.message ?? raw), ''),
    )
  }, [])

  function signOut() {
    token.clear()
    setSignedIn(false)
    setMe(null)
    setProblem(null)
    setUserMenu(null)
  }

  useEffect(() => {
    if (!signedIn) {
      setMe(null)
      return
    }
    let stale = false
    api
      .me()
      .then((data) => !stale && setMe(data))
      .catch((error) => {
        if (stale) return
        // An expired or revoked token must not lock the app up.
        if (error instanceof ApiError && error.status === 403) return signOut()
        fail(error)
      })
    return () => {
      stale = true
    }
  }, [signedIn, reloadKey])

  function flipTheme() {
    const next = mode === 'light' ? 'dark' : 'light'
    setMode(next)
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // ignore
    }
  }

  function toggleNav() {
    if (isMobile) return setMobileNavOpen((open) => !open)
    const next = !collapsed
    setCollapsed(next)
    try {
      localStorage.setItem(NAV_KEY, String(next))
    } catch {
      // ignore
    }
  }

  if (!signedIn) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Login onSignedIn={() => setSignedIn(true)} />
      </ThemeProvider>
    )
  }

  const items: { key: Page; label: string; icon: React.ReactNode; badge?: number }[] = [
    { key: 'flows', label: 'Flows', icon: <SchemaIcon /> },
    {
      key: 'work',
      label: 'My work',
      icon: <AssignmentIndIcon />,
      badge: me?.open_tasks || undefined,
    },
    { key: 'runs', label: 'Runs', icon: <TimelineIcon /> },
    ...(me?.can_publish
      ? [{ key: 'publish' as Page, label: 'Publish', icon: <UploadFileIcon /> }]
      : []),
    ...(me?.can_view_all
      ? [{ key: 'activity' as Page, label: 'Activity', icon: <HubIcon /> }]
      : []),
  ]

  const navWidth = collapsed && !isMobile ? NAV_RAIL_WIDTH : NAV_WIDTH

  const nav = (
    <List sx={{ pt: 1 }}>
      {items.map((item) => (
        <Tooltip
          key={item.key}
          title={collapsed && !isMobile ? item.label : ''}
          placement="right"
        >
          <ListItemButton
            selected={page === item.key}
            onClick={() => {
              setFocusRun(null)
              setPage(item.key)
              setMobileNavOpen(false)
            }}
            sx={{ mx: 1, borderRadius: 1, mb: 0.25, minHeight: 44 }}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
            {(!collapsed || isMobile) && (
              <ListItemText
                primary={item.label}
                slotProps={{ primary: { sx: { fontSize: 14 } } }}
              />
            )}
            {(!collapsed || isMobile) && item.badge ? (
              <Chip size="small" color="primary" label={item.badge} />
            ) : null}
          </ListItemButton>
        </Tooltip>
      ))}
    </List>
  )

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
        <AppBar color="inherit" sx={{ position: "fixed", borderBottom: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
            zIndex: (t) => t.zIndex.drawer + 1 }}>
          <Toolbar variant="dense" sx={{ gap: 1.5, minHeight: 56 }}>
            <IconButton edge="start" onClick={toggleNav} size="small">
              <MenuIcon />
            </IconButton>
            <AccountTreeIcon color="primary" sx={{ fontSize: "small" }} />
            <Typography sx={{ fontWeight: 650, letterSpacing: "-0.01em" }}>
              Flowdesk
            </Typography>
            <Box sx={{ flex: 1 }} />
            {me && (
              <Chip
                size="small"
                variant="outlined"
                label={me.company}
                sx={{ display: { xs: 'none', sm: 'flex' } }}
              />
            )}
            <Tooltip title={mode === 'light' ? 'Dark theme' : 'Light theme'}>
              <IconButton onClick={flipTheme} size="small">
                {mode === 'light' ? (
                  <DarkModeIcon sx={{ fontSize: "small" }} />
                ) : (
                  <LightModeIcon sx={{ fontSize: "small" }} />
                )}
              </IconButton>
            </Tooltip>
            <Tooltip title={me ? `${me.name} · ${me.role}` : ''}>
              <IconButton size="small" onClick={(event) => setUserMenu(event.currentTarget)}>
                <Box
                  sx={{
                    width: 30,
                    height: 30,
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    display: 'grid',
                    placeItems: 'center',
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {(me?.name ?? '?')
                    .split(' ')
                    .slice(0, 2)
                    .map((part) => part[0])
                    .join('')}
                </Box>
              </IconButton>
            </Tooltip>
            <Menu
              anchorEl={userMenu}
              open={userMenu !== null}
              onClose={() => setUserMenu(null)}
            >
              <Box sx={{ px: 2, py: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {me?.name}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  {me?.title}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  role {me?.role} · engine role {me?.library_role}
                </Typography>
              </Box>
              <Divider />
              <MenuItem onClick={signOut}>
                <ListItemIcon>
                  <LogoutIcon sx={{ fontSize: "small" }} />
                </ListItemIcon>
                Sign out
              </MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>

        <Drawer
          variant={isMobile ? 'temporary' : 'permanent'}
          open={isMobile ? mobileNavOpen : true}
          onClose={() => setMobileNavOpen(false)}
          sx={{
            width: isMobile ? NAV_WIDTH : navWidth,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: isMobile ? NAV_WIDTH : navWidth,
              boxSizing: 'border-box',
              bgcolor: 'background.paper',
              borderRight: 1,
              borderColor: 'divider',
              overflowX: 'hidden',
            },
          }}
        >
          {!isMobile && <Toolbar variant="dense" sx={{ minHeight: 56 }} />}
          {nav}
        </Drawer>

        <Box component="main" sx={{ flexGrow: 1, minWidth: 0 }}>
          <Toolbar variant="dense" sx={{ minHeight: 56 }} />
          <Box sx={{ maxWidth: 1000, mx: 'auto', p: { xs: 2, sm: 3 } }}>
            {problem && (
              <Alert
                severity="error"
                sx={{ mb: 2 }}
                action={
                  <>
                    {problem.technical && (
                      <IconButton
                        size="small"
                        onClick={() => setShowTechnical((on) => !on)}
                      >
                        <Typography variant="caption">
                          {showTechnical ? 'less' : 'details'}
                        </Typography>
                      </IconButton>
                    )}
                    <IconButton size="small" onClick={() => setProblem(null)}>
                      <Typography variant="caption">dismiss</Typography>
                    </IconButton>
                  </>
                }
              >
                {problem.message}
                {showTechnical && problem.technical && (
                  <Box component="pre" sx={{ mt: 1, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                    {problem.technical}
                  </Box>
                )}
              </Alert>
            )}

            {me && page === 'flows' && (
              <Flows
                reloadKey={reloadKey}
                onStarted={(id) => {
                  reload()
                  setFocusRun(id)
                  setPage('runs')
                }}
                onError={fail}
              />
            )}
            {me && page === 'work' && (
              <Work reloadKey={reloadKey} onChanged={reload} onError={fail} />
            )}
            {me && page === 'runs' && (
              <Runs
                me={me}
                reloadKey={reloadKey}
                focus={focusRun}
                onChanged={reload}
                onError={fail}
              />
            )}
            {me && page === 'publish' && (
              <Publish me={me} onPublished={reload} onError={fail} />
            )}
            {me && page === 'activity' && (
              <Activity reloadKey={reloadKey} onError={fail} />
            )}
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  )
}
