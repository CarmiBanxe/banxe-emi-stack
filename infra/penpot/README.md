# Penpot — Self-Hosted Design Tool

Self-hosted deployment of [Penpot](https://penpot.app) for BANXE Design-to-Code Pipeline (IL-D2C-01).

## Quick Start

```bash
cd infra/penpot
docker compose up -d
```

Services start at:
- **Penpot UI**: http://localhost:9001
- **Mailcatcher** (SMTP): http://localhost:1080

## First Run

1. Open http://localhost:9001
2. Click **Create account** (email verification is disabled in dev mode)
3. Create a new team: **BANXE Design System**
4. Import existing Figma files via **Penpot Figma Plugin**

## Access Token (for API/MCP)

1. Go to **Profile → Access Tokens**
2. Create a new token with name `banxe-pipeline`
3. Copy the token and add to `.env`:
   ```
   PENPOT_TOKEN=your_token_here
   PENPOT_BASE_URL=http://localhost:9001
   PENPOT_BANXE_FILE_ID=<file-id-from-url>
   ```

## Architecture

```
penpot-frontend  :9001   (nginx → serves React SPA)
penpot-backend   :6060   (Clojure API server)
penpot-exporter  :6061   (Headless Chrome for exports)
penpot_db        :5432   (PostgreSQL 16)
penpot_redis     :6379   (Redis 7)
penpot_smtp      :1025   (Mailcatcher SMTP)
```

## Volumes

| Volume | Purpose |
|--------|---------|
| `penpot_assets` | Uploaded files, images, exported SVGs |
| `penpot_db_data` | PostgreSQL data |
| `penpot_redis_data` | Redis persistence |

## Stop / Restart

```bash
docker compose -f infra/penpot/docker-compose.yml down
docker compose -f infra/penpot/docker-compose.yml up -d
```

## Data Backup

```bash
docker exec penpot_db pg_dump -U penpot penpot > backup-$(date +%Y%m%d).sql
```

## Integration with Design Pipeline

The `PenpotMCPClient` at `services/design_pipeline/penpot_client.py` connects to Penpot REST API using the access token. Configure via:

```env
PENPOT_BASE_URL=http://localhost:9001
PENPOT_TOKEN=<your-access-token>
PENPOT_BANXE_FILE_ID=<file-uuid>
```

## Security Notes

- **Dev only**: `disable-email-verification` flag is set — remove for production
- Access tokens are scoped per-user — use a service account for CI
- Penpot data contains design IP — restrict network access in production
- PostgreSQL password in `docker-compose.yml` is for local dev only — use secrets in prod
