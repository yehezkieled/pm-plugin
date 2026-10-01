---
id: T002
title: Rate-limit login attempts
epic: E01
milestone: M1
status: todo
priority: P1
depends_on: [T001]
owner:
auto: no
plan: required
ready: yes
issue: https://github.com/acme/shortlink/issues/12
pr:
---
## What
Block an account for 15 minutes after 5 failed attempts. Keep "$HOME" and $(touch injected) literal.

## Current notes
This heading text belongs to the requester's words, not to the notes.

## Acceptance
- [ ] The sixth attempt is refused.

## Plan
Approach:
Touches:
Tests first:
Decisions to record:
approved: no

## Notes
Check the clock source first.
