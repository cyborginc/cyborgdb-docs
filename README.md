# CyborgDB Docs

Repository for all CyborgDB Docs, hosted live at [docs.cyborg.co](https://docs.cyborg.co).

### Development

Install the [Mintlify CLI](https://www.npmjs.com/package/mintlify) to preview the documentation changes locally:

```
npm i -g mintlify
```

Run the following command at the root of the repo:

```
mintlify dev
```

### Contributing

The docs are versioned across `versions/latest/`, `versions/next/` and frozen archives. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to edit a page, stage an unreleased change, and cut a release.

### Publishing Changes

Changes will be deployed to production automatically after pushing to the `main`. You must work on a separate branch and create a PR for changes to be merged into `main`.