export default function StatsPanel({ stats }) {
  const { totalRequests = 0, allowed = 0, flagged = 0, blocked = 0 } = stats || {};

  return (
    <div className="panel stats-panel">
      <span className="panel-label">Session stats</span>
      <div className="stats-grid">
        <div className="stat-cell">
          <span className="stat-number">{totalRequests}</span>
          <span className="stat-label">Processed</span>
        </div>
        <div className="stat-cell stat-cell--low">
          <span className="stat-number">{allowed}</span>
          <span className="stat-label">Allowed</span>
        </div>
        <div className="stat-cell stat-cell--medium">
          <span className="stat-number">{flagged}</span>
          <span className="stat-label">Flagged</span>
        </div>
        <div className="stat-cell stat-cell--high">
          <span className="stat-number">{blocked}</span>
          <span className="stat-label">Blocked</span>
        </div>
      </div>
    </div>
  );
}