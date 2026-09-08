# build-order.md

Machine-parseable build sequencing for the issues decomposed from
`spec/spec.md` (see the `issue-decomposition` skill). Generated once by
the Sequencing stage after issue creation; not updated for progress —
the Scrum Master derives live progress from GitHub issue/PR state.

```yaml
issues:
  - number: 6
    title: "feat: validate CLI arguments and reject missing/unsupported input files"
    depends_on: []
  - number: 7
    title: "feat: validate Azure Speech credentials from environment variables"
    depends_on: []
  - number: 8
    title: "feat: submit audio file as an Azure Batch Transcription job"
    depends_on: [7]
  - number: 9
    title: "feat: poll Azure transcription job until terminal status or timeout"
    depends_on: [8]
  - number: 10
    title: "feat: download and transform Azure transcription results into the output schema"
    depends_on: [9]
  - number: 11
    title: "feat: orchestrate end-to-end transcription for one or more files with per-file error handling"
    depends_on: [6, 7, 8, 9, 10]

groups:
  - [6, 7]
  - [8]
  - [9]
  - [10]
  - [11]

order: [6, 7, 8, 9, 10, 11]
```
