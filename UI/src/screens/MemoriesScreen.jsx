import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";

const categoryIcon = { person: "person", preference: "heart", routine: "routine", medical: "medical", safety: "safety" };

export function MemoriesScreen() {
  const [facts, setFacts] = useState([]);
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summariesLoading, setSummariesLoading] = useState(true);
  const [error, setError] = useState("");
  const [summariesError, setSummariesError] = useState("");

  const load = async () => {
    try { const payload = await api.listFacts(); setFacts(payload.facts || []); setError(""); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    api.summaries(7)
      .then((payload) => { setSummaries(payload.summaries || []); setSummariesError(""); })
      .catch((requestError) => setSummariesError(requestError.message))
      .finally(() => setSummariesLoading(false));
  }, []);

  const pin = async (factId) => {
    setFacts((items) => items.map((fact) => fact.fact_id === factId ? { ...fact, pinned: true } : fact));
    try { await api.pinFact(factId); } catch (requestError) { setError(requestError.message); await load(); }
  };
  const archive = async (factId) => {
    setFacts((items) => items.filter((fact) => fact.fact_id !== factId));
    try { await api.archiveFact(factId); } catch (requestError) { setError(requestError.message); await load(); }
  };

  return (
    <section className="screen standard-screen memories-screen">
      <div className="screen-heading"><p className="eyebrow">The details that matter</p><h1>Memories</h1><p>Helpful things you have shared with Memoria.</p></div>
      <div className="section-title"><div><h2>Things Memoria knows</h2><p>Pin the most important details so they stay close.</p></div></div>
      {error && <p className="inline-error" role="status">{error}</p>}
      {loading ? <div className="soft-loading">Gathering the details you shared…</div> : facts.length ? <div className="fact-grid">{facts.map((fact) => (
        <article className={`fact-card ${fact.pinned ? "pinned" : ""}`} key={fact.fact_id}>
          <div className="fact-top"><span className="card-icon mint"><Icon name={categoryIcon[fact.category] || "memories"} size={24} /></span><span className="category-badge">{fact.category || "memory"}</span></div>
          <p>{fact.text}</p>
          <div className="fact-actions">
            <button type="button" className={`pin-button ${fact.pinned ? "selected" : ""}`} disabled={fact.pinned} onClick={() => pin(fact.fact_id)}><Icon name={fact.pinned ? "star" : "pin"} size={19} fill={fact.pinned ? "currentColor" : "none"} /> {fact.pinned ? "Pinned" : "Pin"}</button>
            <button type="button" className="hide-button" onClick={() => archive(fact.fact_id)}><Icon name="hide" size={18} /> Hide</button>
          </div>
        </article>
      ))}</div> : <div className="empty-card"><Icon name="memories" size={30} /><h2>Your shared details will appear here</h2><p>Tell Memoria about people, routines, or preferences in Chat.</p></div>}
      <div className="section-title summaries-title"><div><h2>Your days</h2><p>Gentle room-by-room summaries from the past week.</p></div></div>
      {summariesError && <p className="inline-error" role="status">{summariesError}</p>}
      {summariesLoading ? <div className="soft-loading compact-loading">Gathering your recent days…</div> : summaries.length ? (
        <div className="summary-list">{summaries.map((summary) => (
          <article className="summary-card" key={summary.summary_id}>
            <div className="summary-date"><span className="card-icon mint"><Icon name="sun" size={24} /></span><div><time dateTime={summary.date}>{new Date(`${summary.date}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}</time><span>{summary.room_name || (summary.room_number != null ? `Room ${summary.room_number}` : "Home")}</span></div></div>
            <p>{summary.text}</p>
            <small>{summary.source_event_count} {summary.source_event_count === 1 ? "moment" : "moments"} remembered</small>
          </article>
        ))}</div>
      ) : <div className="empty-card summary-empty"><Icon name="sun" size={30} /><h2>Your day summaries will appear here</h2><p>Memoria creates them as everyday moments collect.</p></div>}
    </section>
  );
}
