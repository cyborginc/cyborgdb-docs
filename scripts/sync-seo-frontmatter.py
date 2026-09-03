#!/usr/bin/env python3
"""Enforce the SEO frontmatter invariant across versioned docs.

Every page outside `versions/latest/` is either canonical'd to its live
counterpart or noindex'd when it has none:

    versions/latest/**   ->  no canonical, no noindex  (the indexed copy)
    versions/next/**     ->  noindex: true             (unreleased staging)
    versions/vX.Y.x/**   ->  canonical -> latest/<same path> if it exists,
                             otherwise noindex: true    (page is gone from latest)

Idempotent: existing canonical/noindex lines are replaced, not duplicated, so
re-running is a no-op. Run it after any change to `versions/latest/` — pages
added to latest let archives upgrade from noindex to canonical, and pages
removed from latest would otherwise leave archives pointing at a 404.

    sync-seo-frontmatter.py            apply changes
    sync-seo-frontmatter.py --check    report drift and exit 1 (for CI)
"""

import argparse
import pathlib
import sys

SITE = "https://docs.cyborg.co"
VERSIONS = pathlib.Path("versions")
LATEST, NEXT = "latest", "next"
MANAGED = ("canonical:", "noindex:")


def split_frontmatter(text):
    """Return (keys, body) where keys are the frontmatter lines. None if absent."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    return text[4:end + 1].splitlines(), text[end + 5:]


def desired_tag(version, relpath):
    """The managed frontmatter line this page should carry, if any."""
    if version == LATEST:
        return None
    if version == NEXT:
        return "noindex: true"
    if (VERSIONS / LATEST / relpath).exists():
        return f"canonical: {SITE}/{VERSIONS.name}/{LATEST}/{relpath.with_suffix('')}"
    return "noindex: true"


def rewrite(path, version, relpath):
    """Return new file text, or None if already correct / unparseable."""
    text = path.read_text(encoding="utf-8")
    keys, body = split_frontmatter(text)
    if keys is None:
        print(f"  !! no frontmatter, skipped: {path}", file=sys.stderr)
        return None

    tag = desired_tag(version, relpath)
    if tag and tag in keys:
        # Already correct: keep its position, drop any other managed key.
        new_keys = [k for k in keys if k == tag or not k.startswith(MANAGED)]
    else:
        new_keys = [k for k in keys if not k.startswith(MANAGED)]
        if tag:
            new_keys.append(tag)
    if new_keys == keys:
        return None
    return "---\n" + "\n".join(new_keys) + "\n---\n" + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 instead of writing")
    args = ap.parse_args()

    if not (VERSIONS / LATEST).is_dir():
        sys.exit(f"error: {VERSIONS / LATEST} not found (run from the repo root)")

    changed, counts = [], {}
    for vdir in sorted(p for p in VERSIONS.iterdir() if p.is_dir()):
        version = vdir.name
        for path in sorted(vdir.rglob("*.mdx")):
            relpath = path.relative_to(vdir)
            new = rewrite(path, version, relpath)
            if new is None:
                continue
            changed.append(path)
            counts[version] = counts.get(version, 0) + 1
            if not args.check:
                path.write_text(new, encoding="utf-8")

    verb = "would update" if args.check else "updated"
    for version in sorted(counts):
        print(f"  {verb} {counts[version]:>4} pages in {version}/")
    if not changed:
        print("  all pages already correct")
    print(f"  {verb} {len(changed)} pages total")

    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
