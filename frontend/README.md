# Secure Enterprise RAG — Frontend SPA

Production Single-Page Application (SPA) for **Secure Enterprise RAG**, constructed using React 19, TypeScript, Vite, and Tailwind CSS.

## Key Capabilities & Components

- **Authentication**: JWT session management with tab-scoped fallback storage (`AuthContext`).
- **Document Management**: Role-aware document listing, streaming PDF upload modal, and document deletion.
- **Permission Management**: Intra-tenant explicit permission grant/revoke modal (`PermissionManagerModal`) for sharing restricted documents with specific users.
- **Grounded Chat & Citations**: Interactive RAG query drawer with server-mapped citation details (`[DOC-N]`) and real-time execution diagnostics (`DiagnosticsPanel`).

## Operational Scripts

* `npm run dev`: Launch Vite local development server on `http://localhost:5173` (proxies `/api` requests to backend).
* `npm run test`: Execute Vitest component & API client unit test suite.
* `npm run build`: Typecheck with `tsc` and assemble production bundle in `dist/`.
* `npm run preview`: Serve production bundle locally for previewing.
