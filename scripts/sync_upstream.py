#!/usr/bin/env python3
"""Mirror Repcz Stash rules and translate labels; never execute upstream code."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

import yaml

UPSTREAM = "Repcz/Tool"
BRANCH = "X"
NAMES = {
    "Manual": "节点选择", "Global": "国外网站", "Streaming": "流媒体",
    "Microsoft": "微软服务", "Google": "谷歌服务", "AI": "AI服务",
    "Social": "社交平台", "Telegram": "电报消息", "Game": "游戏平台",
    "Emby": "Emby", "Spotify": "Spotify", "Final": "兜底分流",
    "HongKong": "香港节点", "United States": "美国节点",
    "Singapore": "新加坡节点", "Japan": "日本节点", "Taiwan": "台湾节点",
}
ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "repcz-stash-zh-sync"})
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read(16 * 1024 * 1024 + 1)
            if len(body) > 16 * 1024 * 1024:
                raise ValueError("upstream file exceeds size limit")
            return body
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def rule_url(url, repository):
    for prefix in (
        "https://github.com/Repcz/Tool/raw/X/Stash/Rules/",
        "https://raw.githubusercontent.com/Repcz/Tool/X/Stash/Rules/",
    ):
        if url.startswith(prefix):
            return f"https://raw.githubusercontent.com/{repository}/main/Stash/Rules/" + url[len(prefix):]
    raise ValueError("unrecognized upstream rule URL; review before publishing")


def validate(data):
    groups = data["proxy-groups"]
    names = [g["name"] for g in groups]
    if len(set(names)) != len(names):
        raise ValueError("duplicate translated group names")
    known = set(names) | {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
    graph = {}
    providers = data.get("proxy-providers", {})
    for group in groups:
        refs = group.get("proxies", [])
        if any(ref not in known for ref in refs):
            raise ValueError("unknown group reference")
        if any(p not in providers for p in group.get("use", [])):
            raise ValueError("unknown proxy provider")
        graph[group["name"]] = [r for r in refs if r in names]
    def visit(name, active, done):
        if name in active:
            raise ValueError("group reference cycle")
        if name in done:
            return
        for child in graph[name]:
            visit(child, active | {name}, done)
        done.add(name)
    done = set()
    for name in names:
        visit(name, set(), done)
    for rule in data["rules"]:
        parts = rule.split(",")
        if parts[-1] not in known:
            raise ValueError("unknown routing policy")
        if parts[0] == "RULE-SET" and parts[1] not in data["rule-providers"]:
            raise ValueError("unknown rule provider")


def translate(source, repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid destination repository")
    original = yaml.safe_load(source)
    unknown = {g["name"] for g in original["proxy-groups"]} - NAMES.keys()
    if unknown:
        raise ValueError("new upstream group needs translation: " + ", ".join(sorted(unknown)))
    expected = copy.deepcopy(original)
    for group in expected["proxy-groups"]:
        group["name"] = NAMES[group["name"]]
        if "proxies" in group:
            group["proxies"] = [NAMES.get(n, n) for n in group["proxies"]]
    expected["rules"] = [
        ",".join(rule.split(",")[:-1] + [NAMES.get(rule.split(",")[-1], rule.split(",")[-1])])
        for rule in expected["rules"]
    ]
    for provider in expected["rule-providers"].values():
        provider["url"] = rule_url(provider["url"], repository)
    lines = []
    for line in source.splitlines(keepends=True):
        if re.match(r"\s*-\s*\{name:", line):
            line = re.sub(r"(\bname:\s*)([^,}]+)",
                          lambda m: m[1] + NAMES.get(m[2].strip(), m[2]), line, count=1)
            line = re.sub(r"(\bproxies:\s*\[)([^\]]*)(\])",
                          lambda m: m[1] + ", ".join(NAMES.get(n.strip(), n.strip())
                                                     for n in m[2].split(",")) + m[3], line)
        elif re.match(r"\s*-\s*(RULE-SET|GEOIP|MATCH),", line):
            ending = "\n" if line.endswith("\n") else ""
            prefix, sep, target = line.rstrip("\n").rpartition(",")
            line = prefix + sep + NAMES.get(target, target) + ending
        lines.append(line)
    result = "".join(lines)
    for old, new in zip(original["rule-providers"].values(), expected["rule-providers"].values()):
        result = result.replace(old["url"], new["url"])
    actual = yaml.safe_load(result)
    if actual != expected:
        raise ValueError("upstream format changed; refusing non-translation edits")
    validate(actual)
    return result


def sync(repository):
    commit = json.loads(fetch(f"https://api.github.com/repos/{UPSTREAM}/commits/{BRANCH}"))
    sha = commit["sha"]
    tree = json.loads(fetch(f"https://api.github.com/repos/{UPSTREAM}/git/trees/{sha}?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("incomplete upstream file list")
    files = {}
    for entry in tree["tree"]:
        path = entry["path"]
        if path in {"Stash/Stash.yaml", "LICENSE"} or path.startswith("Stash/Rules/"):
            if entry["type"] == "tree":
                continue
            if entry["type"] != "blob" or entry["mode"] not in {"100644", "100755"}:
                raise ValueError("unsupported upstream file type")
            if ".." in PurePosixPath(path).parts or PurePosixPath(path).is_absolute():
                raise ValueError("unsafe upstream path")
            files[path] = entry
    if not {"Stash/Stash.yaml", "LICENSE"} <= files.keys():
        raise ValueError("missing source or license")
    def download(item):
        path, entry = item
        body = fetch(f"https://raw.githubusercontent.com/{UPSTREAM}/{sha}/" + urllib.parse.quote(path))
        blob = b"blob " + str(len(body)).encode() + b"\0" + body
        if hashlib.sha1(blob).hexdigest() != entry["sha"]:
            raise ValueError("upstream blob checksum mismatch: " + path)
        return path, body
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        content = dict(pool.map(download, sorted(files.items())))
    source = content.pop("Stash/Stash.yaml").decode()
    translated = translate(source, repository)
    config = yaml.safe_load(translated)
    prefix = f"https://raw.githubusercontent.com/{repository}/main/"
    for provider in config["rule-providers"].values():
        if urllib.parse.unquote(provider["url"].removeprefix(prefix)) not in content:
            raise ValueError("referenced rule file is missing")
    content["upstream/Stash.yaml"] = source.encode()
    content["Stash/Stash.yaml"] = translated.encode()
    manifest = {
        "upstream": UPSTREAM, "branch": BRANCH, "commit": sha,
        "committed_at": commit["commit"]["committer"]["date"],
        "source_url": f"https://github.com/{UPSTREAM}/commit/{sha}",
        "rules": {p: files[p]["sha"] for p in sorted(files) if p.startswith("Stash/Rules/")},
    }
    content["upstream/state.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    # Publish locally only after the entire snapshot passed download and validation.
    rules_dir = ROOT / "Stash/Rules"
    if rules_dir.exists():
        for path in rules_dir.rglob("*"):
            if path.is_file() and path.relative_to(ROOT).as_posix() not in content:
                path.unlink()
    for name, body in content.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != body:
            path.write_bytes(body)
    print(f"Synced {sha[:12]}: {len(manifest['rules'])} rule files, {len(config['proxy-groups'])} groups")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="kongjue/repcz-stash-zh")
    args = parser.parse_args()
    sync(args.repository)
