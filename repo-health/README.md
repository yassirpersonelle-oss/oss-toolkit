# repo-health

> One command to know if you should depend on this repo.

Like Lighthouse, but for GitHub repositories. Calculates a **health score (0–100)** for any public GitHub repo using the public GitHub API.

## Usage

```bash
python repo-health.py --repo owner/repo
```

### Options

| Flag | Description |
|------|-------------|
| `--repo` | **Required.** Owner/repo (e.g. `yassirpersonelle-oss/oss-toolkit`) |
| `--token` | GitHub personal access token (increases API rate limit from 60 to 5000 req/hr) |
| `--json` | Output results as JSON |
| `--verbose` | Show extra metadata (languages, stars, release info, etc.) |

### Example

```bash
$ python repo-health.py --repo lodash/lodash
```

```
📊 repo-health report: lodash/lodash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Bus Factor (15/20)        — 6 contributors
  ✅ Issue Resp. (15/20)       — last closed: 14d ago
  ✅ Commit Fresh. (20/20)     — last commit: 3h ago
  ⚠️  Dep. Fresh. (15/15)      — established project
  ✅ Documentation (15/15)     — README + wiki + description
  ✅ Community (10/10)         — 58328 stars, has license

  🏆 OVERALL: 90/100 — 🟢 Healthy
```

## Scoring Categories

All categories are scored out of their respective max, summing to **100 points**.

| Category | Max | What it measures | Why it matters |
|---|---|---|---|
| **Bus Factor** | 20 | Number of distinct contributors (≥8 = full marks) | Can the project survive if the maintainer leaves? |
| **Issue Responsiveness** | 20 | Days since last closed issue was updated | Are maintainers actively triaging bugs? |
| **Commit Freshness** | 20 | Days since last commit | Is the project actively maintained? |
| **Dependency Freshness** | 15 | Project age (proxy for maturity/established dependencies) | Older projects tend to have more stable dependencies |
| **Documentation** | 15 | README + Wiki + description on GitHub | Can you actually use this thing? |
| **Community** | 10 | Stars and license | Is there a community and is it legally safe to use? |

### Tiers

| Score | Status |
|-------|--------|
| ≥ 80 | 🟢 Healthy |
| ≥ 60 | 🟡 Fair |
| ≥ 40 | 🟠 Needs love |
| < 40 | 🔴 Critical |

## Rate Limits

Without a token, GitHub's unauthenticated API allows **60 requests per hour** — enough for occasional use. For heavier usage, pass a [personal access token](https://github.com/settings/tokens) with `--token` (no scopes needed for public repos) to get **5,000 requests per hour**.

## Requirements

- Python 3.6+
- Standard library only (no pip install needed)

## Notes

- "Dependency Freshness" uses repo age as a proxy because there's no universal public API for checking dependency versions across all ecosystems.
- The GitHub Issues API does not distinguish between issues and pull requests for all endpoints (some endpoints return both), but the health signals (response time, activity) remain valid.
