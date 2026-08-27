"""Explicit, user-initiated GitHub release checks."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable, ContextManager, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY = "Jaap79/JSON-Fold"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


@dataclass(frozen=True)
class UpdateResult:
    status: str
    message: str
    tag_name: str = ""
    html_url: str = ""


def version_key(version: str) -> tuple[int, ...]:
    """Return a pragmatic numeric key for release tags such as v1.2.3."""
    numbers = re.findall(r"\d+", version.lstrip("vV"))
    return tuple(int(number) for number in numbers) if numbers else (0,)


def check_for_updates(
    current_version: str,
    opener: Callable[..., ContextManager[Any]] = urlopen,
) -> UpdateResult:
    """Check GitHub only when called; never runs during application startup."""
    request = Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"JSON-Fold/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            return UpdateResult("no_release", "Er is nog geen publieke GitHub-release beschikbaar.")
        return UpdateResult("error", f"GitHub gaf HTTP-fout {error.code}.")
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        reason = getattr(error, "reason", error)
        return UpdateResult("error", f"Updatecontrole mislukt: {reason}")

    tag = str(payload.get("tag_name", "")).strip()
    url = str(payload.get("html_url", "")).strip()
    if not tag:
        return UpdateResult("error", "GitHub gaf geen geldige releaseversie terug.")
    if version_key(tag) > version_key(current_version):
        return UpdateResult("available", f"Versie {tag} is beschikbaar.", tag, url)
    return UpdateResult("current", f"Je gebruikt de nieuwste versie ({current_version}).", tag, url)
