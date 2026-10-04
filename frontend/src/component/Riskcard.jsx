import RiskBadge from "./Riskbadge";

export default function RiskScoreWidget({ latestEvent }) {
  if (!latestEvent) {
    return (
      <div className="panel score-widget">
        <span className="panel-label">Current risk score</span>
        <p className="empty-hint">
          No requests yet. Send a prompt to see it scored live.
        </p>
      </div>
    );
  }

  const { riskScore, riskTier, decision } = latestEvent;

  // The API sends riskScore on a 0-1 scale; this panel shows it as 0-100.
  const displayScore =
    typeof riskScore === "number" && Number.isFinite(riskScore)
      ? Math.round(riskScore * 100)
      : 0;

  return (
    <div className={`panel score-widget score-widget--${riskTier.toLowerCase()}`}>
      <span className="panel-label">Current risk score</span>
      <div className="score-main">
        <span className="score-number">{displayScore}</span>
        <span className="score-max">/100</span>
      </div>
      <div className="score-footer">
        <RiskBadge tier={riskTier} size="lg" />
        <span className="decision-text">{decision}</span>
      </div>
    </div>
  );
}