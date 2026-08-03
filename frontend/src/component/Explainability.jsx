import RiskBadge from "./RiskBadge";

export default function ExplainabilityPanel({ event }) {
  return (
    <div className="panel explain-panel">
      <span className="panel-label">Why this decision</span>
      {!event ? (
        <p className="empty-hint">
          Select a request from the timeline to see which rule fired.
        </p>
      ) : (
        <dl className="explain-list">
          <div className="explain-row">
            <dt>Rule triggered</dt>
            <dd className="mono">{event.ruleTriggered}</dd>
          </div>
          <div className="explain-row">
            <dt>Reason</dt>
            <dd>{event.reason}</dd>
          </div>
          <div className="explain-row">
            <dt>Gate</dt>
            <dd>
              {event.gate === "input" ? "Gate 1 - InputGate" : "Gate 2 - ActionGate"}
            </dd>
          </div>
          <div className="explain-row">
            <dt>Decision</dt>
            <dd>
              <RiskBadge tier={event.riskTier} size="sm" /> {event.decision}
            </dd>
          </div>
          {event.toolCalled && (
            <div className="explain-row">
              <dt>Tool called</dt>
              <dd className="mono">{event.toolCalled}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}