#!/usr/bin/env python3
"""Generate transparent profile statistic cards from public GitHub API data only."""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import time
import urllib.error
import urllib.request

USERNAME = "Felpsqzzy"
API_ROOT = "https://api.github.com"
OUTPUT_DIR = pathlib.Path("dist/generated")
USER_AGENT = "Felpsqzzy-public-profile-stats"


def get_json(url: str) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (403, 429) and attempt < 2:
                retry_after = error.headers.get("Retry-After")
                try:
                    delay = int(retry_after) if retry_after else 2 ** (attempt + 1)
                except ValueError:
                    delay = 2 ** (attempt + 1)
                time.sleep(min(delay, 30))
                continue
            raise RuntimeError(
                f"GitHub public API request failed with HTTP {error.code}: {url}"
            ) from error
        except urllib.error.URLError as error:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError(f"Could not reach GitHub public API: {error}") from error
    raise RuntimeError("GitHub public API request failed after retries.")


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def fetch_public_data() -> tuple[dict, list[dict], dict[str, int]]:
    profile = get_json(f"{API_ROOT}/users/{USERNAME}")
    repositories = get_json(
        f"{API_ROOT}/users/{USERNAME}/repos?type=owner&per_page=100&sort=updated"
    )
    if not isinstance(profile, dict) or not isinstance(repositories, list):
        raise RuntimeError("GitHub returned an unexpected public API response.")

    # This endpoint returns public repositories; exclude forks so the cards reflect
    # projects owned by the profile rather than upstream projects.
    owned_public = [
        repo for repo in repositories
        if isinstance(repo, dict) and not repo.get("fork", False)
    ]

    language_bytes: dict[str, int] = {}
    for repo in owned_public:
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        languages = get_json(languages_url)
        if not isinstance(languages, dict):
            continue
        for language, byte_count in languages.items():
            if isinstance(byte_count, int) and byte_count > 0:
                language_bytes[language] = language_bytes.get(language, 0) + byte_count

    return profile, owned_public, language_bytes


def card_styles() -> str:
    return """<style>
      .title,.value{fill:#1f2328}
      .label,.caption{fill:#59636e}
      .border{stroke:#d0d7de}
      .track{fill:#eaeef2}
      @media(prefers-color-scheme:dark){
        .title,.value{fill:#e6edf3}
        .label,.caption{fill:#8b949e}
        .border{stroke:#30363d}
        .track{fill:#30363d}
      }
    </style>"""


def write_overview(profile: dict, repositories: list[dict]) -> None:
    followers = int(profile.get("followers") or 0)
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in repositories)
    forks = sum(int(repo.get("forks_count") or 0) for repo in repositories)
    metrics = [
        ("Public repos", len(repositories)),
        ("Stars", stars),
        ("Forks", forks),
        ("Followers", followers),
    ]
    x_positions = [28, 178, 328, 478]
    text = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 190" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub public overview</title>',
        f'<desc id="desc">Public overview for {escape(USERNAME)}: {len(repositories)} repositories, {stars} stars, {forks} forks, and {followers} followers.</desc>',
        card_styles(),
        '<rect class="border" x="1" y="1" width="618" height="188" rx="12" fill="none" stroke-width="1.5"/>',
        '<text class="title" x="26" y="38" font-family="Segoe UI,Arial,sans-serif" font-size="18" font-weight="700">GitHub overview</text>',
        f'<text class="caption" x="26" y="60" font-family="Segoe UI,Arial,sans-serif" font-size="12">Public repositories · updated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d} UTC</text>',
    ]
    for x, (label, value) in zip(x_positions, metrics):
        text.extend(
            [
                f'<text class="value" x="{x}" y="112" font-family="Segoe UI,Arial,sans-serif" font-size="28" font-weight="700">{value:,}</text>',
                f'<text class="label" x="{x}" y="139" font-family="Segoe UI,Arial,sans-serif" font-size="12">{escape(label)}</text>',
            ]
        )
    text.append("</svg>")
    (OUTPUT_DIR / "overview.svg").write_text("\n".join(text), encoding="utf-8")


def write_languages(language_bytes: dict[str, int]) -> None:
    total = sum(language_bytes.values())
    ranked = sorted(language_bytes.items(), key=lambda item: item[1], reverse=True)[:6]
    height = max(158, 76 + len(ranked) * 27)
    palette = {
        "HTML": "#e34c26",
        "JavaScript": "#f1e05a",
        "TypeScript": "#3178c6",
        "CSS": "#563d7c",
        "PLpgSQL": "#4b6b8a",
        "Python": "#3572a5",
        "Shell": "#89e051",
        "Jupyter Notebook": "#da5b0b",
        "Java": "#b07219",
        "Go": "#00add8",
        "C#": "#178600",
        "C++": "#f34b7d",
    }
    text = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub language usage</title>',
        f'<desc id="desc">Top {len(ranked)} languages by byte count across {len(language_bytes)} detected languages in the public repositories of {escape(USERNAME)}.</desc>',
        card_styles(),
        f'<rect class="border" x="1" y="1" width="618" height="{height-2}" rx="12" fill="none" stroke-width="1.5"/>',
        '<text class="title" x="26" y="36" font-family="Segoe UI,Arial,sans-serif" font-size="18" font-weight="700">Most used languages</text>',
    ]
    if total == 0 or not ranked:
        text.append('<text class="label" x="26" y="75" font-family="Segoe UI,Arial,sans-serif" font-size="13">No language data in public repositories yet.</text>')
    else:
        for index, (language, byte_count) in enumerate(ranked):
            y = 68 + index * 27
            percentage = byte_count / total * 100
            bar_width = 265 * percentage / 100
            color = palette.get(language, "#a371f7")
            text.extend(
                [
                    f'<text class="label" x="26" y="{y+12}" font-family="Segoe UI,Arial,sans-serif" font-size="12">{escape(language)}</text>',
                    f'<rect class="track" x="174" y="{y}" width="275" height="10" rx="5"/>',
                    f'<rect x="174" y="{y}" width="{bar_width:.2f}" height="10" rx="5" fill="{color}"/>',
                    f'<text class="value" x="472" y="{y+10}" font-family="Segoe UI,Arial,sans-serif" font-size="12" font-weight="600">{percentage:.2f}%</text>',
                ]
            )
    text.append("</svg>")
    (OUTPUT_DIR / "languages.svg").write_text("\n".join(text), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile, repositories, language_bytes = fetch_public_data()
    write_overview(profile, repositories)
    write_languages(language_bytes)
    print(
        f"Generated public stats for {len(repositories)} repositories "
        f"with {sum(language_bytes.values()):,} language bytes."
    )


if __name__ == "__main__":
    main()
