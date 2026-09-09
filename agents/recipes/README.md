# Recipe collection

`RecipeCoordinator` reads the complete awesome-recipes README and inspects pinned Git trees. `config/recipe-sources.yaml` records all 42 links in the initial index, including inaccessible repositories, non-corpus applications, excluded source types, unsupported formats, and third-party corpora embedded in tools. Repository licensing and recipe-text licensing are separate. Unknown rights default to no prose publication.

Use the Python 3.11+ environment from the root README:

```sh
.venv/bin/python -m recipe_system.recipes discover
.venv/bin/python -m recipe_system.recipes plan --workers 3
.venv/bin/python -m recipe_system.recipes prepare
.venv/bin/python -m recipe_system.recipes collect --workers 3
.venv/bin/python -m recipe_system.recipes manifest
```

Discovery refreshes the index but preserves existing source pins and reviewed decisions. Newly linked sources are recorded as unsupported pending explicit inspection of corpus paths and text licensing. Review their complete trees in `state/recipes/discovery.json`; enable them by assigning exact `include`/`exclude` patterns and their inspected `estimated_items` count in YAML. Pins do not automatically follow source updates. For a new revision or changed partition, create a separate collection run root with its own configuration, cache, shards and state; merge centrally after validation. Existing raw snapshots remain intact.

Add a source within the same repository by recording its inspected license, pinned revision, corpus patterns and candidate count in the YAML, then extend the saved plan:

```sh
.venv/bin/python -m recipe_system.recipes extend-plan --workers 3
.venv/bin/python -m recipe_system.recipes collect --workers 3
```

`extend-plan` subtracts every already owned source/path, keeps existing partitions byte-for-byte equivalent, and assigns additions to fresh `recipe-agent-N` shards. Repeating it is idempotent. Completed sources are skipped during collection and Food Lion is independent. A changed revision for an already owned source is rejected and needs a future explicit versioned-refresh workflow; adding sources does not require a separate repository or recollection.

Planning enumerates all included candidate files. Deterministic chunks of at most 200 files are assigned by size to the least loaded worker. `prepare` fills each shared Git cache centrally before workers start, downloading only corpus paths. Initial collection used three independent human-supervised AI source agents; the reusable CLI executes the same isolated workers with a thread pool. A saved plan is reused on resume. Repartitioning an existing checkpoint is rejected.

For independently delegated workers:

```sh
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-01
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-02
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-03
```

Each worker exclusively owns `data/recipes/raw/<agent>.jsonl` and `state/recipes/<agent>.json`. File locks reject concurrent ownership. Successful records are written atomically before processed IDs are checkpointed. Complete files are staged before commit; a failed recipe in a multi-recipe file cannot leak partial rows. Each checkpoint persists the full assigned index, revision, success IDs, cursor, explicit failures, timestamps and retry counts. Reruns skip successes and retain original retrieval times. Retry only the affected shard after fixing an adapter:

```sh
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-01 --retry-failures
```

Adapters support Markdown (including Chinese section headings and ingredient tables), YAML frontmatter/MDX and foodprocessor YAML, JSON Recipe structures, HTML JSON-LD and explicit microdata, and the meanrecipe gzip text archive. Parsing never executes repository code. Failed candidates remain available in the pinned Git object cache; do not delete caches until failures have been resolved or archived. Raw successful records include complete original text, extracted original measurements, repository/path/revision provenance, text license, attribution and retrieval timestamp. `original_source_url`, where present, records the upstream website independently of the pinned repository file URL.

Counts deliberately distinguish candidate files from extracted recipes: one file may contain several recipes, and a failed candidate may be a non-recipe index or placeholder. `candidate_files_discovered = candidate_files_processed + candidate_files_failed` proves file accounting. Exact recipe counts remain unknown when failures prevent determining how many recipes a file contains. The manifest lists every source decision and its individual counts. `complete-with-failures` means all enabled candidate files were attempted; it does not claim full extraction or collection of blocked/unsupported sources.

The BBC index contains 11,161 title/search records, preserved in `state/recipes/bbc-index.jsonl`. BBC robots rules explicitly prohibit this AI agent; no remote sitemap or recipe bodies were fetched. The evidence is `state/recipes/bbc-access.json`. YunYouJun's CSV video index is preserved in `state/recipes/yunyoujun-index.jsonl`; video-only instructions are unsupported. The sourdough-framework book uses interdependent LaTeX chapters/tables and has no reliable recipe-boundary adapter. These limitations are explicit source statuses, never successful full-recipe records.

The initial source license review permits prose publication only for enabled original corpora whose inspected license is MIT or Unlicense. Third-party copied fixtures remain unknown even if their repository software is permissively licensed. CC-BY-ND content is retained privately but not authorized for transformed prose publication by this flag. Publication must preserve attribution and the applicable source license notices.
