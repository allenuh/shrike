import type { CSSProperties } from "react";

const paths = {
  overview: ["M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"],
  repository: ["M4 4h16v16H4zM8 4v16M12 8h4M12 12h4"],
  review: ["M7 3h10v18H7zM10 8h4M10 12h4M10 16h3M4 6v12M20 6v12"],
  settings: ["M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6"],
  status: ["M2 12h5l3-8 4 16 3-8h5"],
  arrow: ["M5 12h14M14 7l5 5-5 5"],
  external: ["M14 4h6v6M20 4l-9 9M10 5H4v15h15v-6"],
  chevron: ["M9 5l7 7-7 7"],
  down: ["M6 9l6 6 6-6"],
  search: ["M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14M15 15l6 6"],
  check: ["M5 12l4 4L19 6"],
  clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2"],
  branch: [
    "M6 8v8M18 8v2a5 5 0 0 1-5 5H6M6 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4M6 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4M18 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4",
  ],
  shield: ["M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"],
  alert: ["M12 3L2 21h20L12 3zM12 9v5M12 17v1"],
  menu: ["M4 6h16M4 12h16M4 18h16"],
  close: ["M5 5l14 14M19 5L5 19"],
  file: ["M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h4"],
  lock: ["M6 10h12v11H6zM8 10V6a4 4 0 0 1 8 0v4"],
  refresh: ["M20 11a8 8 0 1 0-2 7M20 3v8h-8"],
  github: [
    "M9 19c-5 2-5-3-7-3M16 22v-4a4 4 0 0 0-1-3c3 0 6-1 6-6a5 5 0 0 0-1-3 5 5 0 0 0 0-4s-1 0-4 2a13 13 0 0 0-8 0C5 2 4 2 4 2a5 5 0 0 0 0 4 5 5 0 0 0-1 3c0 5 3 6 6 6a4 4 0 0 0-1 3v4",
  ],
} as const;
export type IconName = keyof typeof paths;
export function Icon({
  name,
  size = 18,
  className,
  style,
}: {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {paths[name].map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}
export function ShrikeMark() {
  return (
    <svg
      width="31"
      height="31"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" fill="#c3e1ce" />
      <path d="M7 21L16 7l3 7 7 2-9 2-5 7 1-8-6 4z" fill="#233b30" />
    </svg>
  );
}
