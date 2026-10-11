// Mirrors backend/webxray/schemas.py. Keep in sync when the API changes.

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type Classification = "confirmed_defect" | "warning" | "observation";
export type InvestigationStatus =
  | "queued"
  | "running"
  | "paused"
  | "awaiting_human"
  | "completed"
  | "failed"
  | "stopped"
  | "blocked";
export type ViewportName = "desktop" | "tablet" | "mobile";

export interface User {
  id: string;
  email: string;
  display_name: string;
  organization_id: string;
  organization_name: string;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  environment_count: number;
  investigation_count: number;
}

export interface Environment {
  id: string;
  project_id: string;
  origin: string;
  label: string;
  verification_status: "pending" | "verified";
  verification_method: string | null;
  verification_token: string;
  verified_at: string | null;
  created_at: string;
}

export interface VerificationResult {
  verified: boolean;
  method: string | null;
  detail: string;
  environment: Environment;
}

export interface VerificationInstructions {
  http_file_url: string;
  http_file_content: string;
  dns_txt_name: string;
  dns_txt_value: string;
}

export interface Credential {
  id: string;
  environment_id: string;
  label: string;
  source: "user_supplied" | "generated";
  username_hint: string;
  lifecycle_state: string;
  created_at: string;
}

export interface InvestigationConfig {
  viewports: ViewportName[];
  max_pages: number;
  max_depth: number;
  max_duration_s: number;
  repeat_failed_runs: number;
  start_path: string;
  include_paths: string[];
  exclude_paths: string[];
  allow_registration: boolean;
  allow_order_submission: boolean;
}

export interface Phase {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "skipped" | "failed" | "blocked";
  detail: string | null;
  started_at?: string;
  finished_at?: string;
}

export interface InvestigationSummary {
  final_status?: string;
  pages?: { public: number; authenticated: number };
  crawl_notes?: string[];
  skipped_links?: Record<string, number>;
  auth?: { status: string; detail: string; onboarding?: { status?: string; steps?: string[] }; login_verified?: boolean };
  features?: Record<string, number>;
  findings?: { total: number; by_severity: Record<string, number>; by_classification: Record<string, number> };
  tests?: { finding_id: string; test_id: string; outcome: string }[];
  limitations?: string[];
  egress_blocked?: number;
  viewports?: string[];
}

export interface Investigation {
  id: string;
  project_id: string;
  project_name: string | null;
  environment_id: string;
  origin: string | null;
  mode: "autonomous" | "authenticated";
  goal: string;
  config: InvestigationConfig;
  status: InvestigationStatus;
  phase: string;
  phases: Phase[];
  requested_control: "none" | "pause" | "stop";
  blocked_reason: string | null;
  error: string | null;
  current_url: string | null;
  current_title: string | null;
  current_action: string | null;
  latest_screenshot_id: string | null;
  auth_state: string;
  summary: InvestigationSummary;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  finding_counts: Partial<Record<Classification, number>>;
  page_count: number;
}

export interface InvestigationEvent {
  seq: number;
  ts: string;
  kind: string;
  level: "info" | "warn" | "error";
  message: string;
  data: Record<string, unknown>;
  browser_run_id: string | null;
  page_url: string | null;
  evidence_id: string | null;
}

export interface PageRecord {
  id: string;
  url: string;
  title: string;
  status_code: number | null;
  depth: number;
  auth_state: string;
  classification: string;
  discovered_from: string | null;
  inventory: {
    h1?: string[];
    forms?: { action: string; method: string; fields: { type: string; label: string; required: boolean }[]; submits: string[] }[];
    buttons?: string[];
    nav_links?: string[];
    link_count?: number;
    internal_links?: string[];
    alerts?: string[];
  };
  screenshot_id: string | null;
  console_error_count: number;
  failed_request_count: number;
  load_ms: number | null;
}

export interface Feature {
  id: string;
  key: string;
  name: string;
  status: "discovered" | "tested" | "untested" | "needs_permission" | "needs_human" | "inaccessible";
  page_url: string | null;
  details: Record<string, unknown>;
}

export interface RunStep {
  key: string;
  name: string;
  expected: string;
  status: "passed" | "failed" | "skipped" | "error" | "pending";
  observed: string;
  started_at: number;
  ended_at: number;
  evidence: Record<string, string>;
  data: Record<string, unknown>;
  signals: Record<string, number>;
}

export interface BrowserRun {
  id: string;
  journey_id: string;
  viewport_name: ViewportName;
  viewport: { label: string; width: number; height: number };
  attempt: number;
  status: "running" | "passed" | "failed" | "error" | "blocked";
  failure_step: string | null;
  steps: RunStep[];
  started_at: string;
  finished_at: string | null;
}

export interface Journey {
  id: string;
  investigation_id: string;
  key: string;
  name: string;
  status: "planned" | "passed" | "failed" | "partial" | "skipped";
  definition: Record<string, unknown>;
  created_at: string;
  runs: BrowserRun[];
  origin: string | null;
  project_name: string | null;
}

export interface EvidenceRef {
  evidence_id: string;
  role: string;
}

export interface Hypothesis {
  key: string;
  title: string;
  status: "supported" | "not_supported" | "inconclusive";
  strength: "strong" | "moderate" | "limited";
  rationale: string;
  evidence: EvidenceRef[];
}

export interface Finding {
  id: string;
  investigation_id: string;
  project_id: string;
  kind: string;
  classification: Classification;
  severity: Severity;
  title: string;
  summary: string;
  expected: string | null;
  observed: string | null;
  page_url: string | null;
  viewport_name: string | null;
  reproduction: {
    status?: string;
    failed_runs?: number;
    total_runs?: number;
    passing_viewports?: string[];
    failing_viewports?: string[];
    run_ids?: string[];
    pages?: string[];
    test?: { test_id: string; run_id: string; outcome: string; playwright_status: string | null };
    fixed_at?: string;
  };
  hypotheses: Hypothesis[];
  evidence_strength: "strong" | "moderate" | "limited";
  steps_to_reproduce: string[];
  recommendation: string | null;
  occurrences: number;
  first_event_seq: number | null;
  created_at: string;
  origin: string | null;
  test_status: string | null;
  test_id: string | null;
}

export interface Evidence {
  id: string;
  kind: string;
  label: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  meta: Record<string, unknown>;
  redactions: string[];
  event_seq: number | null;
  browser_run_id: string | null;
  created_at: string;
  role: string | null;
  url: string;
  url_expires_at: number;
}

export interface TestRun {
  id: string;
  test_id: string;
  status: "queued" | "running" | "finished" | "error";
  playwright_status: string | null;
  outcome: "reproduced" | "not_reproduced" | "inconclusive" | null;
  exit_code: number | null;
  duration_ms: number | null;
  error_message: string | null;
  output_evidence_id: string | null;
  source_sha256: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ReproTest {
  id: string;
  finding_id: string;
  investigation_id: string;
  framework: string;
  filename: string;
  source: string;
  sha256: string;
  verification_status: "generated" | "reproduced" | "not_reproduced" | "inconclusive";
  created_at: string;
  runs: TestRun[];
}

export interface Overview {
  projects: number;
  environments: number;
  investigations: { total: number; by_status: Record<string, number> };
  findings: { total: number; by_severity: Record<string, number>; by_classification: Record<string, number> };
  tests: { total: number; by_status: Record<string, number> };
  pages_discovered: number;
  features: Record<string, number>;
  journey_runs: Record<string, number>;
}

// --------------------------------------------------------------------------- briefings

export type BriefingStatus = "queued" | "running" | "completed" | "failed" | "blocked";
export type BriefingAuthStatus =
  | "not_requested"
  | "pending"
  | "authenticated"
  | "failed"
  | "blocked_captcha"
  | "mfa_required"
  | "verification_required"
  | "no_login_form";

export interface BriefingResult {
  name: string;
  name_source: string;
  headline: string | null;
  description: string | null;
  description_source: string | null;
  summary: string;
  site_type: { key: string; label: string; confidence: "high" | "medium" | "low"; reasons: string[] };
  other_types: { key: string; label: string; reasons: string[] }[];
  capabilities: { key: string; label: string; detail: string; pages: string[]; signed_in_only?: boolean }[];
  sections: { label: string; url: string }[];
  organization: {
    name: string | null;
    copyright: string | null;
    emails: string[];
    phones: string[];
    address: string | null;
    social: { network: string; url: string }[];
  };
  prices: { text: string; page: string }[];
  technology: { name: string; evidence: string }[];
  languages: string[];
  question: string | null;
  answer: { text: string; page: string }[];
  answer_pages?: { page: string; title: string }[];
  pages: { url: string; path: string; title: string; status: number | null; kind: string; description: string | null; signed_in?: boolean }[];
  sign_in: { status: BriefingAuthStatus; detail: string | null; as: string | null; pages: string[] } | null;
  notes: string[];
  skipped: { url: string; reason: string }[];
  stats: { pages_read: number; duration_ms: number };
}

export interface Briefing {
  id: string;
  url: string;
  origin: string;
  question: string;
  status: BriefingStatus;
  current_action: string | null;
  current_url: string | null;
  steps: { ts: string; message: string }[];
  shots: { url: string; page_url: string | null; title: string | null; sha256: string; signed_in: boolean }[];
  result: BriefingResult | Record<string, never>;
  error: string | null;
  login_url: string | null;
  credential_hint: string | null;
  auth_status: BriefingAuthStatus;
  auth_detail: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
