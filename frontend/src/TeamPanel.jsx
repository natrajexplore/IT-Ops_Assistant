import { useEffect, useRef, useState } from 'react'
import ApprovalCard from './ApprovalCard.jsx'

export default function TeamPanel({ team, state, onRefresh, onSend, onDecide }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)
  const { report, messages, pending, loading } = state

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending, report])

  function submit(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    onSend(text)
  }

  return (
    <div className="team-panel">
      <header className="team-header">
        <div>
          <span className="team-icon">{team.icon}</span>
          <span className="team-name">{team.name}</span>
        </div>
        <button className="ghost-button" onClick={onRefresh} disabled={loading}>
          Refresh status
        </button>
      </header>

      <div className="team-body">
        {report && (
          <div className="report-grid">
            <div className="report-card">
              <div className="report-card-title">Currently Observing</div>
              <div className="report-card-text">{report.observations}</div>
            </div>
            <div className="report-card">
              <div className="report-card-title">Mitigation & Upgrade Plan</div>
              <div className="report-card-text">{report.mitigation_plan}</div>
            </div>
          </div>
        )}

        {!report && !pending && loading && (
          <p className="empty-hint">Generating status report…</p>
        )}

        {messages.length > 0 && (
          <div className="chat-thread">
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>
                {m.text}
              </div>
            ))}
          </div>
        )}

        {pending && (
          <ApprovalCard
            actions={pending.actions}
            topology={team.topology}
            disabled={loading}
            onDecide={(approved) => onDecide(pending.requestId, pending.actions, approved)}
          />
        )}

        {loading && (report || messages.length > 0) && (
          <div className="bubble assistant loading">…</div>
        )}

        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask ${team.name} a question…`}
          disabled={loading || !!pending}
        />
        <button type="submit" disabled={loading || !!pending || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}
