#!/usr/bin/env python3
"""Fetch Apple Developer Releases RSS, filter by keywords, and generate a filtered RSS feed."""

import html
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from xml.dom import minidom
from xml.etree import ElementTree

import feedparser
import requests
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "feeds.yml"
OUTPUT_DIR = SCRIPT_DIR / "docs"
OUTPUT_PATH = OUTPUT_DIR / "feed.xml"
FEED_URL = os.getenv("FEED_URL", "https://eliu-lotso.github.io/os-rss/feed.xml")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


VERSION_RE = re.compile(r"^(\w+)\s+(\d+)")
TITLE_RE = re.compile(
    r"^(iOS|macOS|iPadOS|watchOS)\s+([\d.]+)\s*(?:(beta|RC)\s*(\d*)\s*)?\((\w+)\)$"
)

SECURITY_ALIAS_RE = re.compile(
    r"^(macOS|iOS|iPadOS|watchOS|tvOS|visionOS)\s+[A-Za-z][A-Za-z0-9 ]*?\s+(\d)"
)
SECURITY_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
SECURITY_LINK_RE = re.compile(
    r"<a href=\"(https://support\.apple\.com/en-us/\d+)\"[^>]*>(.*?)</a>", re.S
)
SECURITY_DATE_RE = re.compile(
    r"<td[^>]*>\s*<p[^>]*>\s*(\d{1,2}\s+\w{3}\s+\d{4})", re.S
)


def matches_keywords(title: str, keywords: list[str]) -> bool:
    title_lower = title.lower()
    return any(title_lower.startswith(kw.lower()) for kw in keywords)


def meets_min_version(title: str, min_version: int) -> bool:
    m = VERSION_RE.match(title)
    if not m:
        return False
    return int(m.group(2)) >= min_version


def is_within_age(entry, max_age_days: int) -> bool:
    if not entry.get("published_parsed"):
        return True
    try:
        pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        return pub_dt >= cutoff
    except Exception:
        return True


def fetch_rss(feed_cfg: dict) -> tuple[dict, list]:
    url = feed_cfg["url"]
    print(f"Fetching {url} ...")
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        print(f"Failed to parse feed: {parsed.bozo_exception}", file=sys.stderr)
        return parsed.feed, []
    return parsed.feed, parsed.entries


def normalize_security_title(title: str) -> str:
    m = SECURITY_ALIAS_RE.match(title)
    if not m:
        return title
    return f"{m.group(1)} {m.group(2)}{title[m.end(2):]}"


def fetch_apple_security(feed_cfg: dict) -> tuple[dict, list]:
    url = feed_cfg.get("url", "https://support.apple.com/en-us/100100")
    print(f"Fetching {url} ...")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    entries = []
    for row in SECURITY_ROW_RE.findall(resp.text):
        link_m = SECURITY_LINK_RE.search(row)
        if not link_m:
            continue
        link, raw_title = link_m.groups()
        raw_title = html.unescape(raw_title).strip()
        date_m = SECURITY_DATE_RE.search(row)
        published = ""
        published_parsed = None
        if date_m:
            published = date_m.group(1)
            try:
                published_parsed = time.strptime(published, "%d %b %Y")
            except ValueError:
                published_parsed = None
        entries.append({
            "title": normalize_security_title(raw_title),
            "link": link,
            "published": published,
            "published_parsed": published_parsed,
        })
    return {}, entries


def fetch_and_filter(feed_cfg: dict) -> tuple[dict, list]:
    feed_type = feed_cfg.get("type", "rss")
    if feed_type == "apple_security":
        feed_meta, entries = fetch_apple_security(feed_cfg)
    else:
        feed_meta, entries = fetch_rss(feed_cfg)

    filters = feed_cfg.get("filters", {})
    keywords = filters.get("keywords", [])
    min_version = filters.get("min_version")
    max_age_days = filters.get("max_age_days")

    filtered = []
    for entry in entries:
        title = entry.get("title", "")
        if keywords and not matches_keywords(title, keywords):
            continue
        if min_version and not meets_min_version(title, min_version):
            continue
        if max_age_days and not is_within_age(entry, max_age_days):
            continue
        filtered.append(entry)

    return feed_meta, filtered


def parse_title(title: str) -> Optional[dict]:
    m = TITLE_RE.match(title)
    if not m:
        return None
    os_name, version, pre_tag, pre_num, build = m.groups()
    is_beta = pre_tag is not None
    pre_label = ""
    if pre_tag:
        pre_label = f" {pre_tag.capitalize()}"
        if pre_num:
            pre_label += f" {pre_num}"
    return {
        "os": os_name,
        "version": version,
        "build": build,
        "is_beta": is_beta,
        "pre_label": pre_label,
    }


def format_title_line(info: dict) -> str:
    tag = info["pre_label"] if info["is_beta"] else ""
    release_type = "测试版" if info["is_beta"] else "正式版"
    return f"{info['os']} {info['version']}{tag} | {release_type}"


def format_description_line(info: dict, pub_date: str) -> str:
    parts = []
    if pub_date:
        parts.append(pub_date)
    parts.append(f"Build: {info['build']}")
    return " | ".join(parts)


def format_pub_date_short(entry) -> str:
    if entry.get("published_parsed"):
        try:
            return datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def format_pub_date_gmt(entry) -> str:
    """Convert entry's published_parsed to RFC 822 GMT format."""
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def build_rss_xml(entries: list, test_mode: bool = False) -> str:
    """Build RSS XML with a single item (matching qweather's proven format)."""
    impl = minidom.getDOMImplementation()
    doc = impl.createDocument(None, "rss", None)
    rss = doc.documentElement
    rss.setAttribute("version", "2.0")
    rss.setAttribute("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = doc.createElement("channel")
    rss.appendChild(channel)

    def el(tag, text):
        node = doc.createElement(tag)
        node.appendChild(doc.createTextNode(text))
        return node

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S")
    pub_date_rfc = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    channel.appendChild(el("title", "Apple OS Releases"))
    channel.appendChild(el("link", FEED_URL))
    channel.appendChild(el("description", "iOS, macOS, iPadOS, watchOS — 正式版与测试版更新推送"))

    atom_link = doc.createElement("atom:link")
    atom_link.setAttribute("href", FEED_URL)
    atom_link.setAttribute("rel", "self")
    atom_link.setAttribute("type", "application/rss+xml")
    channel.appendChild(atom_link)

    lines = []
    for entry in entries:
        raw_title = entry.get("title", "")
        info = parse_title(raw_title)
        if info:
            lines.append(format_title_line(info))
        else:
            lines.append(raw_title)

    summary = " / ".join(lines) if lines else "No updates"

    item = doc.createElement("item")

    if test_mode:
        item_title = f"[测试] Apple OS 推送测试 ({now.strftime('%m-%d %H:%M:%S')})"
        item_guid = f"os-test-{timestamp}"
        item_desc = f"这是一条测试推送 ({now.strftime('%Y-%m-%d %H:%M:%S UTC')})\n实际内容: {summary}"
    else:
        item_title = f"Apple OS ({now.strftime('%m-%d %H:%M')})"
        item_guid = f"os-{timestamp}"
        item_desc = summary

    item.appendChild(el("title", item_title))
    item.appendChild(el("link", "https://developer.apple.com/news/releases/"))
    item.appendChild(el("pubDate", pub_date_rfc))

    guid_node = doc.createElement("guid")
    guid_node.setAttribute("isPermaLink", "false")
    guid_node.appendChild(doc.createTextNode(item_guid))
    item.appendChild(guid_node)

    desc_node = doc.createElement("description")
    desc_node.appendChild(doc.createCDATASection(item_desc))
    item.appendChild(desc_node)

    channel.appendChild(item)

    return doc.toprettyxml(indent="  ")


def get_existing_guids() -> set:
    """Read the previous feed.xml and extract all guid values."""
    if not OUTPUT_PATH.exists():
        return set()
    try:
        tree = ElementTree.parse(OUTPUT_PATH)
        return {g.text for g in tree.iter("guid") if g.text}
    except Exception:
        return set()


def send_bark(title: str, body: str):
    bark_key = os.getenv("BARK_KEY")
    if not bark_key:
        print("[BARK] No BARK_KEY set, skipping push.")
        return
    url = f"https://api.day.app/{bark_key}/{quote_plus(title)}/{quote_plus(body)}"
    try:
        r = requests.get(url, params={"group": "Apple OS", "icon": "https://developer.apple.com/favicon.ico"}, timeout=10)
        r.raise_for_status()
        print("[BARK] Push sent successfully.")
    except Exception as e:
        print(f"[BARK] Push failed: {e}")


def send_slack(title: str, body: str):
    webhook_url = os.getenv("SLACK_WEBHOOK")
    if not webhook_url:
        print("[SLACK] No SLACK_WEBHOOK set, skipping push.")
        return
    payload = {
        "text": f"*{title}*\n{body}",
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        print("[SLACK] Push sent successfully.")
    except Exception as e:
        print(f"[SLACK] Push failed: {e}")


def build_bark_summary(entries: list) -> tuple:
    """Build a concise BARK notification from a list of entries."""
    lines = []
    for entry in entries:
        raw_title = entry.get("title", "")
        info = parse_title(raw_title)
        if info:
            tag = info["pre_label"] if info["is_beta"] else ""
            release = "测试版" if info["is_beta"] else "正式版"
            lines.append(f"{info['os']} {info['version']}{tag} {release}")
        else:
            lines.append(raw_title)
    title = f"Apple OS 更新 ({len(entries)})"
    body = "\n".join(lines)
    return title, body


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Apple RSS filter")
    parser.add_argument(
        "--test", action="store_true",
        help="Generate unique guids so Slack treats all items as new (for testing)",
    )
    args = parser.parse_args()

    old_guids = get_existing_guids()

    config = load_config()
    all_entries = []

    for feed_cfg in config.get("feeds", []):
        feed_meta, entries = fetch_and_filter(feed_cfg)
        all_entries.extend(entries)
        print(f"  Kept {len(entries)} item(s) after filtering.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    xml_str = build_rss_xml(all_entries, test_mode=args.test)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(xml_str)

    mode = " (TEST MODE)" if args.test else ""
    print(f"Generated {OUTPUT_PATH} with {len(all_entries)} item(s).{mode}")

    new_guids = {entry.get("id") or entry.get("link", "") for entry in all_entries}
    truly_new = [
        e for e in all_entries
        if (e.get("id") or e.get("link", "")) not in old_guids
    ]

    if truly_new:
        print(f"  {len(truly_new)} new item(s) detected, sending push.")
        title, body = build_bark_summary(truly_new)
        send_bark(title, body)
        send_slack(title, body)
    elif args.test:
        print("  Test mode: sending push for all items.")
        title, body = build_bark_summary(all_entries)
        send_bark(title, body)
        send_slack(title, body)
    else:
        print("  No new items, skipping push.")


if __name__ == "__main__":
    main()
