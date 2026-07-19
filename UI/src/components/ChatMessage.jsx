import { mediaUrl } from "../api";
import { MemoryUsedPanel } from "./MemoryUsedPanel";

export function ChatMessage({ message }) {
  const image = mediaUrl(message.image_path);
  return (
    <article className={`chat-message ${message.role}`}>
      {message.role === "assistant" && <img className="message-avatar" src="/icons/icon-192.png" alt="" />}
      <div className="message-stack">
        <div className="message-bubble"><p>{message.text}</p></div>
        {image && <img className="evidence-image" src={image} alt="A memory image that supports this answer" />}
        {message.role === "assistant" && <MemoryUsedPanel recall={message.data?.recall_debug} />}
      </div>
    </article>
  );
}
