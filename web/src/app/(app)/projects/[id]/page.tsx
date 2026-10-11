"use client";

import { useParams } from "next/navigation";

import { InvestigationTable } from "@/components/lists";
import { useCrumbs } from "@/components/shell/context";
import { AddTargetForm, CredentialForm, CredentialList, TargetRow } from "@/components/targets";
import { Icon } from "@/components/ui/icons";
import { ButtonLink, EmptyState, ErrorState, LoadError, LoadingRows, PageHeader, Section } from "@/components/ui/primitives";
import { useApi } from "@/lib/hooks";
import type { Credential, Environment, Investigation, Project } from "@/lib/types";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const project = useApi<Project>(`/api/projects/${id}`);
  const ok = !!project.data;
  const envs = useApi<Environment[]>(ok ? `/api/projects/${id}/environments` : null);
  const creds = useApi<Credential[]>(ok ? `/api/projects/${id}/credentials` : null);
  const invs = useApi<Investigation[]>(ok ? `/api/investigations?project_id=${id}&limit=20` : null, { refreshInterval: 10_000 });
  useCrumbs([{ label: "Websites", href: "/projects" }, { label: project.data?.name ?? "Project" }]);

  if (project.error) return <LoadError error={project.error} retry={() => project.mutate()} what="project" backHref="/projects" backLabel="All projects" />;
  if (!project.data) return <LoadingRows />;

  return (
    <div className="space-y-14">
      <PageHeader eyebrow="Project" title={project.data.name} description="The websites in this project, the test accounts for signing in to them, and their investigations." />

      <Section eyebrow="Websites" title="Websites" description="Prove each website is yours once; after that you can check it whenever you like.">
        {envs.error ? (
          <ErrorState error={envs.error} retry={() => envs.mutate()} />
        ) : !envs.data ? (
          <LoadingRows rows={2} />
        ) : envs.data.length === 0 ? (
          <EmptyState compact title="No websites yet" description="Add the address of the site you want to check — a test copy is best." />
        ) : (
          <ul className="panel overflow-hidden">
            {envs.data.map((e) => (
              <TargetRow key={e.id} env={e} manage onChange={() => envs.mutate()} />
            ))}
          </ul>
        )}
        <div className="panel mt-5 p-5">
          <AddTargetForm projectId={id} onCreated={() => envs.mutate()} />
        </div>
      </Section>

      <Section eyebrow="Signing in" title="Test accounts" description="Accounts our browser can sign in with, and accounts it created itself. Passwords are encrypted and can't be shown again.">
        <div className="grid gap-6 xl:grid-cols-2">
          <div>{creds.error ? <ErrorState error={creds.error} /> : creds.data ? <CredentialList items={creds.data} environments={envs.data ?? []} onChange={() => creds.mutate()} /> : <LoadingRows rows={2} />}</div>
          <div className="panel p-5">
            <CredentialForm projectId={id} environments={envs.data ?? []} onCreated={() => creds.mutate()} />
          </div>
        </div>
      </Section>

      <Section
        eyebrow="History"
        title="Investigations"
        actions={
          <ButtonLink href="/investigations/new" variant="primary" icon={<Icon.Search size={15} />}>
            Check a website
          </ButtonLink>
        }
      >
        {invs.error ? (
          <ErrorState error={invs.error} />
        ) : !invs.data ? (
          <LoadingRows rows={2} />
        ) : invs.data.length === 0 ? (
          <EmptyState compact title="No investigations yet" description="Once a website is confirmed as yours, press “Check this site”." />
        ) : (
          <InvestigationTable items={invs.data} showProject={false} />
        )}
      </Section>
    </div>
  );
}
