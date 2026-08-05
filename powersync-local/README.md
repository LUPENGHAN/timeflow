# Local PowerSync verification

This directory is a local development stack. The source database is the Brew
PostgreSQL instance on the host; Docker runs PowerSync and its metadata
storage PostgreSQL.

## Start

```bash
cd powersync-local
cp powersync/docker/.env.example powersync/docker/.env
# Edit powersync/docker/.env with local-only credentials.
powersync docker start
powersync status
```

The service is available at `http://127.0.0.1:8080`. Stop it with:

```bash
powersync docker stop
```

`powersync/docker/.env` contains local source and storage credentials and must
not be committed. Start from the tracked `.env.example`; never put real
credentials in that template. The sync rules currently subscribe only to
`user_id = 'default_user'` in `schedules`.
