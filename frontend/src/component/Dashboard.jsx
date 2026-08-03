import { useState, useEffect, useCallback } from "react";
import PromptForm from "../components/PromptForm";
import Dashboard from "../components/Dashboard";
import { analyzePrompt, fetchHistory, fetchStats, ApiError } from "../services/api";

const POLL_INTERVAL_MS = 4000;

export default function DashboardPage() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [latestEvent, setLatestEvent] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);

  const refreshBackground = useCallback(async () => {
    try {
      const [historyRes, statsRes] = await Promise.all([fetchHistory(50), fetchStats()]);
      setEvents(historyRes.events);
      setStats(statsRes);
    } catch {
      // silent on background poll failures
    }
  }, []);

  useEffect(() => {
    refreshBackground();
    const id = setInterval(refreshBackground, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshBackground]);

  async function handleSubmit(payload) {
    setIsSubmitting(true);
    setErrorBanner(null);
    try {
      const result = await analyzePrompt(payload);
      setLatestEvent(result);
      await refreshBackground();
    } catch (err) {
      setErrorBanner(
        err instanceof ApiError ? err.message : "Something went wrong sending that prompt. Try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Agent Sandbox Console</h1>
        <p className="app-subtitle">Every request is scanned, scored, and gated before the agent sees it.</p>
      </header>

      {errorBanner && <div className="error-banner" role="alert">{errorBanner}</div>}

      <main className="app-main">
        <section className="form-section">
          <PromptForm onSubmit={handleSubmit} isSubmitting={isSubmitting} />
        </section>
        <section className="dashboard-section">
          <Dashboard events={events} stats={stats} latestEvent={latestEvent} />
        </section>
      </main>
    </div>
  );
}