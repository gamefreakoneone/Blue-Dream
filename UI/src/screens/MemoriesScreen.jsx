import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";

const categoryIcon = { person: "person", preference: "heart", routine: "routine", medical: "medical", safety: "safety" };

function digestDayLabel(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

export function MemoriesScreen() {
  const [facts, setFacts] = useState([]);
  const [digests, setDigests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [digestsLoading, setDigestsLoading] = useState(true);
  const [error, setError] = useState("");
  const [digestsError, setDigestsError] = useState("");

  const load = async () => {
    try { const payload = await api.listFacts(); setFacts(payload.facts || []); setError(""); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    api.digest(7)
      .then((payload) => { setDigests(payload.digests || []); setDigestsError(""); })
      .catch((requestError) => setDigestsError(requestError.message))
      .finally(() => setDigestsLoading(false));
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
      <div className="section-title summaries-title"><div><h2>Your story</h2><p>One gentle note about each recent day.</p></div></div>
      {digestsError && <p className="inline-error" role="status">{digestsError}</p>}
      {digestsLoading ? <div className="soft-loading compact-loading">Gathering your recent days…</div> : digests.length ? (
        <div className="summary-list">{digests.map((digest) => {
          const momentCount = Number(digest.source_event_count || 0) + Number(digest.source_summary_count || 0);
          return (
            <article className="summary-card" key={digest.digest_id}>
              <div className="summary-date"><span className="card-icon mint"><Icon name="sun" size={24} /></span><div><time dateTime={digest.date}>{digestDayLabel(digest.date)}</time></div></div>
              <p>{digest.text}</p>
              {digest.highlights?.length ? <ul className="digest-highlights">{digest.highlights.map((highlight) => <li key={highlight}>{highlight}</li>)}</ul> : null}
              <small>{momentCount} {momentCount === 1 ? "moment" : "moments"} remembered</small>
            </article>
          );
        })}</div>
      ) : <div className="empty-card summary-empty"><Icon name="sun" size={30} /><h2>Your daily story will appear here</h2><p>Memoria creates it as everyday moments collect.</p></div>}
    </section>
  );
}
