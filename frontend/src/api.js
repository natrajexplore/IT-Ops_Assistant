export const BACKEND_URL = 'http://127.0.0.1:8010'

async function asJson(res) {
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

export const getTeams = () => fetch(`${BACKEND_URL}/teams`).then(asJson)

export const refreshTeam = (teamId) =>
  fetch(`${BACKEND_URL}/teams/${teamId}/refresh`, { method: 'POST' }).then(asJson)

export const messageTeam = (teamId, message) =>
  fetch(`${BACKEND_URL}/teams/${teamId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }).then(asJson)

export const approveRequest = (requestId, decisions) =>
  fetch(`${BACKEND_URL}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, decisions }),
  }).then(asJson)

export const getApprovalQueue = () => fetch(`${BACKEND_URL}/approvals`).then(asJson)

export const getChangeRequestHistory = () =>
  fetch(`${BACKEND_URL}/change-requests`).then(asJson)
