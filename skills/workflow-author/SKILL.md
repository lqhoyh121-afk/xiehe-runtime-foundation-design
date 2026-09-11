---
name: workflow-author
description: "Build and check offline workflow author packages."
version: 0.1.0
author: Laiqh, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [workflow, offline, authoring]
    related_skills: []
---
# Workflow author

## When to Use
Create or inspect the single-code-output-v1 offline author package. Not for starting a business Case, waiting, external actions or production.

## Prerequisites
Run from the checked-out project with its existing Python/jsonschema dependencies. This repository skill is not installed into Hermes by this task. Use the actual repository root, never a remembered machine path.

## Procedure
1. Read [author guide](references/author-guide.md). Confirm the author's output directory is new or empty.
2. Use `terminal` to run `python -B tools/workflow_author.py init --template single-code-output-v1 --output <empty-dir> --format json`.
3. Use `terminal` to run `python -B tools/workflow_author.py check --package <package-dir> --format json`; generated drafts must not pass.
4. The author completes declarations, implementation, independent tests and accepted references. Explicit synthetic preparation is a separate TEST ONLY command in the guide, not a fallback after ordinary check fails.
5. Run component tests independently, then the correct check entry. Record report versions, exit status and limitations; return to controller for independent review.

## Pitfalls
No arbitrary module paths, trust JSON, business defaults, permission issuance or runtime state. I3/I4/I6 remain unsupported. A check never runs package code. Static checks are not a malicious-Python sandbox or proof of business correctness.

## Verification
Expect CREATED/0, DRAFT/2, REJECTED/3, INCOMPLETE/4, CONFLICT/5, USAGE_ERROR/64, INTERNAL_ERROR/1; PASSED/0 only for the declared offline subset. Runtime and production flags always false. Independent author blind-run is a later controller gate.
