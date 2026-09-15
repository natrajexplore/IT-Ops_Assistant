import InfraDiagram from './InfraDiagram.jsx'

function ChangeRequestAction({ action, topology }) {
  const cr = action.change_request

  if (!cr) {
    return (
      <div className="approval-action">
        <code>{action.tool_name}({action.arguments})</code>
      </div>
    )
  }

  const typeLabel = cr.change_type === 'emergency_weekday' ? 'Emergency CR (weekday)' : 'Weekend planned'
  const typeClass = cr.change_type === 'emergency_weekday' ? 'tag-emergency' : 'tag-weekend'

  return (
    <div className="cr-card">
      <div className="cr-header">
        <span className="cr-id">CR-{String(cr.id).padStart(4, '0')}</span>
        <span className={`tag ${typeClass}`}>{typeLabel}</span>
        <span className={`tag tag-risk-${cr.risk}`}>{cr.risk} risk</span>
        {cr.incident_id && <span className="tag tag-incident">{cr.incident_id}</span>}
      </div>
      <div className="cr-title">{cr.title}</div>
      <div className="cr-description">{cr.description}</div>

      {topology && (
        <>
          <div className="cr-section-title">Infra impact</div>
          <InfraDiagram topology={topology} affected={cr.affected_components} />
        </>
      )}

      <div className="cr-section-title">Configuration plan</div>
      <div className="cr-config-plan">{cr.configuration_plan}</div>

      {cr.impacted_teams.length > 0 && (
        <div className="cr-impacted-teams">
          <span className="cr-section-title inline">Also impacts:</span>
          {cr.impacted_teams.map((t) => (
            <span className="tag tag-team" key={t}>{t}</span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ApprovalCard({ actions, topology, onDecide, disabled }) {
  return (
    <div className="approval-card">
      <div className="approval-title">Approval required</div>
      {actions.map((a) => (
        <ChangeRequestAction key={a.call_id} action={a} topology={topology} />
      ))}
      <div className="approval-buttons">
        <button className="approve-button" onClick={() => onDecide(true)} disabled={disabled}>
          Approve
        </button>
        <button className="reject-button" onClick={() => onDecide(false)} disabled={disabled}>
          Reject
        </button>
      </div>
    </div>
  )
}
