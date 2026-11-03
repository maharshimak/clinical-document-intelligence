# Changelog

All notable engineering changes to this repository are documented here.

The format follows the intent of [Keep a Changelog](https://keepachangelog.com/) and uses semantic versioning principles where releases are created.

## [Unreleased]

### Fixed
- Evidence spans for labeled values exclude surrounding whitespace, so `text[start:end] == raw_value`.
- Participant counts with misplaced thousands separators (`1,2,5,0`) or non-ASCII digits are rejected instead of silently merged.
- Ingested UTF-8 files with a byte-order mark no longer lose the first-line field; text files are decoded without newline translation so offsets refer to the hashed text.
- Lone-CR line endings are recognised as line breaks.

### Added
- Versioned `SourceDocument`, field-level evidence with verified spans, per-field schema validation, explicit confidence origin, append-only hash-chained review history, structured JSON export, field-level evaluation with a bundled synthetic set, and the `makma.v1` contract (`extract`, `apply_correction`, `export`, `evaluate`).

### Engineering
- Added repository ownership and structured contribution workflows.
- Added Dependabot coverage for Python and GitHub Actions dependencies.
- Added issue and pull-request templates focused on reproducibility, validation, risk, and rollback.
- Added consistent editor configuration and engineering standards.

## Release policy

A release should describe user-visible behavior, compatibility notes, validation evidence, and any migration or rollback requirements. Repository history remains the source of truth for individual commits.
