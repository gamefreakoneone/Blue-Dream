import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { disablePush, enablePush, getPushStatus } from "../push";

export function DemoToolsSheet({ open, onClose, onResetConversation, pushState, onPushState }) {
  const [busy, setBusy] = useState("");
  const [report, setReport] = useState(null);
  const [result, setResult] = useState("");

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("sheet-open");
    return () => { document.removeEventListener("keydown", onKey); document.body.classList.remove("sheet-open"); };
  }, [onClose, open]);
  if (!open) return null;

  const run = async (name, action) => {
    setBusy(name); setResult("");
    try { await action(); } catch (error) { setResult(error.message); }
    finally { setBusy(""); }
  };

  const togglePush = () => run("push", async () => {
    const value = pushState === "enabled" ? await disablePush() : await enablePush();
    onPushState(value.state);
  });
  const testPush = () => run("test", async () => {
    const response = await api.testPush();
    setResult(response.status === "sent" ? `Test notification sent to ${response.sent} browser${response.sent === 1 ? "" : "s"}.` : response.status === "no_subscriptions" ? "No enabled browser subscription is registered yet." : "Web Push is not configured on the backend.");
  });
  const consolidate = () => run("consolidate", async () => setReport(await api.consolidate()));
  const geofence = () => run("geofence", async () => {
    const settings = await api.geofenceSettings();
    const response = await api.simulateExit({ event_type: "exit", latitude: Number(settings.home_lat || 37.7749) + 0.02, longitude: Number(settings.home_lng || -122.4194) + 0.02, device_id: "demo-web" });
    setResult(`Demo exit recorded: ${response.title || response.alert_id || "alert created"}.`);
  });
  const reset = () => run("reset", async () => { await onResetConversation(); setResult("A fresh conversation is ready."); });
  const refresh = () => run("refresh", async () => {
    const registrations = await navigator.serviceWorker?.getRegistrations();
    await Promise.all((registrations || []).map((registration) => registration.unregister()));
    window.location.reload();
  });

  return (
    <div className="sheet-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="demo-sheet" role="dialog" aria-modal="true" aria-labelledby="demo-tools-title">
        <div className="sheet-handle" />
        <header><div><p className="eyebrow">Caregiver controls</p><h2 id="demo-tools-title">Caregiver / demo tools</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close demo tools"><Icon name="close" size={25} /></button></header>

        <div className="tool-card"><div className="tool-heading"><span className="card-icon mint"><Icon name="bell" size={23} /></span><div><h3>Notifications</h3><p className={`status-pill ${pushState}`}>{pushState || "checking"}</p></div></div><div className="tool-actions"><button type="button" className="secondary-button" onClick={togglePush} disabled={busy === "push"}>{pushState === "enabled" ? "Turn off" : "Enable"}</button><button type="button" className="primary-button" onClick={testPush} disabled={busy === "test"}>Send test</button></div></div>
        <div className="tool-card"><div className="tool-heading"><span className="card-icon mint"><Icon name="sparkles" size={23} /></span><div><h3>Memory cleanup</h3><p>Consolidate older room events into gentle daily summaries.</p></div></div><button type="button" className="secondary-button full" onClick={consolidate} disabled={busy === "consolidate"}>Run memory cleanup</button>{report && <div className="report-grid"><span><strong>{report.groups_formed ?? 0}</strong> groups</span><span><strong>{report.events_consolidated ?? 0}</strong> events</span><span><strong>{report.summaries_created ?? 0}</strong> summaries</span></div>}</div>
        <div className="tool-card"><div className="tool-heading"><span className="card-icon amber"><Icon name="map" size={23} /></span><div><h3>Geofence rehearsal</h3><p>Creates the canned caregiver-only exit result here.</p></div></div><button type="button" className="secondary-button full" onClick={geofence} disabled={busy === "geofence"}>Simulate leaving home</button></div>
        <div className="tool-card slim"><button type="button" className="tool-row-button" onClick={reset} disabled={busy === "reset"}><Icon name="chat" size={22} /><span><strong>Start fresh conversation</strong><small>Reset and rotate this browser’s session</small></span></button><button type="button" className="tool-row-button" onClick={refresh}><Icon name="refresh" size={22} /><span><strong>Refresh app</strong><small>Unregister the service worker and reload</small></span></button></div>
        {result && <p className="tool-result" role="status">{result}</p>}
      </section>
    </div>
  );
}
