# paymentops-hackathon (Hetzner `hetzner-dr`)

Isolated deployment of the `paymentops-amd` application (Evolus/AMD investigator). Shares
nothing with the business app or other namespaces: separate namespace, database, PVC, secrets,
selectors, and hostname.

- Namespace: `paymentops-hackathon`
- Layout: `base/` (shared) + `overlays/dr/` (cluster overlay, immutable image tags)
- Flux: `clusters/hetzner-dr/flux-system/paymentops-hackathon.yaml`
- Exposure: shared Envoy `public-gateway` + Cloudflare Tunnel (HTTPRoute added in Step 6)
- Storage: `local-path` PVC (2 Gi)
- No worker/Redis/address-structuring (not required for the investigation demo)

Full instructions, verification, and rollback: `paymentops-amd/docs/PHASE2_DEPLOY.md`.
