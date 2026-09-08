# build-order.md

Machine-parseable build sequencing for the issues decomposed from
`spec/spec.md` (see the `issue-decomposition` skill). Generated once by
the Sequencing stage after issue creation; not updated for progress —
the Scrum Master derives live progress from GitHub issue/PR state.

Revised after ADR-0003: the CLI now targets **local files via fast
(synchronous) transcription** first (Phase 1), with **blob-staged batch**
transcription deferred to Phase 2. This retires the batch-only polling issue
(#9) from the current path and reshapes #8 and #10 for the synchronous flow.

```yaml
# Phase 1 — local files via fast (synchronous) transcription (current)
issues:
  - number: 6
    title: "feat: validate CLI arguments and reject missing/unsupported input files"
    depends_on: []
    status: done
  - number: 7
    title: "feat: validate Azure Speech credentials from environment variables"
    depends_on: []
    status: done
  - number: 8
    title: "feat: transcribe a local audio file via Azure fast (synchronous) transcription"
    depends_on: [7]
  - number: 10
    title: "feat: transform fast-transcription result into the output schema and write FILE.json"
    depends_on: [8]
  - number: 11
    title: "feat: orchestrate end-to-end transcription for one or more files with per-file error handling"
    depends_on: [6, 7, 8, 10]

# Phase 2 — blob-staged batch transcription (deferred; see spec.md "Phase 2")
deferred:
  - number: 9
    title: "feat: poll Azure batch transcription job until terminal status or timeout"
    depends_on: []  # re-sequenced when Phase 2 (blob upload + batch submit) is built
    note: >
      Batch-only. Not part of the local/fast path. Belongs to the deferred
      blob-staged batch mode, alongside not-yet-created issues for blob upload,
      batch submit, and result download.

groups:
  - [6, 7]
  - [8]
  - [10]
  - [11]

order: [6, 7, 8, 10, 11]
```
