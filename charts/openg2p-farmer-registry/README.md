# OAN Farmer Registry

OpenAgriNet (OAN) application developed in the OAN
repositories. This chart reuses the pinned OpenG2P registry platform.

| Source | GitHub repository |
| --- | --- |
| OAN application | [farmer-registry](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry) |
| OAN Helm sources | [oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/tree/main/charts/openg2p-farmer-registry) |
| OAN dashboard component | [farmer-registry-dashboard-api](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api) |
| OAN dashboard component | [oan_farmerregistry_dashboard](https://github.com/Centre-for-Open-Societal-Systems/oan_farmerregistry_dashboard) |

The Helm chart name retains its `openg2p-` prefix to preserve the existing release
and resource names. It does not identify the application source owner. The
OpenG2P dependency repository contains reused platform templates; application
images and provenance are configured by this OAN chart.

Use chart version **1.0.0-dev.5** and upgrade the current release in its current
namespace. Review private values, image digests and namespace-local Secret
references before applying changes. Optional dashboard components remain at
their explicit enablement settings; DA workloads await verified images/config.

See [included services](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/service-catalog.md),
[readiness](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/readiness.md) and
[Rancher instructions](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/rancher-dev.md).

Dev URLs use `<service>.development.oanstaging.com`. The environment-owned
wildcard DNS/TLS and `istio-system/development` Gateway must be prepared first.
See the service onboarding and enablement guide in `docs/service-onboarding.md`.

## Registrant authentication (Fayda through eSignet)

`registrantAuth` configures core's registrant authentication for the farmer
register from values: a post-install/post-upgrade hook writes the provider row
in this registry's database and the shared `oan-registry-intake` OIDC client in
eSignet's database, adding this registry's Staff API callback to the client's
redirect URIs. The client's RSA key is generated into the `registrantAuth.keySecret`
Secret the first time and reused afterwards; it never appears in values, logs or
Git. Set `esignetBaseUrl` (the public eSignet URL) and `callbackUrl`
(`https://<staff api host>/registrant-auth/callback`) per environment. The
register must have `requires_registrant_authentication` set in its metadata, which
the OAN seed does. See `docs/registry-esignet-onboarding.md`.

## DCI response signing

`dciSigning` gives the partner API a stable RSA key for signing its DCI search
responses, which consuming registries (Crop Sown's Farmer reference) pin. A
pre-install/pre-upgrade hook generates the key the first time into the
`dciSigning.keySecret` Secret (`signing.p12`, `password`, `public-key.pem`,
`kid`) and reuses it afterwards; the private key never appears in values, logs
or Git. The public key is printed in the hook log and published in ConfigMap
`<release>-dci-signing-public`. Mount the Secret on the partner API and set
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_PATH` (the bundle),
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_PASSWORD` (from the Secret) and
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_KID` (`dciSigning.kid`) through
`registry.partnerApi` per environment.

## Autoscaling with scale behaviour

`autoscaling.staffApi`, `autoscaling.partnerApi` and `autoscaling.celeryWorker` render
`autoscaling/v2` HorizontalPodAutoscalers for the registry subchart Deployments, with an
optional `behavior` block. The subchart's own HPA (`registry.<component>.autoscaling`) has no
`behavior`, and the Celery worker has no HPA at all. All three are off by default; rendering
fails if both HPAs are enabled for one component.

Throttle staff and partner API scale-up (for example +1 pod per minute). Each new pod runs
the farmer startup migration, which holds an exclusive lock on `g2p_register_farmers` for
about a minute with 1M farmers. The subchart still renders `replicas`, so keep
`registry.<component>.replicaCount` equal to `minReplicas`. CPU utilisation is measured
against the container's CPU request. An existing hand-made HPA with the same name must be
deleted before the upgrade. Example: `environments/prod-testing/values/farmer.yaml`.

## Database settings

With `dbSettings.enabled`, a post-install/post-upgrade hook Job connects as the registry's
own database user (no superuser) and, idempotently:

- builds the trigram GIN index `idx_g2p_register_farmers_search_text_trigram` on
  `g2p_register_farmers.search_text` with `CREATE INDEX CONCURRENTLY` (no table lock). An
  invalid index left by an interrupted build is dropped and rebuilt. The chart never drops
  the index. Staff portal search by name or Farmer ID (`search_text ILIKE '%term%'`) then
  reads the index; with 1M farmers it fell from ~1.4 s to ~0.1 s.
- sets `dbSettings.roleSettings` on the registry user (`ALTER ROLE CURRENT_USER SET`). They
  apply to new sessions; pooled connections pick them up when recycled. With the index, set
  `plan_cache_mode: force_custom_plan`. Otherwise the application's prepared statements
  switch to a generic plan that also uses the index for browse (an empty filter matches
  every row), which made browse about twice as slow.

The Job uses the `registry.dbSeed` image unless `dbSettings.image` is set.
