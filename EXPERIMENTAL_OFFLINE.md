# Experimental offline package (not a complete provisioner)

Install the separately named wheel, not the historical single-file plugin. Python
3.12 / Heat 27.0.0 / cloudsigma 3.0.0rc1 are the bounded qualification target.
No Heat entry point is auto-registered. Import
`cloudsigma_heat.experimental_offline.resource_mapping(registry=...)` with an
explicit `OfflineRegistry`; the returned mapping is caller-local. This does not
replace Heat's global environment, workers or existing plugin.

All 13 retained modules are namespaced. SDKCloud requires endpoint, username,
password, trusted_source SHA256 identity and offline_opt_in=True, plus an injected
BaseAdapter (production HTTPAdapter rejected). It has no default network adapter,
credential loader or environment transport. Trusted source is a caller assertion,
not authenticated authority. Lifecycle and cleanup grants must match it.
`early_admission.admit/store` require the same explicit endpoint. Only the narrow
reference template and one-server offline wire policy are supported; these tests
are not evidence of writable public cloud fields or live API semantics. Private
SDK response helpers are bounded to the declared SDK version.

The original cloudsigma_plugin.py and README remain byte-identical historical
compatibility artifacts, excluded from this wheel. Their effect-capable install
instructions are NOT experimental-package enablement instructions. All legacy
manager paths in the namespaced plugin refuse. Do not copy this package over a
production installation or infer a migration support guarantee.

CleanupOnly.binding is a read-only view of the fully validated original grant;
every access checks all fields and original identity, plus trusted source. Outbox
acknowledgment never closes the cleanup obligation or grants operational authority.
Tests use fake HTTP and local disposable SQLite only. No supervisor, fake cloud,
fixture DB, environment pins or evidence is included in the wheel. Unsigned
custody/keyed storage, process/owner death, power loss, distributed runtime and
operational authorization remain separate gates. No live enablement.
