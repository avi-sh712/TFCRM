# TalentForge Deployment Runbook

This runbook keeps secrets out of Git and uses the lowest-cost practical stack for a hackathon demo.

## Recommended Hosting

- Frontend: Vercel Hobby. Set `VITE_API_URL` to the public backend URL.
- Backend: Render Free for lowest cost, or Railway Free trial/Hobby if you need fewer cold starts.
- Database: Neon Free PostgreSQL with `pgvector`.
- Email: Resend developer tier.
- AI: OpenAI API key stored only in backend host secrets.

Render Free can sleep when inactive, so the first request may be slow. For judging demos, open the app a few minutes before presenting or use Railway Hobby/trial.

## Secret Rules

- Do not commit `.env`, `.env.production`, Vercel secrets, Render secrets, Railway variables, database URLs, API keys, JWT secrets, webhook secrets, or Resend keys.
- Keep frontend variables limited to public values. `VITE_API_URL` is public by design.
- Store all backend secrets only in Render/Railway/GitHub secret settings.
- Use the read-only `app_readonly` database user only for MCP. Use the normal app database URL only for the FastAPI app.

## Backend on Render

1. Push this repository to GitHub.
2. In Render, create a new Blueprint or Web Service from the repository.
3. Use the included `render.yaml`.
4. Set these environment variables in Render:

```text
DATABASE_URL=postgresql+asyncpg://...
FRONTEND_URL=https://your-vercel-app.vercel.app
TALENTFORGE_PRODUCTION_FRONTEND_ORIGIN=https://your-vercel-app.vercel.app
OPENAI_API_KEY=...
POSTGRES_MCP_URL=https://your-mcp-host.example.com/mcp
POSTGRES_MCP_AUTH_TOKEN=...
RESEND_API_KEY=...
RESEND_FROM_EMAIL=Your Team <verified@yourdomain.com>
ADMIN_EMAIL=your-admin-email@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-strong-admin-password
```

Render can generate `JWT_SECRET_KEY` and `WEBHOOK_SECRET_TOKEN` from `render.yaml`. If your service was created manually, generate both yourself with at least 32 random bytes.

The Docker container runs `alembic upgrade head` before starting the API, so schema changes are applied during deploy.

## Frontend on Vercel

1. Import the GitHub repository in Vercel.
2. Set the root directory to `frontend`.
3. Set build command to `npm run build`.
4. Set output directory to `dist`.
5. Add this environment variable:

```text
VITE_API_URL=https://your-backend-host.example.com
```

Redeploy the frontend after changing `VITE_API_URL`, because Vite bakes that value into the build.

## Neon Database

1. Create a Neon project.
2. Enable the `vector` extension.
3. Use the pooled connection string for the app if Neon recommends it for your plan.
4. Keep the MCP read-only user separate:

```sql
CREATE USER app_readonly WITH PASSWORD 'replace-with-strong-password';
GRANT CONNECT ON DATABASE talentforge TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_readonly;
```

## GitHub Actions

The workflow validates every push and pull request:

- installs backend dependencies
- runs `pytest tests/`
- builds the Docker image locally
- optionally pushes the Docker image if registry secrets exist
- optionally calls a Render deploy hook if `RENDER_DEPLOY_HOOK_URL` exists

Add these GitHub repository secrets only if you need the optional steps:

```text
DOCKER_REGISTRY
DOCKER_USERNAME
DOCKER_PASSWORD
DOCKER_IMAGE_NAME
RENDER_DEPLOY_HOOK_URL
```

Vercel and Render can also auto-deploy directly from GitHub, so the workflow is intentionally safe when these secrets are missing.

## Production Checklist

- `DATABASE_URL` points to Neon production.
- `FRONTEND_URL` and `TALENTFORGE_PRODUCTION_FRONTEND_ORIGIN` exactly match the Vercel URL.
- `JWT_SECRET_KEY` is at least 32 random bytes and not reused from local development.
- `OPENAI_API_KEY` is set only on the backend host.
- `RESEND_FROM_EMAIL` uses a verified sender before sending real customer email.
- `POSTGRES_MCP_*` points to a read-only MCP service.
- GitHub repository has branch protection on `main`.
- GitHub Actions passes before merging.
