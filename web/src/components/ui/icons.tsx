import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...rest,
  };
}

export const Icon = {
  Compass: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="6" />
      <path d="M10.5 5.5 9 9 5.5 10.5 7 7z" />
    </svg>
  ),
  Home: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M2.5 7 8 2.5 13.5 7" />
      <path d="M4 6v7.5h8V6" />
      <path d="M6.75 13.5V10h2.5v3.5" />
    </svg>
  ),
  Question: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="6" />
      <path d="M6.3 6.2a1.8 1.8 0 0 1 3.5.5c0 1.2-1.8 1.5-1.8 2.6" />
      <path d="M8 11.4v.1" />
    </svg>
  ),
  Eye: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </svg>
  ),
  Overview: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </svg>
  ),
  Investigation: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M2 8h12" strokeDasharray="1.2 1.2" />
      <path d="M5 5.5h3M5 10.5h6" />
    </svg>
  ),
  Finding: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M3.5 14V2.5M3.5 3h8l-1.5 3 1.5 3h-8" />
    </svg>
  ),
  Journey: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="3.5" cy="12.5" r="1.5" />
      <circle cx="12.5" cy="3.5" r="1.5" />
      <path d="M5 12.5h4.5a2 2 0 0 0 0-4h-3a2 2 0 0 1 0-4H11" />
    </svg>
  ),
  Project: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 1.5h4.5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z" />
    </svg>
  ),
  Integration: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M6 2v3M10 2v3M4.5 5h7v2.5a3.5 3.5 0 0 1-7 0zM8 11v3" />
    </svg>
  ),
  Settings: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.5v1.8M8 12.7v1.8M14.5 8h-1.8M3.3 8H1.5M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3M12.6 12.6l-1.3-1.3M4.7 4.7L3.4 3.4" />
    </svg>
  ),
  Plus: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 3v10M3 8h10" />
    </svg>
  ),
  Pause: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M5.5 3.5v9M10.5 3.5v9" />
    </svg>
  ),
  Play: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M5 3.5l7 4.5-7 4.5z" />
    </svg>
  ),
  Stop: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="4" y="4" width="8" height="8" rx="1" />
    </svg>
  ),
  Chevron: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M6 4l4 4-4 4" />
    </svg>
  ),
  ChevronDown: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M4 6l4 4 4-4" />
    </svg>
  ),
  ArrowLeft: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M13 8H3M7 4L3 8l4 4" />
    </svg>
  ),
  External: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M9 3h4v4M13 3L7.5 8.5M11 9.5V13H3V5h3.5" />
    </svg>
  ),
  Copy: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 5.5V3.5A1 1 0 0 0 9.5 2.5h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" />
    </svg>
  ),
  Check: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M3 8.5l3 3 7-7" />
    </svg>
  ),
  X: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  ),
  Download: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 2.5v8M4.5 7L8 10.5 11.5 7M3 13.5h10" />
    </svg>
  ),
  Search: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  ),
  Sidebar: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M6 2.5v11" />
    </svg>
  ),
  Menu: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
    </svg>
  ),
  Lock: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="3" y="7" width="10" height="7" rx="1.5" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
    </svg>
  ),
  Globe: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c1.8 1.8 2.5 3.8 2.5 6S9.8 12.2 8 14C6.2 12.2 5.5 10.2 5.5 8S6.2 3.8 8 2z" />
    </svg>
  ),
  Desktop: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="1.5" y="2.5" width="13" height="8.5" rx="1" />
      <path d="M6 14h4M8 11v3" />
    </svg>
  ),
  Tablet: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="3" y="1.5" width="10" height="13" rx="1.5" />
      <path d="M7 12.5h2" />
    </svg>
  ),
  Mobile: (p: IconProps) => (
    <svg {...base(p)}>
      <rect x="4.5" y="1.5" width="7" height="13" rx="1.5" />
      <path d="M7.25 12.5h1.5" />
    </svg>
  ),
  Refresh: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M13 3.5V7H9.5M3 12.5V9h3.5" />
      <path d="M12.6 7A5 5 0 0 0 3.8 5M3.4 9a5 5 0 0 0 8.8 2" />
    </svg>
  ),
  ArrowRight: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  ),
  Book: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M3 2.5h7.5a2 2 0 0 1 2 2v9H5a2 2 0 0 1-2-2z" />
      <path d="M3 11.5a2 2 0 0 1 2-2h7.5" />
    </svg>
  ),
  Shield: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 1.8l5 2v4c0 3-2.1 5.3-5 6.4-2.9-1.1-5-3.4-5-6.4v-4z" />
      <path d="M5.8 8l1.6 1.6 2.9-3" />
    </svg>
  ),
  Code: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M5.5 4.5L2 8l3.5 3.5M10.5 4.5L14 8l-3.5 3.5" />
    </svg>
  ),
  Layers: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 2l6 3-6 3-6-3z" />
      <path d="M2 8l6 3 6-3M2 11l6 3 6-3" />
    </svg>
  ),
  Activity: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M1.5 8h3l2-5 3 10 2-5h3" />
    </svg>
  ),
  Sun: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="2.8" />
      <path d="M8 1.5v1.3M8 13.2v1.3M14.5 8h-1.3M2.8 8H1.5M12.6 3.4l-.9.9M4.3 11.7l-.9.9M12.6 12.6l-.9-.9M4.3 4.3l-.9-.9" />
    </svg>
  ),
  Moon: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M13.5 9.5A5.8 5.8 0 0 1 6.5 2.5 5.8 5.8 0 1 0 13.5 9.5z" />
    </svg>
  ),
  Logout: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M6 13.5H3.5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1H6M10.5 11l3-3-3-3M13.5 8H6" />
    </svg>
  ),
  Trash: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M2.5 4h11M6.5 4V2.5h3V4M4 4l.7 9.5h6.6L12 4" />
    </svg>
  ),
  Target: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="6" />
      <circle cx="8" cy="8" r="2.5" />
    </svg>
  ),
  Bell: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M4 11V7a4 4 0 0 1 8 0v4l1 1.5H3zM6.5 14h3" />
    </svg>
  ),
  Flask: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M6 1.5h4M6.5 1.5v4L2.8 12.4a1.2 1.2 0 0 0 1 1.8h8.4a1.2 1.2 0 0 0 1-1.8L9.5 5.5v-4M4.6 9.5h6.8" />
    </svg>
  ),
  // Severity glyphs: distinct shapes so severity never depends on color alone.
  SevCritical: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M5.5 1.5h5l4 4v5l-4 4h-5l-4-4v-5z" fill="currentColor" stroke="none" />
      <path d="M8 4.5v4M8 10.8v.2" stroke="var(--wx-bg)" strokeWidth="1.7" />
    </svg>
  ),
  SevHigh: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 1.8l6.5 11.7h-13z" fill="currentColor" stroke="none" />
      <path d="M8 6v3.6M8 11.3v.2" stroke="var(--wx-bg)" strokeWidth="1.6" />
    </svg>
  ),
  SevMedium: (p: IconProps) => (
    <svg {...base(p)}>
      <path d="M8 2.5l5.8 10.5H2.2z" />
      <path d="M8 6.5v3M8 11.2v.1" />
    </svg>
  ),
  SevLow: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M5.5 8h5" />
    </svg>
  ),
  SevInfo: (p: IconProps) => (
    <svg {...base(p)}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 7.5v3.5M8 5.2v.1" />
    </svg>
  ),
};
