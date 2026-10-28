# References

The phase files and worker briefs point at these documents instead of restating them.

| File | Contents | Read by |
|------|----------|---------|
| `artifacts.md` | run-dir layout, phase gates, batch states, refine round contract | orchestrator |
| `extraction-conventions.md` | transcript format, marking conventions, Flags, figure rules | extract workers |
| `card-writing-rules.md` | CW-1 to CW-16, lint rules L01 to L14, waivers | authors; orchestrator in triage |
| `review-rubric.md` | what to check, severities, categories, triage, common findings and fixes | reviewers; orchestrator |
| `note-types.md` | note types, fields, macros, provenance labels, tags, styling, stable IDs | authors; orchestrator |
| `device-import.md` | AnkiMobile / AnkiDroid / desktop import, updates, pace advice | orchestrator (final message) |

The JSON schemas for every artifact are package data in
`packages/adb-core/src/adb_core/schemas/` (manifest, figures, categories, card, findings,
triage). `adb validate` uses them.

## Exit codes (every `adb` command)

| Code | Meaning |
|------|---------|
| 0 | success / check passed |
| 1 | the check ran and found problems (details on stderr or in the report) |
| 2 | bad command-line usage, including a path argument that doesn't exist; also `state detect` reporting `mode=invalid` |
| 3 | a file wasn't valid JSON |
| 4 | a file couldn't be read or written |
