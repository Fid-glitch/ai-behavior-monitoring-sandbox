// =============================================================================
// This is the ONLY file that talks to the backend. Every component imports
// from here instead of calling fetch() directly.
//
// Contract is PROPOSED, pending confirmation from Fida's shared/schemas.py
// and Member 4's ActivityLog format. If field names differ once confirmed,
// only adaptGateDecision() below needs to change.
// =============================================================================

const API_BASE = '/api'

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// Translates whatever the backend sends into the shape your components
// expect. Update the RIGHT side of each ?? once you know the real field
// names from shared/schemas.py.
function adaptGateDecision(raw) {
  return {
    id: raw.id ?? raw.event_id,
    timestamp: raw.timestamp ?? raw.created_at,
    gate: raw.gate ?? raw.gate_name,
    riskTier: (raw.riskTier ?? raw.risk_level ?? 'LOW').toUpperCase(),
    riskScore: raw.riskScore ?? raw.risk_score ?? 0,
    decision: raw.decision ?? raw.outcome,
    ruleTriggered: raw.ruleTriggered ?? raw.rule_triggered ?? raw.rule_id ?? 'unknown_rule',
    reason: raw.reason ?? raw.explanation ?? '',
    agentResponse: raw.agentResponse ?? raw.agent_response,
    toolCalled: raw.toolCalled ?? raw.tool_called,
  }
}

async function apiRequest(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new ApiError('Could not reach the backend. Is FastAPI running on :8000?', 0)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // response wasn't JSON - fall back to statusText
    }
    throw new ApiError(detail, res.status)
  }
  return res.json()
}

// Send a prompt (and optional file) to the sandbox for scoring
export async function analyzePrompt({ prompt, fileName, fileText }) {
  const raw = await apiRequest('/analyze', {
    method: 'POST',
    body: JSON.stringify({ prompt, fileName, fileText }),
  })
  return adaptGateDecision(raw)
}

// Get the list of past requests, for the Timeline
export async function fetchHistory(limit = 50) {
  const raw = await apiRequest(`/history?limit=${limit}`)
  const events = raw.events ?? raw.decisions ?? raw
  return { events: events.map(adaptGateDecision) }
}

// Get aggregate counts, for the Stats Panel
export function fetchStats() {
  return apiRequest('/stats')
}

export { ApiError }