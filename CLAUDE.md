# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Lovable-connected project

This project is connected to [Lovable](https://lovable.dev) (see `AGENTS.md`, `.lovable/project.json`).
Never rewrite published git history — no force pushing, rebasing, amending, or squashing commits that
are already pushed; it rewrites history on Lovable's side and the user loses project history. Commits
pushed to the connected branch sync back into the Lovable editor, so keep the branch working.

## Commands

Package manager is **bun** (`bun.lock`, `bunfig.toml`). Use bun so the text lockfile stays consistent.

```bash
bun install
bun run dev          # vite dev server
bun run build        # production build (nitro, cloudflare target by default)
bun run build:dev    # build with development mode
bun run preview      # preview a production build
bun run lint         # eslint (prettier runs as an eslint rule — formatting errors fail lint)
bun run format       # prettier --write .
bunx tsc --noEmit    # typecheck (no script for it; tsconfig is noEmit)
```

No test framework is configured.

`bunfig.toml` sets `minimumReleaseAge = 86400` as a supply-chain guard (skips packages published in
the last 24h). Each entry in `minimumReleaseAgeExcludes` bypasses it for one package — confirm with
the user before adding any.

## Architecture

TanStack Start (SSR) + React 19 + Vite 8 + Tailwind v4 + shadcn/ui (new-york, `@/*` → `src/*`).

### Build config is preset-driven

`vite.config.ts` uses `@lovable.dev/vite-tanstack-config`, which already includes TanStack devtools,
`tanstackStart`, `viteReact`, `tailwindcss`, `tsConfigPaths`, `nitro`, VITE_* env injection, the `@`
alias, React/TanStack dedupe, error-logger plugins, and sandbox port/host detection. **Adding any of
those plugins manually breaks the app with duplicate plugins.** Extra config goes through
`defineConfig({ vite: { ... } })`.

### SSR error-handling chain

Three layers, all custom, all easy to break accidentally:

- `vite.config.ts` redirects TanStack Start's bundled server entry to `src/server.ts`.
- `src/server.ts` wraps `@tanstack/react-start/server-entry`. h3 swallows in-handler throws into a
  plain 500 JSON body (`{"unhandled":true,"message":"HTTPError"}`) that a try/catch never sees, so it
  inspects 5xx JSON responses and swaps in `renderErrorPage()` plus the error captured by
  `src/lib/error-capture.ts`.
- `src/start.ts` registers a request middleware that catches non-`statusCode` errors and returns the
  same error page.
- `src/routes/__root.tsx` supplies the client-side `errorComponent` / `notFoundComponent` and reports
  to Lovable via `src/lib/lovable-error-reporting.ts`.

### Routing

File-based; see `src/routes/README.md` for the full convention table. `src/routeTree.gen.ts` is
generated — never hand-edit. `__root.tsx` is the only layout root: it owns the `<html>` shell, head
metadata, and the `QueryClientProvider`, and must keep its `<Outlet />`. Do not create `src/pages/`
or `app/layout.tsx` (Next.js/Remix conventions that don't apply here). The router factory lives in
`src/router.tsx` and injects a `QueryClient` into route context.

### The app: a simulated swarm dashboard

The whole product is one route (`src/routes/index.tsx`) rendering a fake-live observability dashboard
for a three-agent Figma → Slack design-handoff swarm (detect → extract → post). **There is no
backend and no network calls — every event, spec, log line, and failure is scripted.**

`src/lib/swarm/use-run-engine.ts` is the core and is deliberately split in two halves:

- **Top half — pure reducer.** All state transitions over `RunState` (`src/lib/swarm/types.ts`),
  seeded by `createInitialState()` in `src/lib/swarm/initial-state.ts`.
- **Bottom half — timed choreography.** An async `runChoreography()` that dispatches actions with
  `sleep()` between them. A comment marks this as *the single seam that would be replaced by a real
  WebSocket/API driver*. Keep new logic on the correct side of that line: state shape changes go in
  the reducer, scripted timing goes in the choreography.

Choreography details worth knowing before editing:
- Cancellation uses `abortRef` with a `guard()` check after every `await`; new awaits need one too.
- `speedRef` divides every sleep (1x/2x toggle), so never call `setTimeout` directly for pacing.
- Two demo paths branch on `state.mode`: `"changes"` (full run) and `"no-changes"` (early exit).
- The run intentionally injects an HTTP 429 failure mid-extraction, matches it against a
  `learnedPatterns` entry, and self-heals — this is a scripted feature, not a bug.

Everything in `src/components/swarm/` is presentational and driven entirely by props off `RunState`;
they hold no state of their own except animation-local state (e.g. `GhostCursor`'s eased position).
Cursor coordinates (`CursorTarget.x/y`) are percentages (0–100) of the `BrowserView` viewport.

### Styling and theming

`src/styles.css` is Tailwind v4 (`@theme inline` + `@utility`), not a tailwind.config.js.

- Two themes: light on `:root`, dark under `.dark`, toggled by `index.tsx` and persisted to
  `localStorage["fds-theme"]` (defaults to dark).
- Tokens are HSL Figma UI values. **Never hardcode hex/rgb in components** — use the semantic tokens
  (`background`, `surface`, `surface-2/3`, `hairline`, `hairline-strong`, `selection`, `success`,
  `warning`, `error`).
- Agent identity brand colors (`--violet`, `--blue`, `--green`, `--red`, `--orange`) are reserved for
  agent cards, connectors, and handoff packets — not for chrome.
- Custom utilities live here too: `panel`, `panel-inset`, `hairline`, `glow-*`, `breathe`,
  `pulse-dot`, `ring-pulse`, `slide-in`, `shimmer`, `caret`, `healed-flash`.

## Lint notes

`eslint.config.js` bans importing `server-only` (a Next.js package): use a `*.server.ts` filename or
`@tanstack/react-start/server-only` instead. `@typescript-eslint/no-unused-vars` is off, and
`prettier` runs through eslint (printWidth 100, double quotes, semis, trailing commas).
