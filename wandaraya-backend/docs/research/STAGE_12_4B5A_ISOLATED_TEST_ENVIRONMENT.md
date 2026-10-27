# Climate integration test environment

`docker-compose.climate-integration-test.yml` defines a dedicated Docker-only
PostgreSQL service, database, role and volume. It publishes no ports and uses
`network_mode: none`. It does not reference the active database bind mount or
the backup restore-test container. A unique test-only password must be supplied
via `CLIMATE_TEST_DB_PASSWORD`; do not put a production credential in the file.

The dedicated container and its new volume were created for this task. Inspection
confirmed `network_mode: none`, no published ports, and the only data mount is
`wandaraya_climate_integration_test_data:/var/lib/postgresql/data`. A read-only
query confirmed the database and role are both `wandaraya_climate_integration_test`
and `climate_integration_test`, respectively, and the climate observation table
does not exist yet. The container was accepting connections at verification.
The existing production and restore-test containers were not modified.
Do not remove or reuse this volume without identifying its contents and obtaining
authorization.

The historical transaction executor and real integration test runner are still
unimplemented. Do not consider this configuration evidence that insertion,
rollback, resumption, idempotency or production collation checks have passed.
Do not use the production database as a test fallback. Do not change or delete
the restore-test database or its volume.
