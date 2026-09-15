function isImpacted(nodeLabel, affected) {
  if (!affected || affected.length === 0) return false
  const n = nodeLabel.toLowerCase()
  return affected.some((a) => {
    const al = a.toLowerCase()
    return n.includes(al) || al.includes(n)
  })
}

export default function InfraDiagram({ topology, affected }) {
  if (!topology || topology.length === 0) return null
  return (
    <div className="infra-diagram">
      {topology.map((node, i) => (
        <div className="infra-diagram-item" key={node}>
          <div className={`infra-node ${isImpacted(node, affected) ? 'impacted' : ''}`}>
            {node}
          </div>
          {i < topology.length - 1 && <span className="infra-arrow">→</span>}
        </div>
      ))}
    </div>
  )
}
