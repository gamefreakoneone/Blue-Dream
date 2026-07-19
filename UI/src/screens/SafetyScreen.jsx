import { useEffect, useMemo, useState } from "react";
import { api, mediaUrl } from "../api";
import { Icon } from "../icons";

const isGeofence = (alert) => [alert.alert_type, alert.hazard_type].some((value) => String(value || "").startsWith("geofence_"));

export function SafetyScreen() {
  const [alerts, setAlerts] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const payload = await api.listAlerts();
      const patientAlerts = (payload.alerts || []).filter((alert) => !isGeofence(alert));
      setAlerts(patientAlerts);
      setSelectedId((value) => value && patientAlerts.some((alert) => alert.alert_id === value) ? value : patientAlerts[0]?.alert_id || null);
      setError("");
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  const selected = useMemo(() => alerts.find((alert) => alert.alert_id === selectedId) || null, [alerts, selectedId]);

  const acknowledge = async () => {
    if (!selected) return;
    const id = selected.alert_id;
    setAlerts((items) => items.filter((alert) => alert.alert_id !== id));
    try { await api.acknowledgeAlert(id, "ok"); } catch (requestError) { setError(requestError.message); await load(); }
  };

  return (
    <section className="screen standard-screen safety-screen">
      <div className="screen-heading"><p className="eyebrow">Here when you need it</p><h1>Safety</h1><p>Clear, calm guidance about things Memoria noticed at home.</p></div>
      {error && <p className="inline-error" role="status">{error}</p>}
      {loading ? <div className="soft-loading">Checking that everything is okay…</div> : !alerts.length ? (
        <div className="empty-card safe"><span className="card-icon"><Icon name="safety" size={30} /></span><h2>Everything looks settled</h2><p>There are no open safety notes for you.</p></div>
      ) : (
        <div className="safety-layout">
          <div className="safety-list" aria-label="Open safety notes">{alerts.map((alert) => (
            <button type="button" key={alert.alert_id} className={`safety-list-item severity-${alert.severity} ${selectedId === alert.alert_id ? "selected" : ""}`} onClick={() => setSelectedId(alert.alert_id)}>
              <Icon name="safety" size={24} /><span><strong>{alert.title || "Safety note"}</strong><small>{alert.room_name || "At home"}</small></span>
            </button>
          ))}</div>
          {selected && <article className={`safety-detail severity-${selected.severity}`}>
            <div className="safety-detail-heading"><span className="card-icon amber"><Icon name="safety" size={27} /></span><div><p>{selected.severity || "important"} safety note</p><h2>{selected.title || "Please take a moment"}</h2></div></div>
            {mediaUrl(selected.image_path) && <img className="safety-image" src={mediaUrl(selected.image_path)} alt="The highlighted area Memoria noticed" />}
            <p className="safety-message">{selected.body || selected.message || "Please take a moment to check that everything is okay."}</p>
            {selected.recommended_action && <p className="recommended-action">A gentle next step: {String(selected.recommended_action).replaceAll("_", " ")}.</p>}
            <button type="button" className="primary-button safety-ack" onClick={acknowledge}><Icon name="check" size={21} /> I’m okay</button>
          </article>}
        </div>
      )}
    </section>
  );
}
