const paths = {
  chat: <path d="M5 6.8A3.8 3.8 0 0 1 8.8 3h6.4A3.8 3.8 0 0 1 19 6.8v3.4a3.8 3.8 0 0 1-3.8 3.8h-4.7L6 18v-4.7a3.8 3.8 0 0 1-1-2.6Z" />,
  reminders: <path d="M7 10a5 5 0 0 1 10 0v3l1.7 2.4H5.3L7 13Zm3 8h4" />,
  safety: <path d="M12 3 5.5 5.8v5.1c0 4.2 2.8 7.7 6.5 9.1 3.7-1.4 6.5-4.9 6.5-9.1V5.8Zm-2.8 9 1.8 1.8 4-4" />,
  memories: <path d="M7 4.5h8A2.5 2.5 0 0 1 17.5 7v13l-5.5-3-5.5 3V7A2.5 2.5 0 0 1 9 4.5Zm3-1.5h5" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19 13.5v-3l-2-.7a7 7 0 0 0-.8-1.8l.9-1.9L15 4l-1.9.9a7 7 0 0 0-1.9-.8L10.5 2h-3l-.7 2.1A7 7 0 0 0 5 5L3 4.1 1 6.2 2 8a7 7 0 0 0-.8 1.9L-1 10.5v3l2.1.7A7 7 0 0 0 2 16l-1 2 2.1 2 1.9-.9a7 7 0 0 0 1.8.8l.7 2.1h3l.7-2.1a7 7 0 0 0 1.9-.8l1.9.9 2.1-2-.9-2a7 7 0 0 0 .8-1.8Z" transform="translate(3) scale(.75)" /></>,
};

export function Icon({ name, size = 24, className = "" }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}
