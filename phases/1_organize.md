# Phase 1: Organize

Goal: turn the input folder into numbered page units you have actually looked at, and
plan the extraction batches so each worker gets a coherent run of pages.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...` (see SKILL.md).
Paths come from `adb state detect`: `<INPUT_DIR>`, `<RUN_DIR>`.

## Steps

**1. Inventory.**

```bash
adb organize run "<INPUT_DIR>" "<RUN_DIR>"
```

Every image becomes a unit with EXIF rotation applied. Each PDF page is rendered and its
text layer kept. Word and PowerPoint files contribute their text plus any embedded
pictures, and plain-text files their text. Hidden files and the skill's own folders are
skipped, and unsupported files are listed as `skipped` with a reason. Units are numbered
`p001...` in natural file order, which for phone photos is usually capture order.

**2. Look at every contact sheet.** Read each `<RUN_DIR>/sheets/contact_NN.jpg`. You are
looking for:

- **Distinct documents.** A printed review packet vs a handwritten notebook vs glued-in
  handouts vs textbook pages. These become sources (subdecks) in Categorize, and batch
  boundaries now.
- **Pages with nothing to learn.** Blank pages, a cover with only a name, an accidental
  photo of the floor. Exclude them (step 3). Keep messy, faint or sideways pages: those
  are the extract workers' job.
- **Duplicates.** Units marked `DUP` are already skipped. Check that near-duplicates
  (two shots of the same page) aren't both needed. If one is clearly better, exclude the
  other and give the reason.
- **Order problems.** For example, a packet whose pages were photographed out of order.
  Note it for Categorize; don't rename the user's files.

**3. Exclude what has nothing to learn.**

```bash
adb organize exclude "<RUN_DIR>" p012 --reason "blank page"
```

(`adb organize include` undoes it.) When unsure, keep the page.

**4. Write `<RUN_DIR>/organize_notes.md`.** Keep it short: one line per document or page
range ("p001-p006 printed study guide, 12 numbered sections; p007-p025 notebook,
p010/p012/p015 photographed sideways, p013-p014 faint pencil"). Extract workers read it.

**5. Plan extraction batches.**

```bash
adb subsets extract "<RUN_DIR>" --break-before p007,p020
```

Pass `--break-before` the first page of each distinct document, so no worker straddles
two kinds of material. Batch size comes from `config.toml` (`extract.pages_per_worker`;
text-only units count about a third of a page).

## Gate

```bash
adb state verify "<RUN_DIR>" organize && adb state advance "<RUN_DIR>" organize
```

Progress line to the user, e.g. *"Organized 25 photos into 25 pages (none skipped), in
two documents: a 6-page review packet and 19 notebook pages. 5 transcription batches next."*

## Error conditions

- **`no usable pages found`:** report what was skipped and why (from the `skipped` list), then stop.
- **Many `skipped` entries with errors:** report the files and reasons. Ask whether to continue without them.
