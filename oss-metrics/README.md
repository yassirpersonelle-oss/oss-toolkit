# oss-metrics

Generate a **standalone static HTML dashboard** from GitHub API data for any public repository. No external dependencies — uses only the Python stdlib.

## Usage

```bash
# Basic (public repo data, may be rate-limited)
python oss-metrics.py --repo yassirpersonelle-oss/oss-toolkit

# With a GitHub token (recommended — avoids rate limits, required for traffic/stats endpoints)
python oss-metrics.py --repo yassirpersonelle-oss/oss-toolkit --token ghp_xxxx…

# Via environment variable
export GITHUB_TOKEN=ghp_xxxx…
python oss-metrics.py --repo yassirpersonelle-oss/oss-toolkit

# Custom output file
python oss-metrics.py -r yassirpersonelle-oss/oss-toolkit -o dashboard.html

# Custom title
python oss-metrics.py -r yassirpersonelle-oss/oss-toolkit --title "My Project Dashboard"
```

## What data is shown

| Section | Source API |
|---|---|
| Header (stars, forks, issues, language, license) | `GET /repos/{owner}/{repo}` |
| Commit activity bar chart (last 52 weeks) | `GET /repos/{owner}/{repo}/stats/code_frequency` |
| Top 10 contributors bar chart | `GET /repos/{owner}/{repo}/stats/contributors` |
| Languages bar chart | `GET /repos/{owner}/{repo}/languages` |
| Issue velocity (open count, last push, created) | `GET /repos/{owner}/{repo}` |

## Requirements

- Python 3.x (stdlib only — `urllib`, `json`, `argparse`)
- A [GitHub personal access token](https://github.com/settings/tokens) (classic, with `public_repo` scope) is **strongly recommended** — some endpoints (`stats/code_frequency`, `stats/contributors`) have strict rate limits without authentication.

## Output

A self-contained HTML file with a dark theme. All CSS and JavaScript is inlined — zero external requests. Bar charts are drawn on `<canvas>` with vanilla JS.

## License

MIT
