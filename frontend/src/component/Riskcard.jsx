import RiskBadge from "./RiskBadge";

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

  return (
    <div className={`panel score-widget score-widget--${riskTier.toLowerCase()}`}>
      <span className="panel-label">Current risk score</span>
      <div className="score-main">
        <span className="score-number">{riskScore}</span>
        <span className="score-max">/100</span>
      </div>
      <div className="score-footer">
        <RiskBadge tier={riskTier} size="lg" />
        <span className="decision-text">{decision}</span>
      </div>
    </div>
  );
}