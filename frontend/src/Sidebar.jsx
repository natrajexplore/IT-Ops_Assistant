export default function Sidebar({ teams, activeId, onSelect, pendingCount }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-title">IT Ops</div>
      <div className="sidebar-scroll">
        {teams.map((t) => (
          <button
            key={t.id}
            className={`sidebar-icon ${activeId === t.id ? 'active' : ''}`}
            title={t.name}
            onClick={() => onSelect(t.id)}
          >
            <span className="icon-emoji">{t.icon}</span>
            <span className="icon-label">{t.name}</span>
          </button>
        ))}
      </div>
      <div className="sidebar-divider" />
      <button
        className={`sidebar-icon queue ${activeId === 'queue' ? 'active' : ''}`}
        title="Approval Queue"
        onClick={() => onSelect('queue')}
      >
        <span className="icon-emoji">✅</span>
        <span className="icon-label">Approvals</span>
        {pendingCount > 0 && <span className="badge">{pendingCount}</span>}
      </button>
    </nav>
  )
}
