import { useState } from 'react'
import ApprovalCard from './ApprovalCard.jsx'
import InfraDiagram from './InfraDiagram.jsx'

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function HistoryRow({ record, topology }) {
  const [open, setOpen] = useState(false)
  const typeLabel = record.change_type === 'emergency_weekday' ? 'Emergency CR (weekday)' : 'Weekend planned'

  return (
    <div className="history-row">
      <button className="history-row-summary" onClick={() => setOpen((o) => !o)}>
        <span className={`tag ${record.status === 'approved' ? 'tag-approved' : 'tag-rejected'}`}>
          {record.status}
        </span>
        <span className="cr-id">CR-{String(record.id).padStart(4, '0')}</span>
        <div className="history-row-body">
          <div className="history-row-title">{record.title}</div>
          <div className="history-row-meta">
            {record.team_id} · {typeLabel} · {record.risk} risk · {formatTime(record.decided_at)}
          </div>
        </div>
        <span className="disclosure">{open ? '−' : '+'}</span>
      </button>

      {open && (
        <div className="history-row-detail">
          <div className="cr-description">{record.description}</div>
          {record.incident_id && (
            <div><span className="tag tag-incident">{record.incident_id}</span></div>
          )}
          {topology && (
            <>
              <div className="cr-section-title">Infra impact</div>
              <InfraDiagram topology={topology} affected={record.affected_components} />
            </>
          )}
          <div className="cr-section-title">Configuration plan</div>
          <div className="cr-config-plan">{record.configuration_plan}</div>
          {record.impacted_teams.length > 0 && (
            <div className="cr-impacted-teams">
              <span className="cr-section-title inline">Also impacts:</span>
              {record.impacted_teams.map((t) => (
                <span className="tag tag-team" key={t}>{t}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ApprovalQueue({ teams, queue, history, loading, onDecide }) {
  const topologyFor = (teamId) => teams.find((t) => t.id === teamId)?.topology

  return (
    <div className="team-panel">
      <header className="team-header">
        <div>
          <span className="team-icon">✅</span>
          <span className="team-name">Approval Queue</span>
        </div>
      </header>

      <div className="team-body">
        {queue.length === 0 && (
          <p className="empty-hint">No pending approvals across any team right now.</p>
        )}

        {queue.map((item) => (
          <div key={item.request_id} className="queue-item">
            <div className="queue-item-team">
              {item.team_icon} {item.team_name}
            </div>
            <ApprovalCard
              actions={item.actions}
              topology={topologyFor(item.team_id)}
              disabled={loading}
              onDecide={(approved) => onDecide(item.request_id, item.actions, approved, item.team_id)}
            />
          </div>
        ))}

        {history.length > 0 && (
          <>
            <div className="history-title">Recent decisions</div>
            <div className="history-list">
              {history.map((h) => (
                <HistoryRow key={h.id} record={h} topology={topologyFor(h.team_id)} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
