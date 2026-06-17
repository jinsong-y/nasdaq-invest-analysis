# Use public-only Automatic Publish for the Market Regime Dashboard

The Market Regime Dashboard is the only surface covered by Automatic Publish. The publish workflow fetches Daily Input, fails fast on source or validation errors, skips publishing a Stale Dashboard, writes Published Artifacts directly to `public/`, commits only `public/*`, and lets Vercel deploy from GitHub. It does not publish Research Reports, does not use intraday overlay data, and does not commit raw data or snapshots because the live monitoring surface should stay narrow, reproducible enough to validate, and low-noise in Git history.

## Considered Options

- Commit raw data, snapshots, reports, and `public/*`: better audit trail, but noisy Git history and higher conflict risk.
- Generate reports first, then copy to `public/`: useful for research output, but adds duplicate state to Automatic Publish.
- Include intraday overlay data: fresher inputs, but weaker source stability and more complex date semantics.
