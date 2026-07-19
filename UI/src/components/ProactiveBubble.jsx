import { mediaUrl } from "../api";
import { Icon } from "../icons";

const treatments = {
  safety: { icon: "safety", label: "Safety check" },
  reminder: { icon: "bell", label: "Gentle reminder" },
  morning_report: { icon: "sun", label: "Good morning" },
};

export function ProactiveBubble({ message, highlighted }) {
  const treatment = treatments[message.trigger_type] || treatments.reminder;
  const image = mediaUrl(message.image_path);
  return (
    <article id={`proactive-${message.message_id}`} className={`proactive-bubble ${message.trigger_type} ${highlighted ? "arrival-highlight" : ""}`}>
      <div className="proactive-icon"><Icon name={treatment.icon} size={24} /></div>
      <div className="proactive-content">
        <p className="proactive-label">{treatment.label}</p>
        <p className="proactive-text">{message.text}</p>
        {image && <img className="evidence-image proactive-image" src={image} alt="The scene Memoria noticed" />}
      </div>
    </article>
  );
}
