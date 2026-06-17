# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This is a single-context repo.

Expected domain documentation:

- `CONTEXT.md` at the repo root
- `docs/adr/` at the repo root

## Before exploring, read these

- Read root `CONTEXT.md` before domain-sensitive work.
- Read relevant files in `docs/adr/` before architectural work.

## Fail fast

This repo prefers failing fast. If required domain docs are missing for a skill's work, stop and report the missing file or directory clearly instead of silently continuing.

## Use the glossary's vocabulary

When your output names a domain concept in an issue title, refactor proposal, hypothesis, or test name, use the term as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If the concept you need is not in the glossary yet, that is a signal: either the project does not use that language, or there is a real documentation gap to resolve with `/grill-with-docs`.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> Contradicts ADR-0007 (`example-title`) because...
