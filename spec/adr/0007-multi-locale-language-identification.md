# ADR-0007: Single-call multi-locale language identification, not a separate identify-then-transcribe pass

## Status
accepted

## Context
Issue #21: `DEFAULT_LOCALE` was hardcoded to `en-US` with no detection, so
non-English call audio (at minimum Spanish, per the live-fire manifest) was
transcribed against the wrong locale — producing garbled or low-confidence
text rather than a usable transcript. The issue asked whether Azure's
fast-transcription endpoint supports multi-locale candidate identification in
a single request, or whether a genuinely separate language-ID call is needed.

This was tested directly against the real endpoint (not just inferred from
docs) using a call from `data/manifest.csv` that a human listener had
identified as Spanish. Sending `{"locales": ["en-US"]}` (today's behavior)
transcribed it as low-confidence English nonsense (`confidence: 0.419`).
Sending `{"locales": ["en-US", "es-US"]}` in the *same single request*
correctly identified and transcribed the Spanish content, reporting
`"locale": "es-US"` and `confidence: 0.554` on the resulting phrase.

A second question surfaced during that same test: Azure's language
identification is forced-choice among the candidate locales supplied — it
always attributes each phrase to its best-matching candidate. In every real
response observed, `locale` was populated; the API schema doesn't appear to
expose a true "language could not be identified" state distinct from a
low-confidence match.

## Decision
1. Send multiple candidate locales in the existing single fast-transcription
   request — no separate identify-then-transcribe pass.
   `transcription.CANDIDATE_LOCALES = ("en-US", "es-US")` replaces the old
   single-value `DEFAULT_LOCALE`, covering the languages actually present in
   the live-fire manifest (out of scope: a general N-language pipeline).
2. Record the locale(s) actually detected: `transform.transform_result` now
   collects the distinct, sorted `locale` values reported across a file's
   phrases into a new frontmatter field, `detected_locales` (a list — a
   single call can code-switch across segments). This is separate from the
   call record's own `language` field (call-inventory's own classification,
   not Azure's detection).
3. A phrase with no `locale` field does not fail the transcription. Given
   Azure's forced-choice behavior (finding #2 above), there is no observed
   "unidentified" signal to treat as an error — a missing `locale` just
   contributes nothing to `detected_locales` rather than raising, matching
   `error-handling.md`'s "don't add error handling for scenarios that can't
   happen."

## Consequences
- Every fast-transcription call now costs marginally more (Azure bills
  multi-locale requests differently) and can take slightly longer, in
  exchange for correct transcription of non-English audio that previously
  produced garbage.
- `detected_locales` can be `[]` for a phrase set where Azure omitted
  `locale` entirely — a valid, non-error output, not a failure.
- Adding a third language later means appending to `CANDIDATE_LOCALES`, not
  redesigning the pipeline — no separate language-ID step exists to touch.
- If Azure's behavior changes (e.g. a future API version does expose an
  explicit "unidentified" state), this decision should be revisited rather
  than silently reinterpreted.
