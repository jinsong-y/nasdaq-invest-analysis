# Nasdaq Investment Analysis

This context defines the project language for Nasdaq 100 DCA research and the live market monitoring surface.

## Language

**Market Regime Dashboard**:
A live monitoring surface that summarizes the current Nasdaq 100 market state and turns the signal stack into a DCA pacing reference.
_Avoid_: Dashboard, site, Vercel page, all reports

**Research Report**:
A generated analysis artifact used to evaluate strategy variants, robustness, historical behavior, or project findings.
_Avoid_: Dashboard, production page

**Automatic Publish**:
The recurring release of the Market Regime Dashboard as the live monitoring surface.
_Avoid_: Vercel push, deploy script, publish all reports

**Publishable Market Date**:
The latest trading date whose required daily inputs are complete enough to score and publish the Market Regime Dashboard.
_Avoid_: Latest input date, intraday date, calendar date

**Daily Input**:
A completed market data point used to score a Publishable Market Date.
_Avoid_: Intraday quote, live tick

**Stale Dashboard**:
A Market Regime Dashboard whose published date is older than the latest Publishable Market Date expected from the daily data sources.
_Avoid_: Safe fallback, cached success

**Published Artifact**:
A static file committed for Vercel to serve as part of the Market Regime Dashboard.
_Avoid_: Raw data, snapshot, research output
