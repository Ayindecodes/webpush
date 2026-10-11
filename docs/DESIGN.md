# WEB X-RAY — UI/UX Design Brief (condensed, authoritative)

Premium, production-grade developer tool. Usability, clarity, precision, and
trust over decoration. The product should feel intelligent through what it
does, not through AI-themed visuals. Distinctive identity, not a generic SaaS
template.

## Hard constraints
- **Colour comes only from semantic tokens** (`web/src/styles/theme.css`); structural
  styling never references raw colours. The palette is now chosen (see Brand).
- No random gradients, glows, particles, rainbow buttons, heavy glassmorphism,
  card-everything layouts, excessive shadows/radii/whitespace, or purposeless
  illustrations.
- No fake analytics, fabricated activity, or nonfunctional controls. Progress
  reflects real backend state.
- Severity/status is never conveyed by color alone (icon + label too).

## Shell
Collapsible sidebar · top bar with breadcrumbs, project selection, account
controls · consistent grid · responsive desktop/tablet/mobile · compact.
Nav: Overview, Investigations, Findings, Journeys, Projects, Integrations,
Settings.

## Screens
- **Overview:** prominent "new investigation", URL entry with scope and
  authorization guidance, summary metrics (investigations, findings, coverage,
  verification), recent investigations (status, target, duration, findings),
  concise activity, real empty states. No meaningless stats or decorative
  charts.
- **Live investigation workspace:** latest browser viewport, current URL +
  title, current action + purpose, progress and page coverage, action/event
  timeline, routes and journeys, console errors / failed requests / issues,
  pause/resume/stop. Confirmed findings visibly distinct from in-progress.
- **Findings:** search, filter, sort, severity; confirmed defect vs warning vs
  informational; detail page with repro steps, screenshots, expected vs actual,
  DOM/layout/network/console, likely causes + supporting evidence +
  alternatives + confidence labels, generated Playwright test with execution
  status; generated ≠ passed/verified.
- **Reports:** executive summary, target/environment, pages + workflows,
  coverage/limitations, findings by severity, repro + evidence, root cause,
  generated tests + actual results, next actions; summary ⇄ evidence links.

## Components
Buttons/menus, forms/URL input, data tables, status indicators, severity
labels, metric summaries, tabs/filters, dialogs/confirmations, tooltips,
loading/error/empty/success states, evidence viewers, code blocks. Consistent
spacing, type, sizing, borders, radii. Focus states, keyboard navigation,
contrast, accessible labels.

## Typography
Deliberate scale: page title / section heading / body / label / metadata.
Monospace for technical text. Restrained weights, consistent line heights,
dense data easy to scan.

## Motion
Only for meaningful state change (progress, navigation, expanding details,
loading/completion, new timeline items). Subtle, fast, respects
`prefers-reduced-motion`, never interferes with controls.

## Definition of done
Credible, polished developer platform an engineering team could use daily:
consistent hierarchy, purposeful interactions, real functionality,
recognizable identity.

## Brand (chosen 2026-10-09, applied app-wide 2026-10-10)
- **Mark:** the Browse mark — a globe crossed by an address bar with a cursor; animates
  only while something is actually running.
- **Colour:** warm paper + ink, with Lens Teal as the single accent. "Paper" (light) is the
  default for the whole product; "Ink" is the dark variant. Marketing pages are always paper.
- **Components:** mono uppercase eyebrows, large tight headlines (`display`), pill buttons
  (ink = primary, paper = secondary), `card-ink` (ink border + offset shadow) for the one
  thing that matters most on a screen, `panel` (hairline card) for everything else.

## Voice (for a non-technical reader)
- Say what happened to a visitor, not what the engine measured: "the tap lands on the bar
  covering the button", not "probe intercepted by aside.help-bar".
- Lead every result with a one-sentence answer; put logs, selectors and raw evidence in a
  collapsed "Technical details" section.
- Names: Briefings, Investigations, Problems found, Journeys tested, Sites & projects.
  Confirmed problem / Possible problem / Note. "Test confirms it" / "Test passes" / "Fixed".
- Never imply something works that doesn't: unavailable features say "Coming later" with no
  connect button.
