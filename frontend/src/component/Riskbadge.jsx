const TIER_LABELS = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
};
export default function RiskBadge({ tier, size = "md" }) {
  const safeTier =
    tier?.toUpperCase?.() in TIER_LABELS
      ? tier.toUpperCase()
      : "LOW";
  return (
    <span
      className={`risk-badge risk-badge--${safeTier.toLowerCase()} risk-badge--${size}`}
    >
      <span className="risk-dot" aria-hidden="true"></span>
      {TIER_LABELS[safeTier]}
    </span>
  );
}