import { useState } from "react";
import { api, mediaUrl } from "../api";
import { Icon } from "../icons";

const treatments = {
  safety: { icon: "safety", label: "Safety check" },
  reminder: { icon: "bell", label: "Gentle reminder" },
  morning_report: { icon: "sun", label: "Good morning" },
};

export function ProactiveBubble({ message, highlighted, onSafetyAcknowledged }) {
  const [ackBusy, setAckBusy] = useState(false);
  const treatment = treatments[message.trigger_type] || treatments.reminder;
  const image = mediaUrl(message.image_path);
  const canAcknowledge = message.trigger_type === "safety" && message.related_id;
  const acknowledgeSafety = async () => {
    if (!canAcknowledge || ackBusy) return;
    setAckBusy(true);
    try {
      await api.acknowledgeAlert(message.related_id, "ok");
      onSafetyAcknowledged(message.message_id);
    } catch {
      // Keep the action available for a quiet retry.
    } finally {
      setAckBusy(false);
    }
  };
  return (
    <article id={`proactive-${message.message_id}`} className={`proactive-bubble ${message.trigger_type} ${highlighted ? "arrival-highlight" : ""}`}>
      <div className="proactive-icon"><Icon name={treatment.icon} size={24} /></div>
      <div className="proactive-content">
        <p className="proactive-label">{treatment.label}</p>
        <p className="proactive-text">{message.text}</p>
        {image && <img className="evidence-image proactive-image" src={image} alt="The scene Memoria noticed" />}
        {canAcknowledge && !message.safety_acknowledged && <button className="primary-button proactive-ack" type="button" disabled={ackBusy} onClick={acknowledgeSafety}><Icon name="check" size={20} /> {ackBusy ? "Noting…" : "I’m okay"}</button>}
        {canAcknowledge && message.safety_acknowledged && <p className="proactive-confirmation" role="status">Thank you — noted that you’re okay.</p>}
      </div>
    </article>
  );
}
