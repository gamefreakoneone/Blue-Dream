import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";

function defaultDue() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

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
  const [text, setText] = useState("");
  const [dueAt, setDueAt] = useState(defaultDue);
  const [daily, setDaily] = useState(false);
  const [saving, setSaving] = useState(false);
  const [eventText, setEventText] = useState("");
  const [condition, setCondition] = useState("");
  const [roomNumber, setRoomNumber] = useState("");
  const [windowStart, setWindowStart] = useState("06:00");
  const [windowEnd, setWindowEnd] = useState("11:00");
  const [validDate, setValidDate] = useState("");
  const [eventSaving, setEventSaving] = useState(false);

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

  const create = async (event) => {
    event.preventDefault();
    if (!text.trim() || !dueAt) return;
    setSaving(true);
    try {
      await api.createReminder({ text: text.trim(), trigger_type: "time", due_at: new Date(dueAt).toISOString(), recurrence: daily ? "daily" : "none", event_trigger: null });
      setText("");
      setDueAt(defaultDue());
      setDaily(false);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const createEventReminder = async (event) => {
    event.preventDefault();
    if (!eventText.trim() || !condition.trim() || !windowStart || !windowEnd) return;
    setEventSaving(true);
    try {
      await api.createReminder({
        text: eventText.trim(),
        trigger_type: "event",
        due_at: null,
        recurrence: "none",
        event_trigger: {
          room_number: roomNumber ? Number(roomNumber) : null,
          window_start: windowStart,
          window_end: windowEnd,
          condition: condition.trim(),
          valid_date: validDate || null,
        },
      });
      setEventText("");
      setCondition("");
      setRoomNumber("");
      setValidDate("");
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setEventSaving(false);
    }
  };

  const complete = async (reminderId) => {
    setReminders((items) => items.filter((item) => item.reminder_id !== reminderId));
    try { await api.completeReminder(reminderId); } catch (requestError) { setError(requestError.message); await load(); }
  };

  const renderGroup = (title, items) => items.length > 0 && (
    <section className="reminder-group"><h2>{title}</h2><div className="card-list">{items.map((reminder) => (
      <article className="reminder-card" key={reminder.reminder_id}>
        <span className={`card-icon ${reminder.trigger_type === "event" ? "amber" : "blue"}`}><Icon name={reminder.trigger_type === "event" ? "sparkles" : "clock"} size={24} /></span>
        <div><h3>{reminder.text}</h3><p>{dueLabel(reminder)}</p></div>
        <button type="button" className="done-button" onClick={() => complete(reminder.reminder_id)}><Icon name="check" size={20} /> Done</button>
      </article>
    ))}</div></section>
  );

  return (
    <section className="screen standard-screen">
      <div className="screen-heading"><p className="eyebrow">A little help for later</p><h1>Reminders</h1><p>Simple notes that arrive at just the right time.</p></div>
      <form className="create-card" onSubmit={create}>
        <div className="create-card-title"><span className="card-icon blue"><Icon name="plus" size={23} /></span><div><h2>Add a reminder</h2><p>Choose a time on this device.</p></div></div>
        <label>What should I remember?<input value={text} onChange={(event) => setText(event.target.value)} placeholder="Take my afternoon medicine" /></label>
        <label>When?<input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
        <label className="check-label"><input type="checkbox" checked={daily} onChange={(event) => setDaily(event.target.checked)} /><span>Repeat every day</span></label>
        <button className="primary-button" type="submit" disabled={saving || !text.trim()}>{saving ? "Saving…" : "Save reminder"}</button>
      </form>
      <form className="create-card event-create-card" onSubmit={createEventReminder}>
        <div className="create-card-title"><span className="card-icon amber"><Icon name="sparkles" size={23} /></span><div><h2>Remind me at the right moment</h2><p>Memoria can notice an activity in a room.</p></div></div>
        <label>What should I remember?<input value={eventText} onChange={(event) => setEventText(event.target.value)} placeholder="Take my water bottle" /></label>
        <label>What should Memoria notice?<input value={condition} onChange={(event) => setCondition(event.target.value)} placeholder="When I am leaving for a walk" /></label>
        <div className="form-pair">
          <label>Room (optional)<input type="number" min="1" inputMode="numeric" value={roomNumber} onChange={(event) => setRoomNumber(event.target.value)} placeholder="1" /></label>
          <label>Date (optional)<input type="date" value={validDate} onChange={(event) => setValidDate(event.target.value)} /></label>
        </div>
        <div className="form-pair">
          <label>From<input type="time" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} /></label>
          <label>Until<input type="time" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} /></label>
        </div>
        <button className="primary-button event-button" type="submit" disabled={eventSaving || !eventText.trim() || !condition.trim()}>{eventSaving ? "Saving…" : "Save moment reminder"}</button>
      </form>
      {error && <p className="inline-error" role="status">{error}</p>}
      {loading ? <div className="soft-loading">Gathering your reminders…</div> : reminders.length ? <>{renderGroup("Today", groups.today)}{renderGroup("Later", groups.later)}</> : <div className="empty-card"><Icon name="check" size={30} /><h2>You’re all caught up</h2><p>New reminders will wait here for you.</p></div>}
    </section>
  );
}
