"use client";

import Link from "next/link";
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { Icon } from "./icons";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ------------------------------------------------------------------ buttons

/**
 * primary = ink pill (the main action on a screen), brand = teal pill (rare,
 * for "start" moments), secondary/paper = outlined paper pill, ghost = text.
 */
type Variant = "primary" | "brand" | "secondary" | "ghost" | "danger" | "outline" | "ink" | "paper";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-fg text-bg border border-fg hover:bg-fg/85",
  ink: "bg-fg text-bg border border-fg hover:bg-fg/85",
  brand: "bg-brand text-brand-fg border border-transparent hover:bg-brand-hover",
  secondary: "bg-surface text-fg border border-border-strong hover:border-fg",
  paper: "bg-surface text-fg border border-border-strong hover:border-fg",
  outline: "bg-transparent text-fg border border-border-strong hover:border-fg",
  ghost: "text-fg-muted hover:text-fg hover:bg-surface-2 border border-transparent",
  danger: "bg-danger-soft text-danger border border-danger/30 hover:border-danger",
};
const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-label gap-1.5",
  md: "h-10 px-4 text-body gap-2",
  lg: "h-12 px-6 text-[1rem] gap-2",
};
const BASE =
  "inline-flex select-none items-center justify-center whitespace-nowrap rounded-full font-medium transition-[background-color,border-color,color,opacity] duration-150 disabled:cursor-not-allowed disabled:opacity-45";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  /** Put the icon after the label (for "Next →" style actions). */
  trailingIcon?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, trailingIcon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(BASE, VARIANTS[variant], SIZES[size], trailingIcon && "flex-row-reverse", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  trailingIcon,
  children,
  className,
  download,
  external,
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  trailingIcon?: boolean;
  children: ReactNode;
  className?: string;
  download?: boolean;
  external?: boolean;
}) {
  const cls = cx(BASE, VARIANTS[variant], SIZES[size], trailingIcon && "flex-row-reverse", className);
  if (download || external || href.startsWith("/api/")) {
    return (
      <a href={href} className={cls} download={download || undefined} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
        {icon}
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {icon}
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx("inline-block size-3.5 animate-spin rounded-full border-[1.5px] border-current border-r-transparent", className)}
    />
  );
}

// ------------------------------------------------------------------ layout

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("eyebrow", className)}>{children}</p>;
}

export function PageHeader({
  title,
  description,
  actions,
  meta,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 pb-7 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-3">{eyebrow}</p>}
        <h1 className="display break-words">{title}</h1>
        {description && <p className="mt-2.5 max-w-2xl text-body leading-relaxed text-fg-muted">{description}</p>}
        {meta && <div className="mt-3.5 flex flex-wrap items-center gap-x-5 gap-y-2 text-label text-fg-subtle">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
  id,
  eyebrow,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  eyebrow?: ReactNode;
}) {
  return (
    <section id={id} className={cx("scroll-mt-24", className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
            {title && <h2 className="text-[1.25rem] font-semibold leading-tight tracking-[-0.02em]">{title}</h2>}
            {description && <p className="mt-1 max-w-2xl text-body text-fg-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** A card. `ink` = bordered in ink with the offset shadow (for the one thing that matters most). */
export function Panel({
  children,
  className,
  padded = true,
  ink,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  ink?: boolean | "sm";
}) {
  return (
    <div className={cx(ink === "sm" ? "card-ink-sm" : ink ? "card-ink" : "panel", padded && "p-5 sm:p-6", "min-w-0", className)}>
      {children}
    </div>
  );
}

export function KeyValue({ items, className }: { items: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <dl className={cx("grid grid-cols-[minmax(7rem,max-content)_1fr] gap-x-6 gap-y-2.5 text-body", className)}>
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-label text-fg-subtle">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Metric({
  label,
  value,
  hint,
  href,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  href?: string;
  tone?: "danger" | "brand" | "success";
}) {
  const body = (
    <>
      <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-subtle">{label}</div>
      <div
        className={cx(
          "mt-2 text-[2rem] font-semibold leading-none tracking-[-0.03em] tabular",
          tone === "danger" && "text-danger",
          tone === "brand" && "text-brand-text",
          tone === "success" && "text-success",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-label text-fg-muted">{hint}</div>}
    </>
  );
  const cls = "block min-w-0 px-5 py-5 sm:px-6";
  return href ? (
    <Link href={href} className={cx(cls, "group transition-colors hover:bg-surface-2")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function MetricStrip({ children }: { children: ReactNode }) {
  return (
    <div className="panel grid grid-cols-2 overflow-hidden lg:grid-cols-4 [&>*]:border-border max-lg:[&>*:nth-child(even)]:border-l max-lg:[&>*:nth-child(n+3)]:border-t lg:[&>*:not(:first-child)]:border-l">
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "success" | "warning" | "danger" | "ink";
  className?: string;
}) {
  const tones = {
    neutral: "bg-surface-2 text-fg-muted border-border",
    brand: "bg-brand-soft text-brand-text border-brand-line",
    success: "bg-success-soft text-success border-success/25",
    warning: "bg-warning-soft text-warning border-warning/25",
    danger: "bg-danger-soft text-danger border-danger/25",
    ink: "bg-fg text-bg border-fg",
  };
  return (
    <span className={cx("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full border px-2.5 text-meta font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

/** Numbered step marker, as on the landing page ("01 · Verify"). */
export function StepTile({ children, active, done }: { children: ReactNode; active?: boolean; done?: boolean }) {
  return (
    <span
      className={cx(
        "flex size-10 shrink-0 items-center justify-center rounded-xl border-[1.5px] font-mono text-[12px] font-medium",
        done ? "border-fg bg-fg text-bg" : active ? "border-fg bg-surface text-fg shadow-[3px_3px_0_var(--wx-ink-shadow)]" : "border-border-strong bg-surface text-fg-subtle",
      )}
    >
      {done ? <Icon.Check size={16} /> : children}
    </span>
  );
}

/** Plain-language explanation that can be opened next to jargon. */
export function Explain({ summary = "What does this mean?", children }: { summary?: string; children: ReactNode }) {
  return (
    <details className="group text-label">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-fg-muted underline decoration-dotted underline-offset-4 hover:text-fg [&::-webkit-details-marker]:hidden">
        <Icon.SevInfo size={13} /> {summary}
      </summary>
      <div className="mt-2 max-w-xl rounded-xl border border-border bg-surface-2 px-4 py-3 text-body leading-relaxed text-fg-muted">{children}</div>
    </details>
  );
}

// ------------------------------------------------------------------ states

export function EmptyState({
  title,
  description,
  action,
  icon,
  compact,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-center rounded-2xl border-[1.5px] border-dashed border-border-strong bg-surface/60 text-center",
        compact ? "gap-2 px-5 py-8" : "gap-3 px-6 py-14",
      )}
    >
      {icon && (
        <div className="mb-1 flex size-12 items-center justify-center rounded-xl border-[1.5px] border-fg bg-surface text-fg shadow-[3px_3px_0_var(--wx-ink-shadow)]">
          {icon}
        </div>
      )}
      <div className="text-[1.125rem] font-semibold tracking-[-0.01em]">{title}</div>
      {description && <div className="max-w-md text-body leading-relaxed text-fg-muted">{description}</div>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-danger/40 bg-danger-soft px-5 py-4">
      <Icon.SevHigh className="mt-0.5 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <div className="text-body font-medium">Something went wrong</div>
        <div className="mt-0.5 break-words text-label text-fg-muted">{message}</div>
      </div>
      {retry && (
        <Button size="sm" onClick={retry} icon={<Icon.Refresh />}>
          Try again
        </Button>
      )}
    </div>
  );
}

/**
 * Error for a page that loads one record. A 404 (missing, or belonging to another
 * workspace — the API doesn't distinguish) becomes a friendly "not found" with a
 * way back; anything else is shown with a retry.
 */
export function LoadError({ error, retry, what, backHref, backLabel }: { error: unknown; retry?: () => void; what: string; backHref: string; backLabel: string }) {
  const status = typeof error === "object" && error !== null && "status" in error ? (error as { status: number }).status : 0;
  if (status === 404) {
    return (
      <EmptyState
        icon={<Icon.Search size={20} />}
        title={`We couldn't find that ${what}`}
        description={`It may have been deleted, or it belongs to a different workspace.`}
        action={
          <ButtonLink href={backHref} variant="primary" icon={<Icon.ArrowLeft size={14} />}>
            {backLabel}
          </ButtonLink>
        }
      />
    );
  }
  return <ErrorState error={error} retry={retry} />;
}

export function Notice({
  children,
  tone = "neutral",
  title,
  action,
}: {
  children: ReactNode;
  tone?: "neutral" | "warn" | "brand" | "success" | "danger";
  title?: string;
  action?: ReactNode;
}) {
  const styles = {
    neutral: "border-border bg-surface-2/70",
    brand: "border-brand-line bg-brand-soft",
    warn: "border-warning/40 bg-warning-soft",
    success: "border-success/40 bg-success-soft",
    danger: "border-danger/40 bg-danger-soft",
  };
  const icon = {
    neutral: <Icon.SevInfo className="mt-0.5 shrink-0 text-fg-subtle" />,
    brand: <Icon.SevInfo className="mt-0.5 shrink-0 text-brand-text" />,
    warn: <Icon.SevMedium className="mt-0.5 shrink-0 text-warning" />,
    success: <Icon.Check className="mt-0.5 shrink-0 text-success" />,
    danger: <Icon.SevHigh className="mt-0.5 shrink-0 text-danger" />,
  };
  return (
    <div
      role={tone === "danger" || tone === "warn" ? "alert" : undefined}
      className={cx("flex flex-wrap gap-3 rounded-2xl border px-5 py-4 text-body sm:flex-nowrap", styles[tone])}
    >
      {icon[tone]}
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold text-fg">{title}</div>}
        <div className={cx(title ? "mt-1" : "", "leading-relaxed text-fg-muted")}>{children}</div>
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-xl bg-surface-2", className)} aria-hidden />;
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-busy aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ forms

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  optional,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  htmlFor?: string;
  optional?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <label htmlFor={htmlFor} className="text-label font-semibold text-fg">
        {label}
        {optional && <span className="ml-1.5 font-normal text-fg-subtle">Optional</span>}
      </label>
      {children}
      {hint && !error && <p className="text-label leading-relaxed text-fg-subtle">{hint}</p>}
      {error && (
        <p className="text-label font-medium text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const control =
  "h-11 w-full rounded-xl border border-border-strong bg-surface px-3.5 text-body text-fg placeholder:text-fg-subtle transition-[border-color,box-shadow] hover:border-fg/50 focus-visible:border-fg focus-visible:outline-none focus-visible:shadow-[0_0_0_4px_var(--wx-brand-soft)] disabled:opacity-50 aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cx(control, className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cx(control, "h-auto min-h-24 py-2.5 leading-relaxed", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cx(control, "cursor-pointer pr-9", className)} {...rest}>
      {children}
    </select>
  );
});

export function Checkbox({
  checked,
  onChange,
  label,
  description,
  disabled,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}) {
  const auto = useId();
  const cid = id ?? auto;
  return (
    <div className={cx("flex items-start gap-3", disabled && "opacity-50")}>
      <input
        id={cid}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 size-[18px] shrink-0 cursor-pointer accent-[var(--wx-fg)] disabled:cursor-not-allowed"
      />
      <label htmlFor={cid} className={cx("min-w-0", disabled ? "cursor-not-allowed" : "cursor-pointer")}>
        <span className="text-body font-medium text-fg">{label}</span>
        {description && <span className="mt-0.5 block text-label leading-relaxed text-fg-muted">{description}</span>}
      </label>
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative h-6 w-11 shrink-0 rounded-full border-[1.5px] transition-colors",
        checked ? "border-fg bg-fg" : "border-border-strong bg-surface-3",
      )}
    >
      <span className={cx("absolute top-[2px] size-4 rounded-full shadow transition-[left]", checked ? "left-[21px] bg-bg" : "left-[2px] bg-surface")} />
    </button>
  );
}

// ------------------------------------------------------------------ tabs & segmented

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { value: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    refs.current[next]?.focus();
    onChange(tabs[next].value);
  };
  return (
    <div role="tablist" aria-label={label} className="flex gap-1.5 overflow-x-auto [scrollbar-width:none] sm:flex-wrap sm:overflow-visible">
      {tabs.map((t, i) => {
        const selected = t.value === value;
        return (
          <button
            key={t.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onKeyDown={(e) => onKey(e, i)}
            onClick={() => onChange(t.value)}
            className={cx(
              "flex h-9 shrink-0 items-center gap-2 rounded-full border px-4 text-body transition-colors",
              selected ? "border-fg bg-fg font-medium text-bg" : "border-border text-fg-muted hover:border-border-strong hover:text-fg",
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <span className={cx("rounded-full px-1.5 text-meta tabular", selected ? "bg-bg/20 text-bg" : "bg-surface-2 text-fg-subtle")}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-border bg-surface p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "flex h-8 items-center gap-1.5 rounded-full px-3.5 text-label transition-colors",
            o.value === value ? "bg-fg font-medium text-bg" : "text-fg-muted hover:text-fg",
          )}
        >
          {o.label}
          {o.count !== undefined && <span className={cx("text-meta tabular", o.value === value ? "text-bg/70" : "text-fg-subtle")}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ dialogs

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className={cx(
        "card-ink m-auto w-[calc(100%-2rem)] p-0 text-fg backdrop:bg-overlay backdrop:backdrop-blur-[2px]",
        wide ? "max-w-5xl" : "max-w-lg",
      )}
    >
      <div className="flex items-start justify-between gap-4 px-6 pb-3 pt-5">
        <div className="min-w-0">
          <h2 className="text-[1.25rem] font-semibold tracking-[-0.02em]">{title}</h2>
          {description && <p className="mt-1.5 text-body leading-relaxed text-fg-muted">{description}</p>}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close" icon={<Icon.X />} className="-mr-2 size-8 px-0" />
      </div>
      {children && <div className="max-h-[72vh] overflow-auto px-6 pb-6">{children}</div>}
      {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-border px-6 py-4">{footer}</div>}
    </dialog>
  );
}

/** A styled confirmation for consequential actions (replaces window.confirm). */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  tone = "danger",
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  tone?: "danger" | "primary";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={busy} autoFocus>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}

// ------------------------------------------------------------------ toasts

interface Toast {
  id: number;
  message: string;
  tone: "success" | "danger" | "neutral";
}
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100%-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role="status" className="card-ink-sm wx-enter pointer-events-auto flex items-start gap-2.5 px-4 py-3 text-body">
            {t.tone === "success" ? (
              <Icon.Check className="mt-0.5 shrink-0 text-success" />
            ) : t.tone === "danger" ? (
              <Icon.SevHigh className="mt-0.5 shrink-0 text-danger" />
            ) : (
              <Icon.SevInfo className="mt-0.5 shrink-0 text-fg-subtle" />
            )}
            <span className="min-w-0 flex-1">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

// ------------------------------------------------------------------ code & misc

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="sm"
      variant="ghost"
      icon={copied ? <Icon.Check /> : <Icon.Copy />}
      aria-label={label ? undefined : copied ? "Copied" : "Copy to clipboard"}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {label ? (copied ? "Copied" : label) : null}
    </Button>
  );
}

export function CodeBlock({ code, title, maxHeight = "28rem", actions }: { code: string; title?: ReactNode; maxHeight?: string; actions?: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border-strong bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="truncate font-mono text-meta text-fg-muted">{title}</div>
        <div className="flex items-center gap-1">
          {actions}
          <CopyButton text={code} />
        </div>
      </div>
      <pre className="overflow-auto bg-surface-2/50 p-4 font-mono text-[12.5px] leading-[1.65]" style={{ maxHeight }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[12.5px]", className)}>{children}</span>;
}

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex" tabIndex={0} aria-label={content}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-64 -translate-x-1/2 rounded-lg bg-fg px-2.5 py-1.5 text-meta text-bg opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100"
      >
        {content}
      </span>
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border-strong bg-surface-2 px-1 font-mono text-[11px] text-fg-muted">{children}</kbd>;
}
