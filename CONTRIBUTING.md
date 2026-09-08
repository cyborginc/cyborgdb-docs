# Contributing to the docs

## Layout

| directory | what it is | frontmatter |
|---|---|---|
| `versions/latest/` | the published, indexed docs | none |
| `versions/next/` | full mirror of `latest/` plus unreleased changes; not reachable in production | `noindex: true` |
| `versions/vX.Y.x/` | frozen archives (the last three releases) | `canonical:` → `latest/` |

`docs.json` is the source of truth for the current version label, not the directory name.

## Edit a published page

1. Edit `versions/latest/<page>.mdx`
2. `scripts/docs.py sync-next` — replays the change onto `next/`
3. Commit **both**

Skipping step 2 means `next/` silently reverts your change at the next release. CI blocks it.

## Document an unreleased feature

1. Edit `versions/next/<page>.mdx` only — never `latest/`
2. Commit

`next/` is 301'd in production, so preview staged pages with `mintlify dev`.

## Cut a release

1. `scripts/docs.py promote vX.Y.0 --dry-run` — read the manifest of what will publish
2. `scripts/docs.py promote vX.Y.0`
3. Add any pages it lists under *no nav entry* to `docs.json`
4. `scripts/docs.py check`
5. Open a PR, confirm the preview, merge

The script archives `latest/`, drops the oldest version and redirects it, promotes `next/`, re-seeds `next/`, and moves the `Latest` tag. It refuses to run if `next/` is not a complete mirror.

## Before pushing

```
scripts/docs.py check && scripts/docs.py seo --check && scripts/docs.py sync-next --check
```

CI runs the same three on every PR. Apply the `no-next-sync` label to skip the drift gate when a `next/` fork is *intentionally* divergent.
