import RiskBadge from "./RiskBadge";

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function Timeline({ events, selectedId, onSelect }) {
  return (
    <div className="panel timeline-panel">
      <span className="panel-label">Timeline</span>
      {events.length === 0 ? (
        <p className="empty-hint">
          Flagged and blocked requests will appear here as they happen.
        </p>
      ) : (
        <ul className="timeline-list">
          {events.map((ev) => (
            <li key={ev.id}>
              <button
                className={`timeline-row${
                  ev.id === selectedId ? " timeline-row--active" : ""
                }`}
                onClick={() => onSelect(ev.id)}
              >
                <span
                  className={`timeline-marker timeline-marker--${ev.riskTier.toLowerCase()}`}
                />
                <span className="timeline-time">{formatTime(ev.timestamp)}</span>
                <span className="timeline-gate">
                  {ev.gate === "input" ? "Gate 1" : "Gate 2"}
                </span>
                <RiskBadge tier={ev.riskTier} size="sm" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}