# Parser recovery audit

The immutable baseline is `state/recipes/recovery/baseline.jsonl`: all 934 original failed candidate files, with shard owner, original error, path and pinned revision. `breakdown.json` groups all baseline candidates by reproducible structural root cause. `outcomes.jsonl` keeps individual classifications and evidence; `summary.json` contains final accounting. These are candidate-file counts, not recipe counts: one structured file may contain several recipes.

Git tree enumeration uses NUL-delimited paths, preserving quotes, tabs and embedded newlines. The previously omitted quoted Brooke recipe was appended to a new independent shard without changing existing ownership.

The generalized adapters add:

- alternate recipe/ingredient/method headings, Setext titles, ingredient tables and unmeasured Markdown bullet lists;
- measured ingredient runs in archived text, wrapped ingredient lines, explicit nutrition and review/footer boundaries, and source URL title fallback marked as such;
- explicitly named HTML ingredient/instruction components alongside existing JSON-LD and microdata support;
- CSV recipe exports and explicit OCR `analyzeResult.content` (OCR uncertainty remains recorded).

No absent ingredient quantity, active cooking time, nutrition or instruction is supplied. Multi-card text archives without a reliable title-aware partition remain unsupported instead of combining dishes. Navigation-only text and incomplete ingredient-only drafts are not successful recipes. Structured JSON arrays continue to yield separate recipes. ZIP recipe members are enumerated without extracting files onto disk: JSON, Markdown, CSV, HTML export cards, gzip Paprika records and one nested ZIP level. Limits are 2,000 entries, 16 MiB per member and 64 MiB declared expansion per container. Unsafe paths, encrypted members and size-limit failures are explicit failures. Individual member paths and failures remain in checkpoints. Cookn DSV tables use their explicit header columns and recipe/food/unit IDs for reproducible joins; original recipe table rows are retained in a recipe-only projection. The nine Mealie backup fixtures contain either an empty recipe table or entirely randomized ten-letter cooking text, matching the repository’s published anonymizer. Their 1,021 recipe-shaped rows are not actual recipes; `backup-audit.json` records inspection of all 24,156 nonempty recipe text fields and the pinned anonymizer URL. They are correctly excluded, and account metadata is not ingested. Archive records retain member path, member position and actual member text separately from the outer Git path.

Run an affected-item-only retry for a shard whose owner is idle:

```sh
.venv/bin/python -m recipe_system.recovery retry --agent recipe-agent-01
```

The retry tests only baseline failures against the generalized parser and processes only accepted items. It does not retry unmodified successes or unrelated failures. The existing shard lock and atomic write/checkpoint sequence still apply. Per-agent reports keep each improvement's counts. Original failure history remains in the checkpoint. Rebuild the global audit after all owners have finished:

```sh
.venv/bin/python -m recipe_system.recovery audit
```

Classification is deliberately conservative. Only explicit heading-only TODOs, pointer-only records or synthetic test-fixture markers receive `NOT_A_RECIPE_SOURCE`. A cached access-denied response receives `BLOCKED`; this does not authorize another request or an access-control workaround. Explicit recipe-component evidence that cannot yield both ingredient and instruction sections remains `LEGITIMATE_RECIPE_FAILURE`. Ambiguous narrative, index pages, incomplete caches and HTML adapter gaps remain `UNSUPPORTED`, not confidently rejected nonrecipes.

A recovered raw record is not a guarantee of final normalization quality. Normalization reparses immutable raw text with current deterministic adapters, and validation can quarantine uncertain or polluted extraction. Report raw recovery and normalized recipe counts separately. Remaining extraction failures and unexplored archives keep their sources partial even when every candidate file has an accounted outcome.
