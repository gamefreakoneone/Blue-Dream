import { mediaUrl } from "./api";

const TITLES = {
  safety: "Memoria noticed something",
  reminder: "A gentle reminder",
  morning_report: "Good morning",
};

export function playSoftChime() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;

  try {
    const context = new AudioContext();
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.7);
    gain.connect(context.destination);

    [659.25, 783.99].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      oscillator.type = "sine";
      oscillator.frequency.value = frequency;
      oscillator.connect(gain);
      oscillator.start(context.currentTime + index * 0.12);
      oscillator.stop(context.currentTime + 0.55 + index * 0.12);
    });
    window.setTimeout(() => context.close().catch(() => {}), 900);
  } catch {
    // Sound is a progressive enhancement and can be blocked by autoplay policy.
  }
}

export function showInPageNotifications(messages, pushState) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  if (!["available", "not_configured", "disabled"].includes(pushState)) return;

  messages.forEach((message) => {
    try {
      const notification = new Notification(
        TITLES[message.trigger_type] || "A note from Memoria",
        {
          body: message.text,
          tag: message.message_id,
          icon: "/icons/icon-192.png",
          image: mediaUrl(message.image_path) || undefined,
        },
      );
      notification.onclick = () => {
        window.focus();
        window.location.hash = "chat";
        notification.close();
      };
    } catch {
      // The in-app bubble remains the guaranteed final fallback.
    }
  });
}
