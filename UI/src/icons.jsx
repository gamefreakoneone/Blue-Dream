const paths = {
  chat: <path d="M5 6.8A3.8 3.8 0 0 1 8.8 3h6.4A3.8 3.8 0 0 1 19 6.8v3.4a3.8 3.8 0 0 1-3.8 3.8h-4.7L6 18v-4.7a3.8 3.8 0 0 1-1-2.6Z" />,
  reminders: <><path d="M7 10a5 5 0 0 1 10 0v3l1.7 2.4H5.3L7 13Z" /><path d="M10 18h4" /></>,
  safety: <><path d="M12 3 5.5 5.8v5.1c0 4.2 2.8 7.7 6.5 9.1 3.7-1.4 6.5-4.9 6.5-9.1V5.8L12 3Z" /><path d="m9.2 12 1.8 1.8 4-4" /></>,
  memories: <path d="M7 4.5h8A2.5 2.5 0 0 1 17.5 7v13l-5.5-3-5.5 3V7A2.5 2.5 0 0 1 9 4.5Z" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  send: <><path d="m3 11 17-8-7.5 18-2.2-7.3L3 11Z" /><path d="m10.3 13.7 4.3-4.3" /></>,
  bell: <><path d="M7 10a5 5 0 0 1 10 0v3l2 3H5l2-3v-3Z" /><path d="M10 19h4" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  chevron: <path d="m8 10 4 4 4-4" />,
  star: <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  pin: <><path d="m9 4 6 0-1 5 3 3H7l3-3-1-5Z" /><path d="M12 12v9" /></>,
  hide: <><path d="M3 3l18 18" /><path d="M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.2A10.5 10.5 0 0 1 12 4c5.2 0 9 5 9 8a12.8 12.8 0 0 1-2.1 3.8M6.2 6.2C4.2 7.7 3 10 3 12c0 3 3.8 8 9 8 1.4 0 2.7-.4 3.8-1" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  sparkles: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Z" /><path d="m6 14 .8 2.2L9 17l-2.2.8L6 20l-.8-2.2L3 17l2.2-.8L6 14ZM19 13l.6 1.4L21 15l-1.4.6L19 17l-.6-1.4L17 15l1.4-.6L19 13Z" /></>,
  map: <><path d="m3 6 5-2 8 3 5-2v13l-5 2-8-3-5 2V6Z" /><path d="M8 4v13M16 7v13" /></>,
  refresh: <><path d="M20 7v5h-5" /><path d="M19 12a7.5 7.5 0 1 1-2.2-5.3L20 10" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  person: <><circle cx="12" cy="8" r="3" /><path d="M5 21a7 7 0 0 1 14 0" /></>,
  heart: <path d="M20.8 5.8a5 5 0 0 0-7.1 0L12 7.5l-1.7-1.7a5 5 0 1 0-7.1 7.1L12 21l8.8-8.1a5 5 0 0 0 0-7.1Z" />,
  routine: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  medical: <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z" />,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m4 17 5-5 4 4 2-2 5 4" /></>,
};

export function Icon({ name, size = 24, className = "", fill = "none" }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name] || paths.sparkles}
    </svg>
  );
}
