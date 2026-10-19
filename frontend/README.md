# Agrivanta frontend

Vite + React 18 + TypeScript scaffold for the Agrivanta web application.

This package proves the frontend toolchain (build, lint, formatting, and
tests) works end to end. It intentionally contains **no** farm-domain
components, routing, global state management, or API calls — those arrive in
later tasks.

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
├── tsconfig.json       # TypeScript (strict) project config
├── vite.config.ts      # Vite + Vitest configuration
└── src/
    ├── App.tsx         # Minimal placeholder component
    ├── App.test.tsx    # Component test (React Testing Library)
    ├── main.tsx        # React entry point
    └── setupTests.ts   # jest-dom matcher registration
```
