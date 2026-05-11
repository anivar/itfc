#!/usr/bin/env python3
"""
- Remove dead-end slugs that are shadowed by useful redirects:
    'search' (Drupal search dispatcher, body="No Search was performed")
    'user/login' (Drupal login form, won't work statically)
- Flatten 2-hop redirect chains
"""
import json
import os
from glob import glob

PAGES_DIR = "src/data/pages"
REDIRECTS = "src/data/redirects.json"

DEAD_SLUGS = {"search", "user/login"}


def main():
    # Drop dead slugs
    removed = 0
    for f in sorted(glob(f"{PAGES_DIR}/*.json")):
        shard = json.load(open(f))
        kept = [p for p in shard if p.get("slug") not in DEAD_SLUGS]
        if len(kept) != len(shard):
            removed += len(shard) - len(kept)
            with open(f, "w") as fh:
                json.dump(kept, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"Removed {removed} dead slugs")

    # Flatten chains
    redirects = json.load(open(REDIRECTS))
    flattened = 0
    for k in list(redirects.keys()):
        target = redirects[k]
        seen = {k}
        while target in redirects and target not in seen:
            seen.add(target)
            target = redirects[target]
        if target != redirects[k]:
            redirects[k] = target
            flattened += 1
    print(f"Flattened {flattened} chained redirects")

    out = {kk: redirects[kk] for kk in sorted(redirects)}
    with open(REDIRECTS, "w") as fh:
        fh.write("{\n")
        items = list(out.items())
        for i, (kk, vv) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            fh.write(f"{json.dumps(kk, ensure_ascii=False)}: {json.dumps(vv, ensure_ascii=False)}{comma}\n")
        fh.write("}\n")
    print(f"Total redirects: {len(out)}")


if __name__ == "__main__":
    main()
