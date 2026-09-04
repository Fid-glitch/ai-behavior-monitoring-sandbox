import { useState, useEffect, useCallback } from "react";

import PromptForm from "../component/Promptform";
import Riskcard from "../component/Riskcard";
import Statspanel from "../component/Statspanel";
import Timeline from "../component/Timeline";
import Explainability from "../component/Explainability";

import {
  analyzePrompt,
  fetchHistory,
  fetchStats,
  ApiError,
} from "../services/api";

const POLL_INTERVAL_MS = 4000;

export default function Dashboard() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [latestEvent, setLatestEvent] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);

  const refreshBackground = useCallback(async () => {
    try {
      const [historyRes, statsRes] = await Promise.all([
        fetchHistory(50),
        fetchStats(),
      ]);

      setEvents(historyRes.events);
      setStats(statsRes);
    } catch {
      // Ignore background polling errors
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
      setSelectedId(result.id);

      await refreshBackground();
    } catch (err) {
      setErrorBanner(
        err instanceof ApiError
          ? err.message
          : "Something went wrong sending that prompt."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const selectedEvent =
    events.find((e) => e.id === selectedId) || latestEvent;

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Agent Sandbox Console</h1>
        <p className="app-subtitle">
          Every request is scanned, scored, and gated before the agent sees it.
        </p>
      </header>

      {errorBanner && (
        <div className="error-banner">{errorBanner}</div>
      )}

      <main className="app-main">
        <section className="form-section">
          <PromptForm
            onSubmit={handleSubmit}
            isSubmitting={isSubmitting}
          />
        </section>

        <section className="dashboard-section">
          <div className="dashboard-grid">
            <Riskcard latestEvent={latestEvent} />

            <Statspanel stats={stats} />

            <Timeline
              events={events}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />

            <Explainability event={selectedEvent} />
          </div>
        </section>
      </main>
    </div>
  );
}