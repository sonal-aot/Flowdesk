import { useEffect, useState } from 'react'
import { api, type Account } from './api'

/** Account chooser. Stands in for a real identity provider. */
export function SignIn({ onSignIn }: { onSignIn: (account: Account) => void }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null)
  const [company, setCompany] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  useEffect(() => {
    api
      .accounts()
      .then((rows) => {
        setAccounts(rows)
        setCompany(rows[0]?.company_id ?? null)
      })
      .catch((error) => setProblem(error.message))
  }, [])

  const companies = [...new Map(
    (accounts ?? []).map((row) => [row.company_id, row.company]),
  )]

  return (
    <div className="signin">
      <div className="signin-card">
        <div className="brand big">
          <span className="mark">⌗</span>
          <span>Flowdesk</span>
        </div>
        <p className="lede">Publish workflows, then run them.</p>

        {problem && <div className="alert">{problem}</div>}
        {accounts === null && !problem && <p className="muted">Loading…</p>}

        {companies.length > 1 && (
          <div className="segmented">
            {companies.map(([id, name]) => (
              <button
                key={id}
                className={company === id ? 'on' : ''}
                onClick={() => setCompany(id)}
              >
                {name}
              </button>
            ))}
          </div>
        )}

        <p className="muted small">Choose your account to continue</p>
        <ul className="people">
          {(accounts ?? [])
            .filter((row) => row.company_id === company)
            .map((row) => (
              <li key={`${row.company_id}:${row.username}`}>
                <button onClick={() => onSignIn(row)}>
                  <span className="avatar">{row.initials}</span>
                  <span className="who-block">
                    <strong>{row.name}</strong>
                    <span className="muted small">
                      {row.title} · {row.role}
                    </span>
                  </span>
                  <span className="chevron">→</span>
                </button>
              </li>
            ))}
        </ul>
      </div>
    </div>
  )
}
