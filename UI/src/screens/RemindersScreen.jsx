import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";

function dueLabel(reminder) {
  if (reminder.trigger_type === "event") return reminder.event_trigger?.condition ? `When ${reminder.event_trigger.condition}` : "When Memoria notices the right moment";
  const due = new Date(reminder.due_at);
  if (Number.isNaN(due.valueOf())) return "Time not set";
  const now = new Date();
  const today = now.toDateString();
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toDateString();
  const time = due.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const prefix = due.toDateString() === today ? "Today" : due.toDateString() === tomorrow ? "Tomorrow" : due.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  return `${prefix} at ${time}${reminder.recurrence === "daily" ? " · every day" : ""}`;
}

function isToday(reminder) {
  if (reminder.trigger_type === "event") return true;
  const due = new Date(reminder.due_at);
  return !Number.isNaN(due.valueOf()) && due.toDateString() === new Date().toDateString();
}

export function RemindersScreen() {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    try {
      const payload = await api.listReminders();
      setReminders(payload.reminders || []);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const groups = useMemo(() => ({ today: reminders.filter(isToday), later: reminders.filter((item) => !isToday(item)) }), [reminders]);

  const complete = async (reminderId) => {
    if (busyId) return;
    setBusyId(reminderId);
    try {
      await api.completeReminder(reminderId);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (reminderId) => {
    if (busyId) return;
    setBusyId(reminderId);
    setReminders((items) => items.filter((item) => item.reminder_id !== reminderId));
    try {
      await api.archiveReminder(reminderId);
    } catch (requestError) {
      setError(requestError.message);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const renderGroup = (title, items) => items.length > 0 && (
    <section className="reminder-group"><h2>{title}</h2><div className="card-list">{items.map((reminder) => (
      <article className="reminder-card" key={reminder.reminder_id}>
        <span className={`card-icon ${reminder.trigger_type === "event" ? "amber" : "blue"}`}><Icon name={reminder.trigger_type === "event" ? "sparkles" : "clock"} size={24} /></span>
        <div><h3>{reminder.text}</h3><p>{dueLabel(reminder)}</p></div>
        <div className="reminder-actions">
          <button type="button" className="done-button" disabled={busyId !== null} onClick={() => complete(reminder.reminder_id)}><Icon name="check" size={20} /> Done</button>
          <button type="button" className="hide-button" disabled={busyId !== null} onClick={() => remove(reminder.reminder_id)}><Icon name="close" size={18} /> Remove</button>
        </div>
      </article>
    ))}</div></section>
  );

  return (
    <section className="screen standard-screen">
      <div className="screen-heading"><p className="eyebrow">A little help for later</p><h1>Reminders</h1><p>Ask Memoria in Chat to remember something for you.</p></div>
      {error && <p className="inline-error" role="status">{error}</p>}
      {loading ? <div className="soft-loading">Gathering your reminders…</div> : reminders.length ? <>{renderGroup("Today", groups.today)}{renderGroup("Later", groups.later)}</> : <div className="empty-card"><Icon name="check" size={30} /><h2>You’re all caught up</h2><p>New reminders will wait here after you ask in Chat.</p></div>}
    </section>
  );
}
