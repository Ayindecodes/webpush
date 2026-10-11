"use client";

import { useState, type FormEvent } from "react";

import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink, ConfirmDialog, CopyButton, Field, Input, Mono, Notice, Select, useToast } from "@/components/ui/primitives";
import { StatusPill } from "@/components/ui/status";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Credential, Environment, VerificationInstructions, VerificationResult } from "@/lib/types";

const METHOD_LABEL: Record<string, string> = {
  http_file: "verification file",
  dns_txt: "DNS record",
  operator_allowlist: "workspace allowlist",
};

export function AddTargetForm({
  projectId,
  initialOrigin = "",
  onCreated,
}: {
  projectId: string;
  initialOrigin?: string;
  onCreated: (env: Environment) => void;
}) {
  const [origin, setOrigin] = useState(initialOrigin);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const raw = origin.trim();
      onCreated(await api.post<Environment>(`/api/projects/${projectId}/environments`, { origin: raw.includes("://") ? raw : `https://${raw}`, label }));
      setOrigin("");
      setLabel("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_200px_auto] sm:items-start">
      <Field label="Website address" htmlFor="origin" error={error} hint="Just the address — like https://staging.example.com. Paths are ignored.">
        <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="https://staging.example.com" className="font-mono text-[14px]" required spellCheck={false} />
      </Field>
      <Field label="Nickname" htmlFor="tlabel" optional>
        <Input id="tlabel" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Staging" maxLength={120} />
      </Field>
      <Button type="submit" variant="primary" loading={busy} disabled={!origin.trim()} icon={<Icon.Plus />} className="sm:mt-[30px]">
        Add website
      </Button>
    </form>
  );
}

export function TargetRow({ env, onChange, manage = false }: { env: Environment; onChange: () => void; manage?: boolean }) {
  const toast = useToast();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [open, setOpen] = useState(!manage && env.verification_status !== "verified");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const instructions = useApi<VerificationInstructions>(open && env.verification_status !== "verified" ? `/api/environments/${env.id}/verification-instructions` : null);

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<VerificationResult>(`/api/environments/${env.id}/verify`);
      setResult(r);
      if (r.verified) onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const verified = env.verification_status === "verified";
  return (
    <li className="border-b border-border last:border-b-0">
      <div className="flex flex-wrap items-center gap-3 px-5 py-4">
        <Icon.Globe className="text-fg-subtle" />
        <div className="min-w-0 flex-1">
          <Mono className="break-all text-[14px]">{env.origin}</Mono>
          {env.label && <span className="ml-2 text-label text-fg-subtle">{env.label}</span>}
        </div>
        {verified ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-0.5 text-meta font-medium text-success" title={`Confirmed ${relativeTime(env.verified_at)}`}>
            <Icon.Check size={12} /> Ownership confirmed{env.verification_method ? ` · ${METHOD_LABEL[env.verification_method] ?? env.verification_method}` : ""}
          </span>
        ) : (
          <StatusPill status="pending" />
        )}
        {!verified && (
          <Button size="sm" variant={open ? "ghost" : "primary"} onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide steps" : "Prove it's yours"}
          </Button>
        )}
        {manage && verified && (
          <ButtonLink href={`/investigations/new?environment=${env.id}`} size="sm" variant="primary" icon={<Icon.Search size={13} />}>
            Check this site
          </ButtonLink>
        )}
        {manage && (
          <Button size="sm" variant="ghost" icon={<Icon.Trash />} onClick={() => setConfirmRemove(true)} aria-label={`Remove ${env.origin}`}>
            Remove
          </Button>
        )}
      </div>
      {manage && (
        <ConfirmDialog
          open={confirmRemove}
          title={`Remove ${env.origin}?`}
          description="Its saved test accounts are deleted too. Websites that already have investigations can't be removed, so no results are lost."
          confirmLabel="Remove website"
          busy={removing}
          onCancel={() => setConfirmRemove(false)}
          onConfirm={async () => {
            setRemoving(true);
            try {
              await api.del(`/api/environments/${env.id}`);
              toast("Website removed");
              onChange();
            } catch (e) {
              toast(e instanceof Error ? e.message : "Couldn't remove it", "danger");
            } finally {
              setRemoving(false);
              setConfirmRemove(false);
            }
          }}
        />
      )}
      {open && !verified && (
        <div className="space-y-4 border-t border-border bg-surface-2/50 px-5 py-5">
          <p className="text-body leading-relaxed text-fg-muted">
            To make sure nobody tests a site they don&apos;t own, add <strong className="text-fg">one</strong> of these to your
            website, then press <em>Check now</em>. It usually takes a couple of minutes.
          </p>
          {instructions.error && <Notice tone="danger">{instructions.error.message}</Notice>}
          {instructions.data && (
            <div className="grid gap-4 lg:grid-cols-2">
              <MethodCard
                title="Option A · Upload a small file"
                body="Create this file on your website. Good if you can upload files."
                rows={[
                  ["Address", instructions.data.http_file_url],
                  ["File contents", instructions.data.http_file_content],
                ]}
              />
              <MethodCard
                title="Option B · Add a DNS record"
                body="Add a TXT record where you manage your domain."
                rows={[
                  ["Name", instructions.data.dns_txt_name],
                  ["Value", instructions.data.dns_txt_value],
                ]}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={verify} loading={busy} variant="primary" icon={<Icon.Shield size={15} />}>
              Check now
            </Button>
            {result && !result.verified && (
              <span role="status" className="text-label text-fg-muted">
                Not confirmed yet: {result.detail}
              </span>
            )}
            {error && (
              <span role="alert" className="text-label font-medium text-danger">
                {error}
              </span>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function MethodCard({ title, body, rows }: { title: string; body: string; rows: [string, string][] }) {
  return (
    <div className="panel p-4">
      <div className="text-body font-semibold">{title}</div>
      <p className="mt-0.5 text-label text-fg-muted">{body}</p>
      <dl className="mt-3 space-y-2.5">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-label text-fg-subtle">{k}</dt>
            <dd className="mt-1 flex items-start gap-1 rounded-lg bg-surface-2 px-2.5 py-1.5">
              <Mono className="min-w-0 flex-1 break-all">{v}</Mono>
              <CopyButton text={v} label="" />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function CredentialForm({
  projectId,
  environments,
  onCreated,
}: {
  projectId: string;
  environments: Environment[];
  onCreated: (c: Credential) => void;
}) {
  const [envId, setEnvId] = useState(environments[0]?.id ?? "");
  const [label, setLabel] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const c = await api.post<Credential>(`/api/projects/${projectId}/credentials`, { environment_id: envId, label, username, password });
      setUsername("");
      setPassword("");
      setLabel("");
      onCreated(c);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (environments.length === 0) return <p className="text-body text-fg-subtle">Add a website first, then you can save test accounts for it.</p>;
  return (
    <form onSubmit={submit} className="space-y-4" autoComplete="off">
      <Notice title="Use a test account, not a personal one">
        Passwords are encrypted, only typed into our isolated browser, hidden from logs and screenshots, and can never be shown
        again — not even to you.
      </Notice>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Website" htmlFor="cenv">
          <Select id="cenv" value={envId} onChange={(e) => setEnvId(e.target.value)}>
            {environments.map((e) => (
              <option key={e.id} value={e.id}>
                {e.origin}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Name for this account" htmlFor="clabel">
          <Input id="clabel" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="QA account" required maxLength={120} />
        </Field>
        <Field label="Username or email" htmlFor="cuser">
          <Input id="cuser" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" spellCheck={false} required maxLength={320} />
        </Field>
        <Field label="Password" htmlFor="cpass">
          <Input id="cpass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required maxLength={512} />
        </Field>
      </div>
      {error && (
        <p role="alert" className="text-label font-medium text-danger">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" loading={busy} icon={<Icon.Lock />}>
        Save test account
      </Button>
    </form>
  );
}

const LIFECYCLE: Record<string, string> = {
  active: "Ready",
  registered: "Ready",
  registration_pending: "Being created",
  verification_required: "Needs email/phone verification",
  registration_failed: "Couldn't be created",
  outcome_unknown: "Status unknown",
};

export function CredentialList({ items, environments, onChange }: { items: Credential[]; environments: Environment[]; onChange?: () => void }) {
  const toast = useToast();
  const [pending, setPending] = useState<Credential | null>(null);
  const [busy, setBusy] = useState(false);
  if (items.length === 0) return <p className="text-body text-fg-subtle">No test accounts saved.</p>;
  return (
    <>
      <ul className="panel divide-y divide-border overflow-hidden">
        {items.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 px-5 py-4">
            <Icon.Lock className="text-fg-subtle" />
            <div className="min-w-0 flex-1">
              <div className="text-body font-semibold">{c.label}</div>
              <div className="text-label text-fg-subtle">
                <Mono>{c.username_hint}</Mono> · {environments.find((e) => e.id === c.environment_id)?.origin ?? "website removed"} ·{" "}
                {c.source === "generated" ? "created by WEB X-RAY" : "added by you"}
              </div>
            </div>
            <StatusPill status={c.lifecycle_state === "active" || c.lifecycle_state === "registered" ? "done" : "pending"} className="normal-case" />
            <span className="text-label text-fg-muted">{LIFECYCLE[c.lifecycle_state] ?? c.lifecycle_state.replace(/_/g, " ")}</span>
            {onChange && (
              <Button size="sm" variant="ghost" icon={<Icon.Trash />} onClick={() => setPending(c)} aria-label={`Delete ${c.label}`}>
                Delete
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={!!pending}
        title={`Delete “${pending?.label ?? ""}”?`}
        description="The encrypted password is erased. Investigations already run keep their results, but new ones can't use this account."
        confirmLabel="Delete test account"
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          if (!pending) return;
          setBusy(true);
          try {
            await api.del(`/api/credentials/${pending.id}`);
            toast("Test account deleted");
            onChange?.();
          } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't delete", "danger");
          } finally {
            setBusy(false);
            setPending(null);
          }
        }}
      />
    </>
  );
}
