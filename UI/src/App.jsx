import { useEffect, useState } from "react";
import { Icon } from "./icons";

const tabs = [
  ["chat", "Chat"],
  ["reminders", "Reminders"],
  ["safety", "Safety"],
  ["memories", "Memories"],
];

function routeFromHash() {
  const value = window.location.hash.replace(/^#/, "");
  return tabs.some(([route]) => route === value) ? value : "chat";
}

export default function App() {
  const [route, setRoute] = useState(routeFromHash);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.history.replaceState(null, "", "/#chat");
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#chat" aria-label="Memoria chat">
          <img src="/slime_logo.png" alt="" />
          <span>Memoria</span>
        </a>
        <button className="icon-button" type="button" aria-label="Caregiver and demo tools">
          <Icon name="settings" size={26} />
        </button>
      </header>
      <main className="screen scaffold-screen">
        <p className="eyebrow">A gentle companion</p>
        <h1>{tabs.find(([value]) => value === route)?.[1]}</h1>
        <p>The Memoria patient experience is getting ready.</p>
      </main>
      <nav className="bottom-nav" aria-label="Main navigation">
        {tabs.map(([value, label]) => (
          <a key={value} className={route === value ? "active" : ""} href={`#${value}`} aria-current={route === value ? "page" : undefined}>
            <Icon name={value} size={25} />
            <span>{label}</span>
          </a>
        ))}
      </nav>
    </div>
  );
}
