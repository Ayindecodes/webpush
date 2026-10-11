import { useId } from "react";

import { BAR, CURSOR_GAP, CURSOR_PATH, GLOBE, STROKE, WORDMARK_HEIGHT, WORDMARK_SVG, WORDMARK_WIDTH } from "./geometry";

type Tone = "duo" | "brand" | "ink" | "current";

const TONE: Record<Tone, { mark: string; cursor: string }> = {
  duo: { mark: "text-fg", cursor: "var(--wx-brand)" },
  brand: { mark: "text-brand", cursor: "currentColor" },
  ink: { mark: "text-fg", cursor: "currentColor" },
  current: { mark: "", cursor: "currentColor" },
};

/**
 * The Browse mark: a globe crossed by an address bar, with a cursor on the bar.
 * `active` animates it — the globe turns, a scan sweeps the bar, the cursor
 * glides and clicks — and is reserved for moments when WEB X-RAY is actually
 * investigating. Reduced-motion users always get the static mark.
 */
export function Mark({
  size = 20,
  active = false,
  tone = "duo",
  title,
  className = "",
}: {
  size?: number;
  active?: boolean;
  tone?: Tone;
  title?: string;
  className?: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const t = TONE[tone];
  const bar = { x: BAR.x, y: BAR.y, width: BAR.w, height: BAR.h, rx: BAR.r };
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`wx-mark shrink-0 overflow-visible ${t.mark} ${className}`}
      data-active={active ? "true" : "false"}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      <defs>
        {/* Globe lines are hidden behind the bar; everything keeps clear of the cursor. */}
        <mask id={`g${id}`} maskUnits="userSpaceOnUse" x="-2" y="-2" width="28" height="28">
          <rect x="-2" y="-2" width="28" height="28" fill="#fff" />
          <rect {...bar} fill="#000" />
          <g className="wx-m-cursor">
            <path d={CURSOR_PATH} fill="#000" stroke="#000" strokeWidth={CURSOR_GAP} strokeLinejoin="round" />
          </g>
        </mask>
        <mask id={`b${id}`} maskUnits="userSpaceOnUse" x="-2" y="-2" width="28" height="28">
          <rect x="-2" y="-2" width="28" height="28" fill="#fff" />
          <g className="wx-m-cursor">
            <path d={CURSOR_PATH} fill="#000" stroke="#000" strokeWidth={CURSOR_GAP} strokeLinejoin="round" />
          </g>
        </mask>
        <clipPath id={`c${id}`}>
          <rect x={BAR.x + STROKE / 2} y={BAR.y + STROKE / 2} width={BAR.w - STROKE} height={BAR.h - STROKE} rx={BAR.r - STROKE / 2} />
        </clipPath>
      </defs>
      <g fill="none" stroke="currentColor" strokeWidth={STROKE} mask={`url(#g${id})`}>
        <circle cx={GLOBE.cx} cy={GLOBE.cy} r={GLOBE.r} />
        <ellipse className="wx-m-meridian" cx={GLOBE.cx} cy={GLOBE.cy} rx={GLOBE.meridianRx} ry={GLOBE.r} />
      </g>
      <g mask={`url(#b${id})`}>
        <rect {...bar} fill="none" stroke="currentColor" strokeWidth={STROKE} />
        <g clipPath={`url(#c${id})`}>
          <rect className="wx-m-scan" x={BAR.x - 4} y={BAR.y} width="4" height={BAR.h} fill={t.cursor} />
        </g>
      </g>
      <g className="wx-m-cursor">
        <path d={CURSOR_PATH} fill={t.cursor} stroke={t.cursor} strokeWidth="0.8" strokeLinejoin="round" />
        <circle className="wx-m-click" cx="13.4" cy="11.3" r="2.4" fill="none" stroke={t.cursor} strokeWidth="1" />
      </g>
    </svg>
  );
}

/** The drawn WEB X-RAY wordmark (geometric construction, no font dependency). */
export function Wordmark({ height = 14, className = "" }: { height?: number; className?: string }) {
  return (
    <svg
      viewBox={`0 0 ${WORDMARK_WIDTH} ${WORDMARK_HEIGHT}`}
      height={height}
      width={(height * WORDMARK_WIDTH) / WORDMARK_HEIGHT}
      fill="currentColor"
      className={`shrink-0 ${className}`}
      role="img"
      aria-label="WEB X-RAY"
    >
      <g dangerouslySetInnerHTML={{ __html: WORDMARK_SVG }} />
    </svg>
  );
}

/** Lockup: mark (1.55 × cap height) + wordmark, spaced at 0.5 × cap height. */
export function Logo({
  height = 14,
  active = false,
  tone = "duo",
  className = "",
}: {
  height?: number;
  active?: boolean;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center ${className}`} style={{ gap: height * 0.5 }}>
      <Mark size={height * 1.55} active={active} tone={tone} />
      <Wordmark height={height} className="text-fg" />
    </span>
  );
}
