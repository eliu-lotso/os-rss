#!/usr/bin/env python3
"""Fetch Apple Developer Releases RSS, filter by keywords, and generate a filtered RSS feed."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

import feedparser
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "feeds.yml"
OUTPUT_DIR = SCRIPT_DIR / "docs"
OUTPUT_PATH = OUTPUT_DIR / "feed.xml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


VERSION_RE = re.compile(r"^(\w+)\s+(\d+)")


def matches_keywords(title: str, keywords: list[str]) -> bool:
    title_lower = title.lower()
    return any(title_lower.startswith(kw.lower()) for kw in keywords)


def meets_min_version(title: str, min_version: int) -> bool:
    """Check if the major version number in the title is >= min_version.

    Parses titles like 'iOS 26.3.1 (23D8133)' or 'macOS 26.4 beta 3'.
    """
    m = VERSION_RE.match(title)
    if not m:
        return False
    return int(m.group(2)) >= min_version


def fetch_and_filter(feed_cfg: dict) -> tuple[dict, list]:
    url = feed_cfg["url"]
    filters = feed_cfg.get("filters", {})
    keywords = filters.get("keywords", [])
    min_version = filters.get("min_version")

    print(f"Fetching {url} ...")
    parsed = feedparser.parse(url)

    if parsed.bozo and not parsed.entries:
        print(f"Failed to parse feed: {parsed.bozo_exception}", file=sys.stderr)
        return parsed.feed, []

    filtered = []
    for entry in parsed.entries:
        title = entry.get("title", "")
        if keywords and not matches_keywords(title, keywords):
            continue
        if min_version and not meets_min_version(title, min_version):
            continue
        filtered.append(entry)

    return parsed.feed, filtered


def build_rss_xml(feed_meta, entries: list) -> ElementTree:
    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Apple OS Releases (Filtered)"
    SubElement(channel, "link").text = "https://developer.apple.com/news/releases/"
    SubElement(channel, "description").text = (
        "Filtered Apple Developer Releases: iOS, macOS, iPadOS, watchOS updates."
    )
    SubElement(channel, "language").text = "en-US"
    SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    for entry in entries:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = entry.get("title", "")
        SubElement(item, "link").text = entry.get("link", "")
        SubElement(item, "guid").text = entry.get("id") or entry.get("link", "")
        SubElement(item, "pubDate").text = entry.get("published", "")

        description = entry.get("summary", "")
        if description:
            SubElement(item, "description").text = description

    indent(rss, space="  ")
    return ElementTree(rss)


def main():
    config = load_config()
    all_entries = []

    for feed_cfg in config.get("feeds", []):
        feed_meta, entries = fetch_and_filter(feed_cfg)
        all_entries.extend(entries)
        print(f"  Kept {len(entries)} item(s) after filtering.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tree = build_rss_xml({}, all_entries)
    tree.write(OUTPUT_PATH, encoding="unicode", xml_declaration=True)

    print(f"Generated {OUTPUT_PATH} with {len(all_entries)} item(s).")


if __name__ == "__main__":
    main()
