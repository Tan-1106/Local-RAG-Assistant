# Legal Assistant Frontend

React + TypeScript frontend for authentication, session-based legal chat, source document viewing, and RAG document administration.

## Local development

```bash
npm install
npm run dev
```

Docker serves the API through the same-origin `/api` Nginx proxy. Set
`VITE_API_URL` only when running the frontend separately against another backend origin.

## Checks

```bash
npm run lint
npm test
npm run build
```

## Container

The production image builds static assets and serves them with Nginx:

```bash
docker compose build frontend
docker compose up frontend
```
