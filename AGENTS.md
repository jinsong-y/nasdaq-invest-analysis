# Repository Instructions

- Don't fallback, just fail fast.
- Use `$caveman` to save tokens in each session.

## Deployment

- Keep only the Vercel project/domain `nasdaq-invest-analysis.vercel.app`.
- Do not deploy, reconnect, push to, or recreate the old Vercel project/domain `nasdq-analysis.vercel.app`.
- Normal deployment flow: commit and push to the GitHub repo, let Vercel auto-deploy, then verify `https://nasdaq-invest-analysis.vercel.app`.
- Do not run direct `vercel --prod` deploys unless explicitly requested.
