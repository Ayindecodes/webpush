"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink, EmptyState, ErrorState, Input, LoadingRows, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  useCrumbs([{ label: "Websites" }]);
  const router = useRouter();
  const { data, error, mutate } = useApi<Project[]>("/api/projects");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const p = await api.post<Project>("/api/projects", { name: name.trim() });
      await mutate();
      router.push(`/projects/${p.id}`);
    } catch (err) {
      setFormError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <PageHeader
        title="Websites"
        description="The websites you've added, grouped into projects. A project is one app — for example your live shop and its test copy — plus the test accounts used to sign in."
        actions={
          <ButtonLink href="/investigations/new" variant="primary" icon={<Icon.Search size={15} />}>
            Check a website
          </ButtonLink>
        }
      />

      {error ? (
        <ErrorState error={error} retry={() => mutate()} />
      ) : !data ? (
        <LoadingRows />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<Icon.Project size={20} />}
          title="No projects yet"
          description="The easiest way to start is to check a website — we'll create a project for it automatically."
          action={
            <ButtonLink href="/investigations/new" variant="primary">
              Check a website
            </ButtonLink>
          }
        />
      ) : (
        <ul className="grid gap-5 md:grid-cols-2">
          {data.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`} className="panel group flex h-full items-start gap-4 p-6 transition-[border-color,box-shadow] hover:border-[var(--wx-ink-line)] hover:shadow-[3px_3px_0_var(--wx-ink-shadow)]">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border-[1.5px] border-[var(--wx-ink-line)] bg-surface-2">
                  <Icon.Project size={18} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[1.125rem] font-semibold tracking-[-0.01em]">{p.name}</div>
                  <div className="mt-1 text-body text-fg-muted">
                    {p.environment_count} website{p.environment_count === 1 ? "" : "s"} · {p.investigation_count} investigation{p.investigation_count === 1 ? "" : "s"}
                  </div>
                  <div className="mt-0.5 text-label text-fg-subtle">Created {relativeTime(p.created_at)}</div>
                </div>
                <Icon.Chevron className="mt-1 text-fg-subtle transition-transform group-hover:translate-x-0.5" />
              </Link>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={create} className="panel flex max-w-2xl flex-col gap-3 p-5 sm:flex-row sm:items-start">
        <div className="flex-1">
          <label htmlFor="pname" className="text-label font-semibold">
            New project
          </label>
          <Input id="pname" className="mt-2" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Online shop" maxLength={120} required />
          {formError && (
            <p role="alert" className="mt-1.5 text-label text-danger">
              {formError}
            </p>
          )}
        </div>
        <Button type="submit" variant="paper" loading={busy} disabled={!name.trim()} icon={<Icon.Plus />} className="sm:mt-[30px]">
          Create project
        </Button>
      </form>
    </div>
  );
}
