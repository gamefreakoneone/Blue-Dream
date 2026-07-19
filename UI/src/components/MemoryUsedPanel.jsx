import { useState } from "react";
import { Icon } from "../icons";

function memoryDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function MemoryUsedPanel({ recall }) {
  const [open, setOpen] = useState(false);
  const memories = recall?.memories || [];
  if (!recall) return null;

  return (
    <section className={`memory-used ${open ? "open" : ""}`}>
      <button type="button" className="memory-used-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span><Icon name="sparkles" size={20} /> Memory used · {recall.packed_count ?? memories.length} memories</span>
        <Icon name="chevron" size={21} />
      </button>
      {open && (
        <div className="memory-used-body">
          <div className="recall-counts" aria-label="Memory recall counts">
            <span><strong>{recall.considered_count ?? 0}</strong> considered</span>
            <span><strong>{recall.packed_count ?? memories.length}</strong> packed</span>
            <span><strong>{recall.excluded_count ?? 0}</strong> excluded</span>
          </div>
          <div className="recall-list">
            {memories.map((memory) => (
              <article className="recall-row" key={`${memory.type}-${memory.id}`}>
                <div className="recall-type"><span>{memory.type || "memory"}</span>{memory.pinned && <Icon name="star" size={16} fill="currentColor" />}</div>
                <time>{memoryDate(memory.timestamp)}</time>
                <div className="recall-scores">
                  <span>Similarity <strong>{Number(memory.similarity || 0).toFixed(3)}</strong></span>
                  <span>Final <strong>{Number(memory.final_score || 0).toFixed(3)}</strong></span>
                </div>
              </article>
            ))}
          </div>
          {recall.excluded_count > 0 && <p className="excluded-note">{recall.excluded_count} lower-ranked memories stayed outside the answer budget.</p>}
        </div>
      )}
    </section>
  );
}
