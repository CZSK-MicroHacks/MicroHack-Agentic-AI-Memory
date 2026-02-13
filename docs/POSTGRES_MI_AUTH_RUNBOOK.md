# PostgreSQL Managed Identity Auth Runbook

This runbook documents how to use Microsoft Entra / Managed Identity authentication for PostgreSQL in this project.

## 1) Application settings

Backend uses:

- `PG_AUTH_MODE=managed_identity`
- `PG_AAD_PRINCIPAL_NAME=<managed-identity-name>`
- `PG_HOST`, `PG_PORT`, `PG_DATABASE`
- `AZURE_CLIENT_ID` (for user-assigned managed identity)

In managed identity mode, the backend gets token scope:

- `https://ossrdbms-aad.database.windows.net/.default`

and passes the token as PostgreSQL password.

## 2) PostgreSQL server prerequisites

Ensure on Flexible Server:

- Microsoft Entra auth enabled
- Managed identity (or group) configured for login
- Password auth can remain enabled during transition; disable after cutover

## 3) Create DB principal for the managed identity

Connect as Entra admin to the `postgres` database and run:

```sql
select * from pgaadauth_create_principal('<identity_name>', false, false);
```

`<identity_name>` must match `PG_AAD_PRINCIPAL_NAME`.

## 4) Grant least-privilege permissions on `appdb`

Example baseline (adjust as needed):

```sql
GRANT CONNECT ON DATABASE appdb TO "<identity_name>";
\c appdb
GRANT USAGE ON SCHEMA public TO "<identity_name>";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE conversation_memory TO "<identity_name>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<identity_name>";
```

## 5) Validation

- Deploy infra changes and backend app
- Verify backend starts without `PG_PASSWORD`
- Test `/memories` CRUD + `/memories/search`
- Inspect Container App logs for authentication errors

## 6) Hardening step

After successful validation, disable password auth in Terraform:

- `postgres_password_auth_enabled = false`
