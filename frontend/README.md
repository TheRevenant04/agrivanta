# Agrivanta frontend

The Agrivanta frontend is a Vite + React 18 + TypeScript application. It
includes authentication and protected routes, a shared application shell,
farm and crop-cycle setup, activity planning, inventory, expenses, payments,
harvests, sales, unit conversions, a dashboard, and predefined reports.

All backend access goes through the typed services layer in `src/services/`.
The app can use browser-based mock services or an HTTP client that calls the
Django API.

## Environment configuration

Copy [`.env.example`](.env.example) to `.env` and adjust as
needed. Vite only exposes variables prefixed with `VITE_`.

| Variable            | Default | Purpose                                                                            |
| ------------------- | ------- | ---------------------------------------------------------------------------------- |
| `VITE_API_CLIENT`   | `mock`  | Selects the services implementation. Unset (or anything but `http`) uses the mock. |
| `VITE_API_BASE_URL` | —       | Base URL prepended to every HTTP request; required when `VITE_API_CLIENT=http`.    |

With the default configuration (`VITE_API_CLIENT` unset), the app uses mock
services and can run without a backend. The mock supports the frontend service
contract with in-memory seed data.

Seed credentials for the mock:

| Email                    | Password      | Role      |
| ------------------------ | ------------- | --------- |
| `owner@agrivanta.test`   | `password123` | `owner`   |
| `manager@agrivanta.test` | `password123` | `manager` |

## Services layer

All backend access goes through the `AgrivantaServices` contract in
`src/services/types.ts`; no component, page, hook, or store calls `fetch`,
`XMLHttpRequest`, or `axios` directly (enforced by ESLint and a test). The UI
consumes it via `useServices()` from `src/services/servicesContext.ts`.

- `src/services/mockServices.ts` — in-memory implementation with seed data.
- `src/services/httpServices.ts` — thin `fetch` wrapper, base URL from
  `VITE_API_BASE_URL`, bearer token header from the stored session.
- `src/services/createServices.ts` — selects the implementation from
  `VITE_API_CLIENT`.

## Requirements

- **Node.js 24.x** — pinned in both [`frontend/.nvmrc`](.nvmrc) and the
  `engines` field of [`frontend/package.json`](package.json).
- npm (bundled with Node.js).

Use `nvm use` from `frontend/` to switch to the pinned Node version. The
package sets `engine-strict=true` in [`frontend/.npmrc`](.npmrc), so
installing with a different Node major fails loudly with an `EBADENGINE`
error instead of silently continuing.

## Install

Run from `frontend/`:

```bash
npm ci
```

`npm ci` installs exactly the versions recorded in the committed
`package-lock.json` and creates `frontend/node_modules/`. (Use
`npm install` only when intentionally changing dependencies, so the
lockfile stays in sync.)

## Commands

Run all commands from `frontend/`:

| Command                | What it does                                                                |
| ---------------------- | --------------------------------------------------------------------------- |
| `npm run dev`          | Start the Vite dev server with hot module replacement                       |
| `npm run build`        | Type-check with `tsc` and emit a production build to `dist/`                |
| `npm run preview`      | Serve the built `dist/` output locally                                      |
| `npm run lint`         | Run ESLint over the project (exits non-zero on errors/warnings)             |
| `npm run format`       | Rewrite files with Prettier                                                 |
| `npm run format:check` | Check Prettier formatting without writing (exits non-zero on drift)         |
| `npm run test`         | Run Vitest once, in non-watch mode (CI-friendly, exits non-zero on failure) |

### Copy-paste from a fresh clone

```bash
npm ci
npm run lint
npm run format:check
npm run test
npm run build
```

The build type-checks TypeScript and emits `dist/index.html` plus hashed
assets under `dist/assets/`.

## Testing

Tests use [Vitest](https://vitest.dev/) with a jsdom environment,
[React Testing Library](https://testing-library.com/docs/react-testing-library/intro/),
and `@testing-library/jest-dom` matchers (registered in
`src/setupTests.ts`). `npm run test` performs a single run and never opens a
watcher, so it is safe to use in CI.

## Application areas

The router in `src/app/AppRoutes.tsx` provides authenticated screens for the
dashboard, farm, fields, crops, varieties, units, conversions, crop cycles,
activities and activity templates, inventory, expenses, payments, harvests,
and sales. Login and registration are available outside the protected
application shell.

The dashboard defaults to the current year to date. A saved reporting period
or season selects its date range; trend points are separate KPI requests for
sub-periods, not client-calculated financial totals. Reports use the same
period or season selector and apply the chosen filters when requested. CSV,
Excel, and PDF downloads use the backend export endpoints. In mock mode the
dashboard and reports show empty data and exports require the HTTP API.

Frontend tests live alongside the components and pages they cover. Vitest is
configured with jsdom and React Testing Library; `npm run test` performs one
non-watch run.
