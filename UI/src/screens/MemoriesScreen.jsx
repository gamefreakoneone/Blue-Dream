import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";

const categoryIcon = { person: "person", preference: "heart", routine: "routine", medical: "medical", safety: "safety" };

export function MemoriesScreen() {
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    try { const payload = await api.listFacts(); setFacts(payload.facts || []); setError(""); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

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
    </section>
  );
}
