import { Icon } from "../icons";
import { enablePush } from "../push";

const copy = {
  prompt: ["Stay gently in the loop", "Turn on notifications for reminders and important safety notes."],
  available: ["Finish notification setup", "Notifications are allowed. Connect this browser to Memoria."],
  denied: ["Notifications are blocked", "Allow notifications in your browser settings, then refresh Memoria."],
  unsupported: ["Notifications unavailable here", "You can still receive every note while Memoria is open."],
  not_configured: ["Notifications need setup", "The caregiver can add the VAPID keys on this computer."],
};

export function NotificationCard({ state, onStateChange }) {
  if (!state || state === "enabled") return null;
  const [title, body] = copy[state] || copy.prompt;
  const canEnable = ["prompt", "available", "disabled"].includes(state);

  const enable = async () => {
    onStateChange("working");
    try {
      const result = await enablePush();
      onStateChange(result.state);
    } catch {
      onStateChange("not_configured");
    }
  };

  return (
    <section className="notification-card">
      <span className="notification-card-icon"><Icon name="bell" size={25} /></span>
      <div><h2>{state === "working" ? "Turning notifications on…" : title}</h2><p>{body}</p></div>
      {canEnable && <button type="button" className="primary-button compact" onClick={enable}>Enable</button>}
    </section>
  );
}
