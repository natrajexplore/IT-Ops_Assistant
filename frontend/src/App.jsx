import { useEffect, useState } from 'react'
import './App.css'
import Sidebar from './Sidebar.jsx'
import TeamPanel from './TeamPanel.jsx'
import ApprovalQueue from './ApprovalQueue.jsx'
import {
  getTeams,
  refreshTeam,
  messageTeam,
  approveRequest,
  getApprovalQueue,
  getChangeRequestHistory,
} from './api.js'

const emptyTeamState = () => ({ report: null, messages: [], pending: null, loading: false })

export default function App() {
  const [teams, setTeams] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [teamState, setTeamState] = useState({})
  const [queue, setQueue] = useState([])
  const [history, setHistory] = useState([])
  const [queueLoading, setQueueLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getTeams()
      .then((t) => {
        setTeams(t)
        if (t.length > 0) setActiveId(t[0].id)
      })
      .catch((e) => setError(e.message))
  }, [])

  function refreshQueueAndHistory() {
    getApprovalQueue().then(setQueue).catch(() => {})
    getChangeRequestHistory().then(setHistory).catch(() => {})
  }

  useEffect(() => {
    refreshQueueAndHistory()
    const t = setInterval(refreshQueueAndHistory, 8000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (activeId && activeId !== 'queue' && !teamState[activeId]) {
      loadTeam(activeId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  function applyResult(id, data) {
    setTeamState((s) => {
      const prev = s[id] || emptyTeamState()
      if (data.status === 'pending_approval') {
        return {
          ...s,
          [id]: { ...prev, pending: { requestId: data.request_id, actions: data.actions }, loading: false },
        }
      }
      const updated = { ...prev, pending: null, loading: false }
      if (data.report) updated.report = data.report
      if (data.reply) updated.messages = [...prev.messages, { role: 'assistant', text: data.reply }]
      return { ...s, [id]: updated }
    })
  }

  async function loadTeam(id) {
    setTeamState((s) => ({ ...s, [id]: { ...emptyTeamState(), loading: true } }))
    try {
      const data = await refreshTeam(id)
      applyResult(id, data)
    } catch (e) {
      setError(e.message)
      setTeamState((s) => ({ ...s, [id]: { ...s[id], loading: false } }))
    }
  }

  async function handleSend(id, text) {
    setTeamState((s) => ({
      ...s,
      [id]: { ...s[id], messages: [...s[id].messages, { role: 'user', text }], loading: true },
    }))
    try {
      const data = await messageTeam(id, text)
      applyResult(id, data)
    } catch (e) {
      setError(e.message)
      setTeamState((s) => ({ ...s, [id]: { ...s[id], loading: false } }))
    }
  }

  async function handleDecide(requestId, actions, approved, teamId) {
    setQueueLoading(true)
    setTeamState((s) => (s[teamId] ? { ...s, [teamId]: { ...s[teamId], loading: true } } : s))
    const decisions = {}
    for (const a of actions) decisions[a.call_id] = approved
    try {
      const data = await approveRequest(requestId, decisions)
      applyResult(teamId, data)
    } catch (e) {
      setError(e.message)
    } finally {
      setQueueLoading(false)
      refreshQueueAndHistory()
    }
  }

  const activeTeam = teams.find((t) => t.id === activeId)
  const pendingCount = queue.length

  return (
    <div className="app">
      <Sidebar teams={teams} activeId={activeId} onSelect={setActiveId} pendingCount={pendingCount} />

      <div className="main">
        {error && <div className="error-banner top">Error: {error}</div>}

        {activeId === 'queue' && (
          <ApprovalQueue
            teams={teams}
            queue={queue}
            history={history}
            loading={queueLoading}
            onDecide={handleDecide}
          />
        )}

        {activeTeam && activeId !== 'queue' && (
          <TeamPanel
            team={activeTeam}
            state={teamState[activeId] || emptyTeamState()}
            onRefresh={() => loadTeam(activeId)}
            onSend={(text) => handleSend(activeId, text)}
            onDecide={(requestId, actions, approved) => handleDecide(requestId, actions, approved, activeId)}
          />
        )}

        {!activeTeam && activeId !== 'queue' && teams.length === 0 && !error && (
          <p className="empty-hint">Loading teams…</p>
        )}
      </div>
    </div>
  )
}
