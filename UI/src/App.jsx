import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { getPushStatus } from "./push";
import { ChatScreen } from "./screens/ChatScreen";
import { RemindersScreen } from "./screens/RemindersScreen";
import { SafetyScreen } from "./screens/SafetyScreen";
import { MemoriesScreen } from "./screens/MemoriesScreen";
import { DemoToolsSheet } from "./components/DemoToolsSheet";

const SESSION_KEY = "memoria-conversation-session";
const tabs = [["chat", "Chat"], ["reminders", "Reminders"], ["safety", "Safety"], ["memories", "Memories"]];
const welcome = () => [{ id: "welcome", role: "assistant", text: "Hello, I’m Memoria. I’m here to help you remember the little things and feel at ease." }];
const newSession = () => crypto.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function getSession() {
  let value = localStorage.getItem(SESSION_KEY);
  if (!value) { value = newSession(); localStorage.setItem(SESSION_KEY, value); }
  return value;
}
function routeFromHash() {
  const value = window.location.hash.replace(/^#/, "");
  return tabs.some(([route]) => route === value) ? value : "chat";
}

export default function App() {
  const [route, setRoute] = useState(routeFromHash);
  const [sessionId, setSessionId] = useState(getSession);
  const [messages, setMessages] = useState(welcome);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pushState, setPushState] = useState(null);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.history.replaceState(null, "", "/#chat");
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  useEffect(() => { getPushStatus().then((value) => setPushState(value.state)).catch(() => setPushState("unsupported")); }, []);

  const appendMessages = useCallback((incoming) => {
    setMessages((existing) => {
      const proactiveIds = new Set(existing.filter((item) => item.kind === "proactive").map((item) => item.message_id));
      return [...existing, ...incoming.filter((item) => item.kind !== "proactive" || !proactiveIds.has(item.message_id))];
    });
  }, []);
  const resetConversation = async () => {
    await api.resetConversation(sessionId);
    const next = newSession();
    localStorage.setItem(SESSION_KEY, next);
    setSessionId(next);
    setMessages(welcome());
    window.location.hash = "chat";
  };

  const screens = {
    chat: <ChatScreen sessionId={sessionId} messages={messages} onMessages={appendMessages} pushState={pushState} onPushState={setPushState} />,
    reminders: <RemindersScreen />,
    safety: <SafetyScreen />,
    memories: <MemoriesScreen />,
  };

  return (
    <div className="app-shell">
      <header className="topbar"><a className="brand" href="#chat" aria-label="Memoria chat"><img src="/icons/icon-192.png" alt="" /><span>Memoria</span></a><p className="topbar-date">{new Date().toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })}</p><button className="icon-button" type="button" onClick={() => setSheetOpen(true)} aria-label="Caregiver and demo tools"><Icon name="settings" size={25} /></button></header>
      <main>{screens[route]}</main>
      <nav className="bottom-nav" aria-label="Main navigation">{tabs.map(([value, label]) => <a key={value} className={route === value ? "active" : ""} href={`#${value}`} aria-current={route === value ? "page" : undefined}><Icon name={value} size={25} /><span>{label}</span></a>)}</nav>
      <DemoToolsSheet open={sheetOpen} onClose={() => setSheetOpen(false)} onResetConversation={resetConversation} pushState={pushState} onPushState={setPushState} />
    </div>
  );
}
