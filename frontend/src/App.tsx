import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, session, type Account, type Me, type Who } from './api'
import { Publish } from './Publish'
import { Activity, Flows, Instances, Work } from './screens'
import { SignIn } from './SignIn'

type Page = 'flows' | 'work' | 'runs' | 'publish' | 'activity'

export default function App() {
  const [who, setWho] = useState<Who | null>(session.read())
  const [me, setMe] = useState<Me | null>(null)
  const [page, setPage] = useState<Page>('flows')
  const [problem, setProblem] = useState<ApiError | null>(null)
  const [showTechnical, setShowTechnical] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [focusRun, setFocusRun] = useState<number | null>(null)

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  const fail = useCallback((raw: unknown) => {
    setShowTechnical(false)
    setProblem(
      raw instanceof ApiError
        ? raw
        : new ApiError(0, String((raw as Error)?.message ?? raw), ''),
    )
  }, [])

  useEffect(() => {
    if (who === null) {
      setMe(null)
      return
    }
    let stale = false
    api
      .me(who)
      .then((data) => !stale && setMe(data))
      .catch((error) => {
        if (stale) return
        fail(error)
        if (error instanceof ApiError && error.status >= 400) signOut()
      })
    return () => {
      stale = true
    }
  }, [who, reloadKey])

  function signIn(account: Account) {
    session.write(account)
    setWho({ company_id: account.company_id, username: account.username })
    setPage('flows')
    setProblem(null)
  }

  function signOut() {
    session.clear()
    setWho(null)
    setMe(null)
  }

  if (who === null) return <SignIn onSignIn={signIn} />

  const pages: { key: Page; label: string; badge?: number }[] = [
    { key: 'flows', label: 'Flows' },
    { key: 'work', label: 'My work', badge: me?.open_tasks || undefined },
    { key: 'runs', label: 'Runs' },
    ...(me?.can_publish ? [{ key: 'publish' as Page, label: 'Publish' }] : []),
    { key: 'activity', label: 'Activity' },
  ]

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark">⌗</span>
          <span>Flowdesk</span>
        </div>
        <nav>
          {pages.map((entry) => (
            <button
              key={entry.key}
              className={page === entry.key ? 'on' : ''}
              onClick={() => {
                setFocusRun(null)
                setPage(entry.key)
              }}
            >
              {entry.label}
              {entry.badge ? <span className="count">{entry.badge}</span> : null}
            </button>
          ))}
        </nav>
        <div className="account">
          <div className="who-block right-align">
            <strong>{me?.name ?? '…'}</strong>
            <span className="muted small">
              {me?.company} · {me?.role}
            </span>
          </div>
          <button className="ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <main>
        {problem && (
          <div className="alert">
            <div>
              <strong>{problem.message}</strong>
              {showTechnical && problem.technical && <pre>{problem.technical}</pre>}
            </div>
            <div className="alert-actions">
              {problem.technical && (
                <button className="ghost" onClick={() => setShowTechnical((on) => !on)}>
                  {showTechnical ? 'Hide details' : 'Details'}
                </button>
              )}
              <button className="ghost" onClick={() => setProblem(null)}>
                Dismiss
              </button>
            </div>
          </div>
        )}

        {me && page === 'flows' && (
          <Flows
            who={who}
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
          <Work who={who} reloadKey={reloadKey} onChanged={reload} onError={fail} />
        )}
        {me && page === 'runs' && (
          <Instances
            who={who}
            me={me}
            reloadKey={reloadKey}
            focus={focusRun}
            onChanged={reload}
            onError={fail}
          />
        )}
        {me && page === 'publish' && (
          <Publish who={who} me={me} onPublished={reload} onError={fail} />
        )}
        {me && page === 'activity' && (
          <Activity who={who} reloadKey={reloadKey} onError={fail} />
        )}
      </main>
    </div>
  )
}
