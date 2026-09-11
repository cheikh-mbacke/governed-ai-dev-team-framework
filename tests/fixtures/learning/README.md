# Learning fixtures (anonymized Feedback Exports)

Source: consented exports under the auditor's `Downloads/feedback` (9 files,
2026-09-06 → 2026-09-11), regenerated via:

```bash
python tools/anonymize_feedback_fixtures.py --source <path-to-raw-exports>
```

Anonymization keeps observation/attempt **identities**, `revision`, timestamps,
categories, and recurrence structure needed to regress aggregate deduplication.
It redacts symptoms, free-text improvements, and hashes project / WU / attempt
ids.

Do **not** put raw exports (with transcripts or client project names) in this
tree. Do **not** modify `tests/fixtures/projects/clean|legacy` for this purpose.
