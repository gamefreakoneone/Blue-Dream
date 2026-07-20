export function markSafetyAcknowledged(messages, messageId) {
  let changed = false;
  const updated = messages.map((message) => {
    if (message.message_id !== messageId || message.safety_acknowledged) return message;
    changed = true;
    return { ...message, safety_acknowledged: true };
  });
  return changed ? updated : messages;
}
