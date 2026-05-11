# Claude / agent conventions for this repo

## Commit messages

Do not add `Co-Authored-By: Claude …` or the `🤖 Generated with [Claude Code]`
line to commit messages or PR bodies. Authorship is curated manually.

## Bulk-refetch scratch files

Inputs/outputs of `scripts/refetch_latest.py` live under `/home/niyam/` rather
than `/tmp/` because `/tmp` is periodically wiped on this machine.
Checkpoint files are `scripts/_refetch.json` and `scripts/_refetch_done.json`
(gitignored).
