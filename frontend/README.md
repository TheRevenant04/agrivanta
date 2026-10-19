# Agrivanta frontend

Vite + React 18 + TypeScript scaffold for the Agrivanta web application.

This package proves the frontend toolchain (build, lint, formatting, and
tests) works end to end. It ships a single typed **services layer**
(`src/services/`) that is the only code allowed to talk to the backend, with
two interchangeable implementations of the same contract — a **mock** (the
default, needs no server) and an **HTTP** client — plus a React Router based
login / register / logout flow and a route guard.

## Environment configuration

Copy [`frontend/.env.example`](.env.example) to `frontend/.env` and adjust as
needed. Vite only exposes variables prefixed with `VITE_`.

| Variable            | Default | Purpose                                                                            |
| ------------------- | ------- | ---------------------------------------------------------------------------------- |
| `VITE_API_CLIENT`   | `mock`  | Selects the services implementation. Unset (or anything but `http`) uses the mock. |
| `VITE_API_BASE_URL` | —       | Base URL prepended to every HTTP request; required when `VITE_API_CLIENT=http`.    |

With the default configuration (`VITE_API_CLIENT` unset) the whole app runs
with no backend: `npm run dev` boots straight to the login page and the mock
implements login, register, logout, and `me`.

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

A green run ends with ESLint reporting nothing, Prettier reporting all files
use its code style, Vitest reporting at least one passing test, and Vite
emitting `dist/index.html` plus hashed assets under `dist/assets/`.

## Testing

Tests use [Vitest](https://vitest.dev/) with a jsdom environment,
[React Testing Library](https://testing-library.com/docs/react-testing-library/intro/),
and `@testing-library/jest-dom` matchers (registered in
`src/setupTests.ts`). `npm run test` performs a single run and never opens a
watcher, so it is safe to use in CI.

## Project layout

```text
frontend/
├── index.html          # Vite HTML entry point
├── eslint.config.js    # ESLint flat config
├── .prettierrc.json    # Prettier options
├── .env.example        # Documented environment variables
├── tsconfig.json       # TypeScript (strict) project config
├── vite.config.ts      # Vite + Vitest configuration
└── src/
    ├── App.tsx         # Providers + router wiring
    ├── App.test.tsx    # Mock-mode boot test (renders the login page)
    ├── main.tsx        # React entry point
    ├── setupTests.ts   # jest-dom matcher registration
    ├── app/
    │   ├── AppProviders.tsx   # Composes auth state + services layer
    │   └── AppRoutes.tsx      # Route table and protected landing route
    ├── auth/
    │   ├── AuthProvider.tsx   # Session state, sign in/out, 401 handling
    │   ├── AuthBootstrap.tsx  # Revalidates a stored token via me()
    │   └── authContext.ts     # Context + useAuth hook
    ├── components/
    │   └── ProtectedRoute.tsx # Redirects unauthenticated visitors
    ├── lib/
    │   └── errors.ts          # Turns thrown values into messages
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── RegisterPage.tsx
    │   └── DashboardPage.tsx  # Protected landing route
    └── services/
        ├── types.ts           # AgrivantaServices contract and errors
        ├── sessionStore.ts    # Refresh-surviving token storage
        ├── mockServices.ts    # In-memory backend
        ├── httpServices.ts    # fetch-based backend
        ├── createServices.ts  # VITE_API_CLIENT factory
        ├── servicesContext.ts # Context + useServices hook
        └── ServicesProvider.tsx # Wires services + 401 handling
```
