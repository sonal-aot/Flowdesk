import { type PaletteMode, type ThemeOptions } from '@mui/material'
import { blue, green, grey, orange, red } from '@mui/material/colors'

/**
 * Palette shaped after m8flow's own theme: a grey page, white surfaces and nav,
 * MUI's status colours, and the same light/dark switch persisted in
 * localStorage.
 */
export function createFlowdeskTheme(mode: PaletteMode): ThemeOptions {
  const light = mode === 'light'
  return {
    palette: {
      mode,
      primary: { main: light ? blue[700] : blue[300] },
      success: {
        main: light ? green[600] : green[400],
        light: green[100],
        dark: green[800],
      },
      warning: {
        main: light ? orange[700] : orange[400],
        light: orange[100],
        dark: orange[800],
      },
      error: { main: light ? red[600] : red[400], light: red[100], dark: red[800] },
      info: { main: light ? blue[600] : blue[300] },
      background: {
        default: light ? grey[50] : '#121212',
        paper: light ? '#ffffff' : '#1c2027',
      },
      text: {
        primary: light ? grey[900] : grey[100],
        secondary: light ? grey[700] : grey[400],
      },
      divider: light ? grey[300] : grey[800],
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily:
        '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      h1: { fontSize: '1.5rem', fontWeight: 600 },
      h2: { fontSize: '1.05rem', fontWeight: 600 },
      button: { textTransform: 'none', fontWeight: 500 },
    },
    components: {
      MuiPaper: { defaultProps: { elevation: 0 } },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiTableCell: { styleOverrides: { root: { paddingTop: 10, paddingBottom: 10 } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
    },
  }
}

export const NAV_WIDTH = 232
export const NAV_RAIL_WIDTH = 60
