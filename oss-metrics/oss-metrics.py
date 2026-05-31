#!/usr/bin/env python3
"""Generate a standalone static HTML dashboard from GitHub API data for any repo."""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_json(url, token):
    """Perform a GET request and return the parsed JSON, or None on failure."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "oss-metrics/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [!] HTTP {e.code} {url} – {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [!] {e} {url}", file=sys.stderr)
        return None


def fmt_count(n):
    """Return a short human-readable number, e.g. 1234 -> '1.2k'."""
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def escape_html(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def build_html(repo, title, repo_data, code_freq, contribs_data, langs_data):
    """Return a complete HTML document as a string."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # --- derived values -----------------------------------------------
    full_name = escape_html(repo)
    desc = escape_html(repo_data.get("description", "")) if repo_data else ""
    stars = fmt_count(repo_data.get("stargazers_count")) if repo_data else "—"
    forks = fmt_count(repo_data.get("forks_count")) if repo_data else "—"
    issues = fmt_count(repo_data.get("open_issues_count")) if repo_data else "—"
    language = escape_html(repo_data.get("language") or "") if repo_data else ""
    license_info = ""
    if repo_data:
        lic = repo_data.get("license")
        if lic:
            license_info = escape_html(lic.get("spdx_id") or lic.get("name") or "")
    pushed_at = ""
    if repo_data and repo_data.get("pushed_at"):
        pushed_at = repo_data["pushed_at"][:10]
    created_at = ""
    if repo_data and repo_data.get("created_at"):
        created_at = repo_data["created_at"][:10]
    topics = repo_data.get("topics", []) if repo_data else []

    # --- commit frequency (last 52 weeks) -----------------------------
    commit_weeks = []
    if code_freq and isinstance(code_freq, list):
        for entry in code_freq[-52:]:
            week_ts, adds, deletes = entry[0], entry[1], entry[2]
            commit_weeks.append([week_ts, adds + deletes])
    commit_json = json.dumps(commit_weeks)

    # --- top 10 contributors ------------------------------------------
    top_contribs = []
    if contribs_data and isinstance(contribs_data, list):
        cds = []
        for c in contribs_data:
            if c.get("author") and c.get("total", 0) > 0:
                cds.append((c["author"].get("login", "unknown"), c["total"]))
        cds.sort(key=lambda x: -x[1])
        top_contribs = cds[:10]
    contrib_json = json.dumps(top_contribs)

    # --- languages ----------------------------------------------------
    lang_items = []
    if langs_data and isinstance(langs_data, dict):
        lang_items = sorted(langs_data.items(), key=lambda x: -x[1])
    lang_json = json.dumps(lang_items)

    # --- chart dimensions --------------------------------------------
    chart_w = 700
    chart_h = 250

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – oss-metrics</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; padding: 24px; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1.3rem; margin: 28px 0 12px; color: #58a6ff; }}
  .subtitle {{ color: #8b949e; font-size: 0.95rem; margin-bottom: 20px; }}
  .badge-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
  .badge {{ background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 8px 14px; font-size: 0.9rem; }}
  .badge strong {{ color: #f0f6fc; }}
  .desc {{ margin: 10px 0 16px; line-height: 1.5; color: #8b949e; }}
  .topics {{ margin: 8px 0; }}
  .topic-tag {{ display: inline-block; background: #1f6feb33; color: #58a6ff; border-radius: 12px; padding: 2px 10px; font-size: 0.8rem; margin: 2px 4px 2px 0; border: 1px solid #1f6feb55; }}
  canvas {{ background: #161b22; border-radius: 6px; border: 1px solid #30363d; display: block; margin: 8px 0; max-width: 100%; height: auto; }}
  .chart-wrap {{ overflow-x: auto; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #21262d; color: #484f58; font-size: 0.85rem; text-align: center; }}
  .err-msg {{ color: #f85149; font-style: italic; padding: 10px 0; }}
</style>
</head>
<body>
<div class="container">

<h1>{escape_html(title)}</h1>
<div class="subtitle">{full_name}</div>

<div class="desc">{desc}</div>

<div class="topics">
  {''.join(f'<span class="topic-tag">{escape_html(t)}</span>' for t in topics)}
</div>

<div class="badge-row">
  <span class="badge">⭐ Stars <strong>{stars}</strong></span>
  <span class="badge">⑂ Forks <strong>{forks}</strong></span>
  <span class="badge">◉ Open Issues <strong>{issues}</strong></span>
  {f'<span class="badge">🔤 Language <strong>{language}</strong></span>' if language else ''}
  {f'<span class="badge">⚖ License <strong>{license_info}</strong></span>' if license_info else ''}
</div>

<h2>Commit Activity (weekly, last 52 weeks)</h2>
<div class="chart-wrap">
  <canvas id="chart-commits" width="{chart_w}" height="{chart_h}"></canvas>
</div>
<div id="err-commits" class="err-msg"></div>

<h2>Top Contributors (commits)</h2>
<div class="chart-wrap">
  <canvas id="chart-contribs" width="{chart_w}" height="{chart_h}"></canvas>
</div>
<div id="err-contribs" class="err-msg"></div>

<h2>Languages</h2>
<div class="chart-wrap">
  <canvas id="chart-langs" width="{chart_w}" height="{chart_h}"></canvas>
</div>
<div id="err-langs" class="err-msg"></div>

<h2>Issue Velocity</h2>
<div class="badge-row">
  <span class="badge">◉ Open Issues <strong>{issues}</strong></span>
  {f'<span class="badge">📅 Last Push <strong>{pushed_at}</strong></span>' if pushed_at else ''}
  {f'<span class="badge">🚀 Created <strong>{created_at}</strong></span>' if created_at else ''}
</div>

<div class="footer">Generated by oss-metrics on {now}</div>

</div>

<script>
(function(){{
function drawBarChart(canvasId, data, labelKey, valueKey, errId, color) {{
  const canvas = document.getElementById(canvasId);
  const errEl = document.getElementById(errId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;

  if (!data || data.length === 0) {{
    if (errEl) errEl.textContent = "No data available.";
    return;
  }}

  const values = data.map(function(d) {{ return d[valueKey]; }});
  const labels = data.map(function(d) {{ return d[labelKey]; }});
  const maxVal = Math.max.apply(null, values) || 1;
  const barCount = values.length;
  const padTop = 10, padBottom = 30, padLeft = 50, padRight = 20;
  const chartW = W - padLeft - padRight;
  const chartH = H - padTop - padBottom;
  const barW = Math.min(30, (chartW / barCount) * 0.7);
  const gap = (chartW - barW * barCount) / (barCount + 1);

  ctx.clearRect(0, 0, W, H);

  // grid lines
  ctx.strokeStyle = "#21262d";
  ctx.lineWidth = 1;
  for (var g = 0; g <= 4; g++) {{
    var y = padTop + chartH - (chartH * g / 4);
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(W - padRight, y);
    ctx.stroke();
    ctx.fillStyle = "#484f58";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(Math.round(maxVal * g / 4), padLeft - 4, y + 4);
  }}

  // bars
  for (var i = 0; i < barCount; i++) {{
    var x = padLeft + gap + i * (barW + gap);
    var h = (values[i] / maxVal) * chartH;
    var y = padTop + chartH - h;
    ctx.fillStyle = color || "#58a6ff";
    ctx.fillRect(x, y, barW, h);
    // label
    ctx.fillStyle = "#8b949e";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "center";
    var lbl = labels[i];
    if (lbl && lbl.length > 5) lbl = lbl.substring(0, 5) + "…";
    ctx.fillText(lbl, x + barW / 2, H - 6);
  }}
}}

// Commit data
var commitData = {commit_json};
var commitItems = commitData.map(function(w) {{
  var d = new Date(w[0] * 1000);
  var m = d.getUTCMonth() + 1, y = String(d.getUTCFullYear()).slice(2);
  return {{ label: m + "/" + y, value: w[1] }};
}});
drawBarChart("chart-commits", commitItems, "label", "value", "err-commits", "#58a6ff");

// Contributor data
var contribData = {contrib_json};
var contribItems = contribData.map(function(c) {{
  return {{ label: c[0], value: c[1] }};
}});
drawBarChart("chart-contribs", contribItems, "label", "value", "err-contribs", "#d29922");

// Language data
var langData = {lang_json};
var langItems = langData.map(function(l) {{
  return {{ label: l[0], value: l[1] }};
}});
drawBarChart("chart-langs", langItems, "label", "value", "err-langs", "#3fb950");

}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a standalone static HTML dashboard from GitHub API data."
    )
    parser.add_argument("--repo", "-r", required=True, help="Repository in owner/name format (e.g. yassirpersonelle-oss/oss-toolkit)")
    parser.add_argument("--token", help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--output", "-o", default="index.html", help="Output HTML file (default: index.html)")
    parser.add_argument("--title", help="Custom dashboard title (default: repo full name)")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  [!] No GITHUB_TOKEN set. API rate limits are strict without one.", file=sys.stderr)

    print(f"  Fetching data for {args.repo} …")

    base = f"https://api.github.com/repos/{args.repo}"

    repo_data = fetch_json(base, token)
    if repo_data is None:
        print("  [!] Failed to fetch repository data. Check repo name and token.", file=sys.stderr)
        sys.exit(1)

    code_freq = fetch_json(f"{base}/stats/code_frequency", token)
    contribs_data = fetch_json(f"{base}/stats/contributors", token)
    langs_data = fetch_json(f"{base}/languages", token)

    dashboard_title = args.title or repo_data.get("full_name", args.repo)

    html = build_html(args.repo, dashboard_title, repo_data, code_freq, contribs_data, langs_data)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Generated dashboard: {args.output}")


if __name__ == "__main__":
    main()
