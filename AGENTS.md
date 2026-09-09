# Personal recipe system

Keep this private, static, simple, and maintainable. Do not deploy, push, or add paid infrastructure without explicit authorization.

## Architecture
COLLECT → immutable raw JSONL → NORMALIZE → DEDUPLICATE → MATCH → PUBLISH.
Collection is independent of preferences and the website. JSONL is the durable interchange; configuration is YAML. Unknown facts remain null. Preserve source URL, license, revision, raw ID, and retrieval time on derived records. Never fabricate products, stock, nutrition, licenses, or completeness.

## Ownership
The coordinator owns shared contracts/configuration, normalization, matching, central merges and validation. Collection agents own only assigned sources and uniquely named shards/checkpoints. Never concurrently append to shared JSONL or modify another agent's state. Atomic replacement, stable IDs, resumable item accounting, explicit failures and structured logs are required. Parallel collection starts only after the small end-to-end check passes.

## Determinism and presentation
Explicit ingredient aliases and reproducible code determine normalization and scores. Preserve original source measurements separately. Publish metric g/kg/mL/L/°C; no tsp, tbsp, teaspoon or tablespoon output. Do not infer volume-to-mass conversion without evidence. Keep personal notes, rating, cooked/favorite status separate from source records. Availability must cite actual products, source URLs, store specificity and observation time. Public Food Lion catalog evidence establishes ingredient compatibility and is sufficient for recommendations; exact local stock is never an approval gate. Keep the distinction from verified local stock internally. Unknown is not unavailable. Keep blocked snapshots immutable and catalog evidence separate.

## Access and time
Respect robots, authentication, CAPTCHAs, access controls and rate limits. Do not bypass protections. Persist unresolved store context and never silently switch stores. User-facing timestamps use America/New_York ISO 8601 offsets. Historical snapshots are immutable.

## Verification
Run formatting, linting, meaningful tests and static build after meaningful changes. Test conversions, schemas, aliases, deterministic ranking, coverage, resume, idempotent merge, provenance and published unit constraints. Report incomplete discovery and explicit failures honestly. Use Git for changes; preserve useful existing work.

## Product boundary
Default browsing prioritizes practical everyday meals. Missing active time, nutrition, equipment or difficulty must not automatically disqualify a recipe. Keep collection failures, shard terminology and completeness metrics in developer documentation, not cooking pages. Use Food Lion Yes / Probably / Unknown and “Local stock may vary.”
