#!/usr/bin/env python3
"""Docs tooling for the three-tier versioned docs tree.

    versions/latest/     the published, indexed copy
    versions/next/       full mirror of latest/ plus unreleased changes; noindex'd
                         and unreachable in production via a permanent redirect
    versions/vX.Y.x/     frozen archives, canonical'd back to latest/

Every command exists to keep those tiers consistent:

    seo       [--check]              canonical / noindex invariant
    sync-next [--check] [--base R]   replay latest/ onto next/ (git 3-way merge)
    check                            nav<->disk parity, internal links, redirects
    promote   VERSION [--dry-run]    cut a release

Run from the repo root.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

SITE = "https://docs.cyborg.co"
VERSIONS = pathlib.Path("versions")
DOCS_JSON = pathlib.Path("docs.json")
LATEST, NEXT = "latest", "next"
NOINDEX = "noindex: true"
MANAGED = ("canonical:", "noindex:")

# The staging redirect is permanent: it is what keeps unreleased docs unreachable
# in production. Unlike the per-version wildcards, promote must never remove it.
NEXT_REDIRECT = f"/{VERSIONS.name}/{NEXT}/:slug*"


# ---------------------------------------------------------------- git helpers

def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"error: git {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout


def git_show(ref, path):
    """File content at a ref, or None if it did not exist there."""
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changed_files(base, pathspec):
    out = git("diff", "--name-only", f"{base}...HEAD", "--", pathspec, check=False)
    return {l for l in out.splitlines() if l.strip()}


def default_base():
    for ref in ("origin/main", "main"):
        if subprocess.run(["git", "rev-parse", "--verify", ref],
                          capture_output=True).returncode == 0:
            return ref
    return None


# --------------------------------------------------------- frontmatter helpers

def split_frontmatter(text):
    """(keys, body) for a leading --- block, else (None, text)."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    return text[4:end + 1].splitlines(), text[end + 5:]


def apply_tag(text, tag):
    """Set the managed frontmatter key, or strip it when tag is None.

    An already-correct tag keeps its position so re-running produces no diff.
    """
    keys, body = split_frontmatter(text)
    if keys is None:
        return None
    if tag and tag in keys:
        new = [k for k in keys if k == tag or not k.startswith(MANAGED)]
    else:
        new = [k for k in keys if not k.startswith(MANAGED)]
        if tag:
            new.append(tag)
    if new == keys:
        return None
    return "---\n" + "\n".join(new) + "\n---\n" + body


def strip_managed(text):
    out = apply_tag(text, None)
    return text if out is None else out


def normalized(text):
    """Comparable form: managed keys removed, trailing newline normalised.

    Both matter. Every next/ page differs from its latest/ twin by the noindex
    line, and several pages lack a final newline -- without this, a comparison
    reports differences that are not real and gets ignored.
    """
    return strip_managed(text).rstrip("\n") + "\n"


# ------------------------------------------------------------- tree discovery

def version_dirs():
    return sorted(p for p in VERSIONS.iterdir() if p.is_dir())


def archives():
    return [p for p in version_dirs() if p.name not in (LATEST, NEXT)]


def pages(directory):
    """Page paths relative to a version directory, without the .mdx suffix."""
    return {p.relative_to(directory).with_suffix("") for p in directory.rglob("*.mdx")}


def load_docs_json():
    return json.loads(DOCS_JSON.read_text(encoding="utf-8"))


def current_label(doc=None):
    """The live version label -- docs.json is the source of truth, not the dirname."""
    doc = doc or load_docs_json()
    return doc["navigation"]["versions"][0]["version"]


def element_spans(text, key):
    """(start, end, value) for each element of a top-level JSON array, plus the
    offset of its closing bracket. Lets us splice docs.json without reserialising
    it, which would reformat all 3.5k lines."""
    dec = json.JSONDecoder()
    i = text.index('"%s"' % key)
    pos = text.index("[", i) + 1
    spans = []
    while True:
        while text[pos] in " \t\r\n,":
            pos += 1
        if text[pos] == "]":
            return spans, pos
        obj, end = dec.raw_decode(text, pos)
        spans.append((pos, end, obj))
        pos = end


# ------------------------------------------------------------------ seo

def desired_tag(version, relpath):
    if version == LATEST:
        return None
    if version == NEXT:
        return NOINDEX
    if (VERSIONS / LATEST / relpath).with_suffix(".mdx").exists():
        return f"canonical: {SITE}/{VERSIONS.name}/{LATEST}/{relpath}"
    return NOINDEX


def cmd_seo(args):
    counts, total = {}, 0
    for vdir in version_dirs():
        for path in sorted(vdir.rglob("*.mdx")):
            rel = path.relative_to(vdir).with_suffix("")
            new = apply_tag(path.read_text(encoding="utf-8"), desired_tag(vdir.name, rel))
            if new is None:
                continue
            total += 1
            counts[vdir.name] = counts.get(vdir.name, 0) + 1
            if not args.check:
                path.write_text(new, encoding="utf-8")
    verb = "would update" if args.check else "updated"
    for v in sorted(counts):
        print(f"  {verb} {counts[v]:>4} pages in {v}/")
    print(f"  {verb} {total} pages total" if total else "  all pages already correct")
    return 1 if (args.check and total) else 0


# ------------------------------------------------------------- sync-next

def merge3(base, ours, theirs):
    """git merge-file. Returns (text, conflicted)."""
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        for name, content in (("ours", ours), ("base", base), ("theirs", theirs)):
            (d / name).write_text(content, encoding="utf-8")
        r = subprocess.run(["git", "merge-file", "-p", "--diff3",
                            str(d / "ours"), str(d / "base"), str(d / "theirs")],
                           capture_output=True, text=True)
        return r.stdout, r.returncode != 0


def cmd_sync_next(args):
    latest, nxt = VERSIONS / LATEST, VERSIONS / NEXT
    if not latest.is_dir():
        sys.exit(f"error: {latest} not found")
    nxt.mkdir(parents=True, exist_ok=True)

    created, merged, conflicts, missing = [], [], [], []
    for rel in sorted(pages(latest)):
        src = (latest / rel).with_suffix(".mdx")
        dst = (nxt / rel).with_suffix(".mdx")
        want = apply_tag(src.read_text(encoding="utf-8"), NOINDEX) or src.read_text(encoding="utf-8")

        if not dst.exists():
            missing.append(str(rel))
            if not args.check:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(want, encoding="utf-8")
                created.append(str(rel))
            continue

        cur = dst.read_text(encoding="utf-8")
        base = git_show("HEAD", str(src))
        if base is None:
            continue                                  # brand-new page, nothing to merge
        if normalized(cur) == normalized(base):
            # Unmodified fork: latest/ wins outright, no conflict possible.
            if normalized(cur) != normalized(want) and not args.check:
                dst.write_text(want, encoding="utf-8")
                merged.append(str(rel))
            elif normalized(cur) != normalized(want):
                merged.append(str(rel))
        else:
            # Staged edits present: real 3-way merge against the previous latest/.
            out, bad = merge3(strip_managed(base), strip_managed(cur), strip_managed(src.read_text(encoding="utf-8")))
            out = apply_tag(out, NOINDEX) or out
            if normalized(out) != normalized(cur):
                (conflicts if bad else merged).append(str(rel))
                if not args.check:
                    dst.write_text(out, encoding="utf-8")

    extra = sorted(str(p) for p in pages(nxt) - pages(latest))

    if missing:
        print(f"  {'missing in next/' if args.check else 'created'}: {len(missing)}")
    if merged:
        print(f"  {'stale (would sync)' if args.check else 'synced'}: {len(merged)}")
        for m in merged[:10]:
            print(f"      {m}")
    if conflicts:
        print(f"  CONFLICTS needing manual resolution: {len(conflicts)}")
        for c in conflicts:
            print(f"      {c}")
    if extra:
        print(f"  next/-only pages (new staged pages, or deleted from latest/): {len(extra)}")
        for e in extra[:10]:
            print(f"      {e}")

    drift = []
    if args.check:
        base_ref = args.base or default_base()
        if base_ref:
            cl = changed_files(base_ref, str(VERSIONS / LATEST))
            cn = changed_files(base_ref, str(VERSIONS / NEXT))
            for f in sorted(cl):
                rel = pathlib.Path(f).relative_to(VERSIONS / LATEST)
                twin = str((VERSIONS / NEXT / rel))
                if (VERSIONS / NEXT / rel).exists() and twin not in cn:
                    drift.append(f)
            if drift:
                print(f"\n  DRIFT vs {base_ref}: latest/ changed without its next/ twin:")
                for f in drift:
                    print(f"      {f}")
                print("\n  Run `scripts/docs.py sync-next`, or apply the `no-next-sync`")
                print("  label if the fork is intentionally divergent.")

    if not (missing or merged or conflicts or drift):
        print("  next/ is in sync with latest/")
    return 1 if (args.check and (missing or merged or conflicts or drift)) else 0


# ----------------------------------------------------------------- check

def cmd_check(args):
    doc = load_docs_json()
    problems = []

    # 1. nav <-> disk
    for entry in doc["navigation"]["versions"]:
        refs = set(re.findall(r'"(versions/[^"]+)"', json.dumps(entry)))
        if not refs:
            continue
        vdir = VERSIONS / sorted(refs)[0].split("/")[1]
        disk = {f"{vdir}/{p}" for p in pages(vdir)} if vdir.exists() else set()
        for r in sorted(refs - disk):
            problems.append(f"nav references a missing page: {r}")
        # Archives are frozen and carry historical orphans; only latest/ must be exact.
        if vdir.name == LATEST:
            for o in sorted(disk - refs):
                problems.append(f"page on disk but absent from nav: {o}")

    # 2. internal links resolve (absolute and relative)
    # next/ is only self-contained once it is a full mirror; before that its
    # relative links legitimately point at pages that live only in latest/.
    next_is_mirror = (VERSIONS / NEXT).is_dir() and not (
        pages(VERSIONS / LATEST) - pages(VERSIONS / NEXT))
    for mdx in sorted(pathlib.Path(".").glob("*.mdx")) + sorted(VERSIONS.rglob("*.mdx")):
        if VERSIONS / NEXT in mdx.parents and not next_is_mirror:
            continue
        text = mdx.read_text(encoding="utf-8")
        links = re.findall(r'\]\(([^)\s]+)\)', text) + re.findall(r'href="([^"\s]+)"', text)
        for link in links:
            link = link.split("#")[0].split("?")[0]
            if not link or re.match(r'^(https?:|mailto:|#)', link):
                continue
            if link.startswith("/images") or link.startswith("images/"):
                continue
            target = (pathlib.Path(link.lstrip("/")) if link.startswith("/")
                      else (mdx.parent / link).resolve().relative_to(pathlib.Path.cwd().resolve()))
            if target.suffix:
                continue
            # A link to a directory resolves to that section (verified against
            # production), so it counts as valid.
            if target.with_suffix(".mdx").exists() or target.is_dir():
                continue
            problems.append(f"dangling link in {mdx}: {link}")

    # 3. redirects
    ondisk = {p.name for p in version_dirs()}
    for r in doc.get("redirects", []):
        src, dst = r["source"], r["destination"]
        if src == dst:
            problems.append(f"redirect self-loop: {src}")
        m = re.match(rf"/{VERSIONS.name}/([^/]+)/:slug\*", src)
        if m:
            # A wildcard whose version exists on disk shadows the whole archive.
            if m.group(1) in ondisk and m.group(1) != NEXT:
                problems.append(f"redirect shadows an on-disk version: {src}")
            continue
        if ":slug" in dst:
            continue
        if not pathlib.Path(dst.lstrip("/")).with_suffix(".mdx").exists():
            problems.append(f"redirect destination does not exist: {src} -> {dst}")

    if problems:
        for p in problems:
            print(f"  {p}")
        print(f"\n  {len(problems)} problem(s)")
        return 1
    print("  nav parity, internal links and redirects all OK")
    return 0


# ---------------------------------------------------------------- promote

def cmd_promote(args):
    new_label = args.version if args.version.endswith(".x") else \
        ".".join(args.version.lstrip("v").split(".")[:2]) + ".x"
    new_label = new_label if new_label.startswith("v") else "v" + new_label

    text = DOCS_JSON.read_text(encoding="utf-8")
    doc = json.loads(text)
    old_label = current_label(doc)
    labels = [v["version"] for v in doc["navigation"]["versions"]]
    lapsed = labels[-1]

    plan = [
        f"archive   versions/{LATEST}/ -> versions/{old_label}/",
        f"seo       re-run canonical/noindex across all archives",
        f"delete    versions/{lapsed}/  (+ wildcard redirect -> latest)",
        f"redirect  remove /{VERSIONS.name}/{old_label}/:slug*  (archive is back on disk)",
        f"promote   versions/{NEXT}/ -> versions/{LATEST}/  (strip noindex)",
        f"reseed    versions/{NEXT}/ from new latest/  (add noindex)",
        f"docs.json label {old_label} -> {new_label}, move \"tag\": \"Latest\", "
        f"insert {old_label} archive entry, drop {lapsed}",
        f"keep      {NEXT_REDIRECT}  (permanent - never removed)",
    ]
    # next/ must be a complete mirror before it can become latest/. Without this
    # guard a partial next/ silently truncates the published docs.
    latest_pages, next_pages = pages(VERSIONS / LATEST), pages(VERSIONS / NEXT)
    orphaned = latest_pages - next_pages
    if orphaned:
        print(f"  REFUSING: next/ is missing {len(orphaned)} page(s) that exist in latest/.")
        print("  Promoting would delete them from the published docs. Run:")
        print("      scripts/docs.py sync-next")
        for o in sorted(str(x) for x in orphaned)[:10]:
            print(f"      missing: {o}")
        if len(orphaned) > 10:
            print(f"      ... and {len(orphaned) - 10} more")
        return 1

    print(f"  promoting {old_label} -> {new_label}\n")
    for step in plan:
        print(f"    {step}")

    print("\n  staged changes in next/ that this would publish:")
    latest, nxt = VERSIONS / LATEST, VERSIONS / NEXT
    staged = []
    for rel in sorted(pages(nxt)):
        src = (latest / rel).with_suffix(".mdx")
        dst = (nxt / rel).with_suffix(".mdx")
        if not src.exists():
            staged.append(f"NEW  {rel}")
        elif normalized(dst.read_text(encoding="utf-8")) != normalized(src.read_text(encoding="utf-8")):
            staged.append(f"MOD  {rel}")
    for s in staged:
        print(f"    {s}")
    if not staged:
        print("    (none)")

    # New pages arriving from next/ have no nav entry yet, and promote cannot
    # guess where they belong in the tree -- surface them for a human.
    nav_refs = set(re.findall(r'"(versions/[^"]+)"', json.dumps(doc["navigation"]["versions"][0])))
    unnavigated = sorted(str(r) for r in pages(nxt)
                         if f"{VERSIONS.name}/{LATEST}/{r}" not in nav_refs)
    if unnavigated:
        print("\n  pages with no nav entry -- add them to docs.json after promoting:")
        for u in unnavigated:
            print(f"    {u}")

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    # ---- filesystem -------------------------------------------------------
    latest.rename(VERSIONS / old_label)
    nxt.rename(latest)
    for path in latest.rglob("*.mdx"):                       # promoted pages are indexed
        out = apply_tag(path.read_text(encoding="utf-8"), None)
        if out is not None:
            path.write_text(out, encoding="utf-8")
    for src in latest.rglob("*.mdx"):                        # re-seed staging
        dst = nxt / src.relative_to(latest)
        dst.parent.mkdir(parents=True, exist_ok=True)
        body = src.read_text(encoding="utf-8")
        dst.write_text(apply_tag(body, NOINDEX) or body, encoding="utf-8")
    shutil.rmtree(VERSIONS / lapsed)

    # The freshly archived version needs canonicals, and surviving archives may
    # gain or lose them as pages appear in or vanish from the new latest/.
    cmd_seo(argparse.Namespace(check=False))

    # ---- docs.json --------------------------------------------------------
    text = DOCS_JSON.read_text(encoding="utf-8")

    spans, _ = element_spans(text, "redirects")
    drop = next((sp for sp in spans
                 if sp[2]["source"] == f"/{VERSIONS.name}/{old_label}/:slug*"), None)
    if drop:                       # the archive is back on disk; the wildcard would shadow it
        prev_end = max((sp[1] for sp in spans if sp[1] <= drop[0]), default=None)
        text = text[:prev_end] + text[drop[1]:] if prev_end else text[:drop[0]] + text[drop[1]:]

    spans, _ = element_spans(text, "redirects")
    entry = ',\n    {\n      "source": "/%s/%s/:slug*",\n      "destination": "/%s/%s/:slug*"\n    }' % (
        VERSIONS.name, lapsed, VERSIONS.name, LATEST)
    text = text[:spans[-1][1]] + entry + text[spans[-1][1]:]

    spans, _ = element_spans(text, "versions")
    live = text[spans[0][0]:spans[0][1]]
    archived = live.replace(f'"{VERSIONS.name}/{LATEST}/', f'"{VERSIONS.name}/{old_label}/')
    archived = re.sub(r'\n\s*"tag":\s*"Latest",', "", archived)
    archived = archived.replace(f'"version": "{old_label}"', f'"version": "{old_label}"', 1)
    promoted = live.replace(f'"version": "{old_label}"', f'"version": "{new_label}"', 1)
    text = text[:spans[0][0]] + promoted + ",\n      " + archived + text[spans[0][1]:]

    spans, _ = element_spans(text, "versions")
    last = spans[-1]
    prev_end = spans[-2][1]
    text = text[:prev_end] + text[last[1]:]

    json.loads(text)                                          # fail loudly on malformed output
    DOCS_JSON.write_text(text, encoding="utf-8")

    print("\n  promoted. next steps:")
    print("    1. add any unnavigated pages above to docs.json")
    print("    2. scripts/docs.py seo && scripts/docs.py check")
    return 0


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seo", help="canonical / noindex invariant")
    p.add_argument("--check", action="store_true")
    p.set_defaults(fn=cmd_seo)

    p = sub.add_parser("sync-next", help="replay latest/ onto next/")
    p.add_argument("--check", action="store_true")
    p.add_argument("--base", help="ref to diff against for the drift check")
    p.set_defaults(fn=cmd_sync_next)

    p = sub.add_parser("check", help="nav parity, internal links, redirects")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("promote", help="cut a release")
    p.add_argument("version")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_promote)

    args = ap.parse_args()
    if not DOCS_JSON.exists():
        sys.exit("error: run from the repo root")
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
