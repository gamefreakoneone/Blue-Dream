import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { useProactivePoll } from "../hooks/useProactivePoll";
import { ChatMessage } from "../components/ChatMessage";
import { ProactiveBubble } from "../components/ProactiveBubble";
import { NotificationCard } from "../components/NotificationCard";
import { playSoftChime, showInPageNotifications } from "../proactiveFeedback";

export function ChatScreen({ sessionId, messages, onMessages, pushState, onPushState }) {
  const [text, setText] = useState("");
  const [typing, setTyping] = useState(false);
  const endRef = useRef(null);
  const acked = useRef(new Set());
  const addProactive = useCallback((values) => onMessages(values.map((value) => ({ ...value, kind: "proactive" }))), [onMessages]);
  const handleArrival = useCallback((values, source) => {
    playSoftChime();
    if (source === "poll") showInPageNotifications(values, pushState);
  }, [pushState]);
  const { highlightedId } = useProactivePoll({ sessionId, onMessages: addProactive, onArrival: handleArrival });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, typing]);

  useEffect(() => {
    const pending = messages.filter((message) => message.kind === "proactive" && !acked.current.has(message.message_id));
    if (!pending.length) return;
    const frame = window.requestAnimationFrame(() => {
      pending.forEach((message) => {
        if (!document.getElementById(`proactive-${message.message_id}`)) return;
        acked.current.add(message.message_id);
        api.acknowledgeProactive(message.message_id).catch(() => {});
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages]);

  const submit = async (event) => {
    event.preventDefault();
    const query = text.trim();
    if (!query || typing) return;
    setText("");
    onMessages([{ id: crypto.randomUUID(), role: "user", text: query }]);
    setTyping(true);
    try {
      const response = await api.query(query, sessionId);
      onMessages([{ id: crypto.randomUUID(), role: "assistant", ...response }]);
    } catch (error) {
      onMessages([{ id: crypto.randomUUID(), role: "assistant", text: error.message, response_type: "error" }]);
    } finally {
      setTyping(false);
    }
  };

  return (
    <section className="chat-screen">
      <div className="chat-intro">
        <p className="friendly-date">{new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}</p>
        <h1>What can I help you remember?</h1>
      </div>
      <NotificationCard state={pushState} onStateChange={onPushState} />
      <div className="message-list" aria-live="polite">
        {messages.map((message) => message.kind === "proactive" ? (
          <ProactiveBubble key={message.message_id} message={message} highlighted={message.message_id === highlightedId} />
        ) : (
          <ChatMessage key={message.id} message={message} />
        ))}
        {typing && <div className="typing-row"><img className="message-avatar" src="/icons/icon-192.png" alt="" /><div className="typing-bubble" aria-label="Memoria is thinking"><span /><span /><span /></div></div>}
        <div ref={endRef} />
      </div>
      <form className="chat-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="chat-input">Ask Memoria anything</label>
        <input id="chat-input" value={text} onChange={(event) => setText(event.target.value)} placeholder="Ask me anything…" autoComplete="off" />
        <button type="submit" aria-label="Send message" disabled={!text.trim() || typing}><Icon name="send" size={25} /></button>
      </form>
    </section>
  );
}
