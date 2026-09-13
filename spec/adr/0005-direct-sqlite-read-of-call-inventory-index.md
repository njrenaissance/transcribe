# ADR-0005: Read call-inventory's `calls` table directly via `sqlite3`, without a `wireline` dependency

## Status
accepted

## Context
Issue #20 needs per-file call metadata (reference number, target/associate
numbers, direction, call timing, classification, language, monitor, and any
text-message body) to populate a frontmatter block in each transcript's
output. That metadata is produced by a separate project, `call-inventory`
(importable as the `wireline` package), which builds a SQLite index from CDR
reports — one `calls` table row per call event, keyed by reference number and
target — documented in call-inventory's own
`docs/adr/0005-CDR-FIRST-CALL-RECORD-INDEX.md`.

Three integration shapes were considered:

1. Add `wireline` as a runtime dependency and call into its Python API.
2. Shell out to the `wireline` CLI as a subprocess and parse its output.
3. Read the `calls` table directly via stdlib `sqlite3`.

Option 1 doesn't fit today's `wireline`: its only query surface, `report()`,
prints/writes a CSV manifest and returns `None` — there is no function that
returns a single `CallRecord` object, and the SQL builder behind `report()` is
private (underscore-prefixed), not intended as a public API for another
project to call. Building that public API would mean designing and
maintaining new surface area in a separate codebase for a need specific to
this project. Option 2 (subprocess + CSV parsing) avoids touching
`call-inventory` but couples this project to CLI argument spelling and CSV
text formatting, and pays a process-spawn cost per lookup.

`call-inventory`'s own `docs/adr/0001-PURE-PYTHON-ZERO-DEPENDENCY.md` commits
it to zero third-party *runtime* dependencies for itself; it says nothing
about being consumed by another project, so it does not bear on this
decision either way.

## Decision
Read the `calls` table directly using stdlib `sqlite3`, in a new
`src/transcribe/call_lookup.py`. Treat the `calls` table schema documented in
call-inventory's ADR-0005 as the versioned data contract between the two
projects, rather than either project's code. `transcribe` defines its own
local `CallRecord` (a `NamedTuple` covering only the fields its frontmatter
needs), not an import of `wireline.CallRecord`, and writes its own minimal SQL:

```sql
SELECT ref, target, associate, direction, call_start, duration, end_time,
       classification, call_progress, language, monitor, text_message
FROM calls
WHERE ref = ? AND target = ?
ORDER BY id LIMIT 1
```

`target` is digits-normalized before binding, mirroring how call-inventory's
own filtering treats phone numbers. The database path is supplied via a new
`--call-db` CLI flag (or the `CALL_DB_PATH` environment variable) — `transcribe`
never assumes where or how the index was built, only that it matches the
documented schema.

## Consequences
- No new runtime dependency on `wireline`/`call-inventory`; `transcribe` can
  run against any SQLite file matching the `calls` schema, regardless of
  which tool produced it.
- `call-inventory` is not modified by this work.
- A schema change to call-inventory's `calls` table is a silent breaking
  change for `transcribe` unless both projects are updated together — there
  is no compile-time coupling, only the documented contract in each
  project's ADRs. A future schema change there should be cross-referenced
  against this ADR.
- Rules out subprocess/CLI-based integration: no CLI-output-parsing
  fragility, no per-lookup process-spawn overhead.
- If `(ref, target)` is not unique in `calls` (not expected in practice), the
  first row by `id` wins silently rather than raising — a simplifying
  assumption, not a schema guarantee.
