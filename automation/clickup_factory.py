#!/usr/bin/env python3
"""
ClickUp -> GitHub Actions workflow factory.

Runs inside GitHub Actions, the only hop in this stack with network access to
both api.github.com and api.clickup.com.

Two input channels:

  1. ClickUp tasks tagged `create-workflow` in the watched List. The task
     description says what to build (a `template:` line, or a fenced ```yaml
     block with the workflow itself). The factory writes the workflow file,
     comments the links back on the task, then swaps the trigger tag for
     `workflow-created` so it never fires twice.

  2. Request files committed to automation/requests/*.json
       {"file": "release.yml", "template": "rust-release"}
       {"file": "ci.yml", "content": "<raw yaml>"}
     Content-compared, so re-runs are no-ops.

Writes into .github/workflows/ use a GitHub App installation token: the App
carries Workflows: read & write, which plain OAuth tokens do not.

Every outcome is also emitted as a GitHub Actions annotation, because the CI
log endpoint needs auth while the check-runs annotations API does not.

Env / secrets:
  APP_ID            GitHub App id                       (required)
  APP_PRIVATE_KEY   full .pem contents                  (required)
  INSTALLATION_ID   optional, auto-discovered if absent
  CLICKUP_TOKEN     ClickUp personal token pk_...        (optional)
  CLICKUP_LIST_ID   List watched for tagged tasks        (optional)
  TRIGGER_TAG       default: create-workflow
  DONE_TAG          default: workflow-created
  DONE_STATUS       optional, e.g. complete
  DRY_RUN           1 = plan only, write nothing
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

GH_API = "https://api.github.com"
CU_API = "https://api.clickup.com/api/v2"

REPO = os.environ.get("GITHUB_REPOSITORY", "supercubegame/zzview")
BRANCH = os.environ.get("TARGET_BRANCH", "main")
TRIGGER_TAG = os.environ.get("TRIGGER_TAG", "create-workflow").strip().lower()
DONE_TAG = os.environ.get("DONE_TAG", "workflow-created").strip().lower()
DONE_STATUS = os.environ.get("DONE_STATUS", "").strip()
REQUEST_DIR = "automation/requests"
DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
UA = "zzview-workflow-factory"


def log(msg):
    print(msg, flush=True)


def annotate(level, title, message):
    """Emit a GitHub Actions annotation.

    Annotations are readable through the public check-runs API, which is the
    only failure channel available to a caller that cannot authenticate
    against the CI log endpoint. Never pass secret values in here.
    """
    text = str(message).replace("\r", " ").replace("\n", "%0A")[:1200]
    print(f"::{level} title={title}::{text}", flush=True)


SECRET_KEYS = ("APP_ID", "APP_PRIVATE_KEY", "INSTALLATION_ID",
               "CLICKUP_TOKEN", "CLICKUP_LIST_ID")


def preflight():
    """Report which secrets arrived, by shape only - never by value."""
    pem = os.environ.get("APP_PRIVATE_KEY", "")
    report = {k: len(os.environ.get(k, "").strip()) for k in SECRET_KEYS}
    report["pem_has_header"] = "BEGIN" in pem and "PRIVATE KEY" in pem
    report["pem_newlines"] = pem.count("\n")
    report["pem_literal_backslash_n"] = "\\n" in pem
    annotate("notice", "factory preflight (lengths only)", json.dumps(report))

    missing = [k for k in ("APP_ID", "APP_PRIVATE_KEY")
               if not os.environ.get(k, "").strip()]
    if missing:
        annotate("error", "missing required secrets",
                 f"{', '.join(missing)} arrived empty. Add them under "
                 f"Settings > Secrets and variables > Actions, then re-run.")
        return False
    if not report["pem_has_header"]:
        annotate("error", "APP_PRIVATE_KEY malformed",
                 "No '-----BEGIN ... PRIVATE KEY-----' header found. Paste the "
                 ".pem file contents verbatim, including the BEGIN and END lines.")
        return False
    if not os.environ.get("APP_ID", "").strip().isdigit():
        annotate("error", "APP_ID malformed",
                 "APP_ID must be the numeric App ID (e.g. 4964810), not the Client ID.")
        return False
    return True


def http(method, url, token=None, data=None, scheme="Bearer", accept=None):
    headers = {"User-Agent": UA, "Accept": accept or "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"{scheme} {token}" if scheme else token
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, _maybe_json(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        return err.code, _maybe_json(err.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def _maybe_json(raw):
    raw = raw.strip()
    if raw[:1] in ("{", "["):
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return raw


def installation_token():
    import jwt  # PyJWT + cryptography, installed by the workflow

    app_id = os.environ["APP_ID"].strip()
    private_key = os.environ["APP_PRIVATE_KEY"]
    if "\\n" in private_key and "\n" not in private_key:
        private_key = private_key.replace("\\n", "\n")

    now = int(time.time())
    bearer = jwt.encode({"iss": app_id, "iat": now - 60, "exp": now + 540},
                        private_key, algorithm="RS256")
    if isinstance(bearer, bytes):
        bearer = bearer.decode()

    inst = os.environ.get("INSTALLATION_ID", "").strip()
    if not inst:
        status, data = http("GET", f"{GH_API}/app/installations", token=bearer)
        if status != 200 or not isinstance(data, list) or not data:
            raise SystemExit(f"cannot list installations ({status}): {data}")
        owner = REPO.split("/")[0].lower()
        match = next((i for i in data
                      if i.get("account", {}).get("login", "").lower() == owner), data[0])
        inst = str(match["id"])
        log(f"discovered installation id {inst}")

    status, data = http("POST", f"{GH_API}/app/installations/{inst}/access_tokens",
                        token=bearer)
    if status not in (200, 201) or not isinstance(data, dict) or not data.get("token"):
        raise SystemExit(f"installation token failed ({status}): {data}")
    return data["token"]


def get_file(token, path):
    url = f"{GH_API}/repos/{REPO}/contents/{urllib.parse.quote(path)}?ref={BRANCH}"
    status, data = http("GET", url, token=token)
    if status == 200 and isinstance(data, dict):
        try:
            text = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            text = ""
        return data.get("sha"), text
    return None, None


def put_file(token, path, content, message):
    sha, existing = get_file(token, path)
    if existing is not None and existing.strip() == content.strip():
        return "unchanged", f"https://github.com/{REPO}/blob/{BRANCH}/{path}"
    if DRY_RUN:
        return "dry-run", path
    payload = {"message": message,
               "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
               "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    status, data = http("PUT", f"{GH_API}/repos/{REPO}/contents/{urllib.parse.quote(path)}",
                        token=token, data=payload)
    if status in (200, 201) and isinstance(data, dict):
        return ("updated" if sha else "created"), data.get("commit", {}).get("html_url", "")
    return "error", f"{status}: {data}"


TEMPLATES = {}

TEMPLATES["rust-ci"] = """name: ci
on:
  push:
    branches: [ main ]
  pull_request:
  workflow_dispatch:
jobs:
  check:
    name: check ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ ubuntu-latest, macos-latest, windows-latest ]
    steps:
      - uses: actions/checkout@v4
      - name: Toolchain
        run: rustc --version && cargo --version
      - name: Linux GUI deps
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libx11-dev libxkbcommon-dev pkg-config
      - name: Resolve dependencies
        run: cargo generate-lockfile
      - name: Build
        run: cargo build --verbose
      - name: Test
        run: cargo test --verbose
"""

TEMPLATES["rust-release"] = """name: build-and-release
on:
  push:
    branches: [ main ]
  workflow_dispatch:
permissions:
  contents: write
jobs:
  version:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.v.outputs.tag }}
    steps:
      - uses: actions/checkout@v4
      - id: v
        name: Read version from Cargo.toml
        run: |
          VER=$(grep -m1 '^version' Cargo.toml | sed -E 's/.*"(.*)".*/\\1/')
          echo "tag=v${VER}" >> "$GITHUB_OUTPUT"
          echo "resolved v${VER}"
  build:
    needs: [ version ]
    name: build ${{ matrix.label }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-latest
            label: linux-x86_64
          - os: macos-latest
            label: macos-arm64
          - os: windows-latest
            label: windows-x86_64
    steps:
      - uses: actions/checkout@v4
      - name: Linux GUI deps
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libx11-dev libxkbcommon-dev pkg-config xvfb imagemagick x11-utils xdotool
      - name: Build release binary
        run: cargo build --release
      - name: Capture real screenshot
        if: runner.os == 'Linux'
        env:
          ICED_BACKEND: tiny-skia
          WGPU_BACKEND: gl
        run: |
          chmod +x scripts/demo.sh || true
          ./scripts/demo.sh || true
      - name: Stage artifacts
        shell: bash
        run: |
          mkdir -p dist
          BIN=$(basename "$GITHUB_REPOSITORY")
          if [ "${{ runner.os }}" = "Windows" ]; then
            cp "target/release/${BIN}.exe" "dist/${BIN}-${{ matrix.label }}.exe"
          else
            cp "target/release/${BIN}" "dist/${BIN}-${{ matrix.label }}"
          fi
          cp -r shots/* dist/ 2>/dev/null || true
          cp -r dist_shots/* dist/ 2>/dev/null || true
      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.label }}
          path: dist/*
  release:
    needs: [ version, build ]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - name: Flatten
        run: |
          mkdir -p dist
          find artifacts -type f -exec cp {} dist/ \\;
          ls -la dist
      - name: Publish ${{ needs.version.outputs.tag }}
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          TAG="${{ needs.version.outputs.tag }}"
          gh release delete "$TAG" --yes --cleanup-tag || true
          gh release create "$TAG" dist/* --title "$TAG" --notes "Automated build from ${GITHUB_SHA:0:7}."
"""

TEMPLATES["node-ci"] = """name: ci
on:
  push:
    branches: [ main ]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm install
      - run: npm test
"""

FENCE_RE = re.compile(r"```(?:ya?ml)?\s*\n(.*?)```", re.S)
FILE_RE = re.compile(r"(?im)^\s*(?:file|workflow)\s*[:=]\s*([\w.\-]+\.ya?ml)\s*$")
TEMPLATE_RE = re.compile(r"(?im)^\s*template\s*[:=]\s*([\w\-]+)\s*$")


def slugify(text, fallback="workflow"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (re.sub(r"-{2,}", "-", slug) or fallback)[:48]


def spec_from_text(text, default_name):
    text = text or ""
    name_match = FILE_RE.search(text)
    filename = name_match.group(1) if name_match else f"{slugify(default_name)}.yml"

    fences = [b.strip() for b in FENCE_RE.findall(text) if b.strip()]
    yaml_block = next((b for b in fences
                       if re.search(r"(?m)^\s*(name|on|jobs)\s*:", b)), None)
    if yaml_block:
        return filename, yaml_block + "\n", "inline-yaml"

    tmpl = TEMPLATE_RE.search(text)
    if tmpl:
        key = tmpl.group(1).strip().lower()
        if key in TEMPLATES:
            return filename, TEMPLATES[key], f"template:{key}"
        return None, None, f"unknown template '{key}' (have: {', '.join(sorted(TEMPLATES))})"
    return None, None, "no `template:` line and no ```yaml block found"


def process_requests(token):
    results = []
    if not os.path.isdir(REQUEST_DIR):
        return results
    for name in sorted(os.listdir(REQUEST_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(REQUEST_DIR, name), "r", encoding="utf-8") as fh:
                req = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            results.append({"request": name, "state": "error", "detail": f"bad json: {exc}"})
            continue
        for entry in (req if isinstance(req, list) else [req]):
            filename = entry.get("file") or f"{slugify(entry.get('name', ''))}.yml"
            content = entry.get("content")
            if not content:
                key = (entry.get("template") or "").strip().lower()
                content = TEMPLATES.get(key)
                if not content:
                    results.append({"request": name, "file": filename, "state": "error",
                                    "detail": f"unknown template '{key}'"})
                    continue
            path = f".github/workflows/{filename}"
            state, detail = put_file(token, path, content,
                                     entry.get("message") or f"factory: sync {filename}")
            log(f"[request] {name} -> {path}: {state} {detail}")
            results.append({"request": name, "file": path, "state": state, "detail": detail})
    return results


def clickup(method, path, data=None):
    return http(method, f"{CU_API}{path}", token=os.environ["CLICKUP_TOKEN"].strip(),
                data=data, scheme=None, accept="application/json")


def comment(task_id, text):
    if DRY_RUN:
        log(f"[dry-run] comment on {task_id}: {text[:70]}")
        return
    status, _ = clickup("POST", f"/task/{task_id}/comment",
                        data={"comment_text": text, "notify_all": False})
    if status not in (200, 201):
        log(f"[clickup] comment on {task_id} failed ({status})")


def process_clickup(token):
    results = []
    if not os.environ.get("CLICKUP_TOKEN", "").strip() or not os.environ.get("CLICKUP_LIST_ID", "").strip():
        log("[clickup] token/list not configured - task channel idle")
        annotate("notice", "clickup channel idle",
                 "CLICKUP_TOKEN / CLICKUP_LIST_ID not set, so no tasks were polled.")
        return results
    list_id = os.environ["CLICKUP_LIST_ID"].strip()
    status, data = clickup("GET", f"/list/{list_id}/task?include_closed=false&subtasks=true")
    if status != 200 or not isinstance(data, dict):
        log(f"[clickup] cannot read list {list_id} ({status}): {data}")
        annotate("error", "clickup list unreadable",
                 f"GET /list/{list_id}/task returned {status}. Check CLICKUP_TOKEN scope "
                 f"and that CLICKUP_LIST_ID is the numeric List id.")
        return [{"state": "error", "detail": f"clickup list read {status}"}]

    tasks = data.get("tasks", [])
    log(f"[clickup] {len(tasks)} open tasks in list {list_id}")
    annotate("notice", "clickup polled",
             f"{len(tasks)} open tasks in list {list_id}, looking for tag '{TRIGGER_TAG}'")
    for task in tasks:
        tags = [t.get("name", "").lower() for t in task.get("tags", [])]
        if TRIGGER_TAG not in tags:
            continue
        tid, title = task.get("id"), task.get("name", "")
        desc = task.get("description") or task.get("text_content") or ""
        log(f"[clickup] trigger on {tid} '{title}'")

        filename, content, source = spec_from_text(desc, title)
        if not content:
            comment(tid, f":warning: Workflow factory could not read a spec here.\n\n{source}\n\n"
                         f"Add a line like `template: rust-release` (options: "
                         f"{', '.join(sorted(TEMPLATES))}) or paste a fenced yaml block.")
            results.append({"task": tid, "state": "error", "detail": source})
            continue

        path = f".github/workflows/{filename}"
        state, detail = put_file(token, path, content,
                                 f"factory: {filename} from ClickUp task {tid}")
        log(f"[clickup] {tid} -> {path}: {state} {detail}")
        results.append({"task": tid, "title": title, "file": path, "state": state,
                        "detail": detail, "source": source})

        if state in ("created", "updated", "unchanged", "dry-run"):
            blob = f"https://github.com/{REPO}/blob/{BRANCH}/{path}"
            comment(tid, f":white_check_mark: Workflow **{filename}** {state} ({source}).\n\n"
                         f"File: {blob}\nRuns: https://github.com/{REPO}/actions\n"
                         + (f"Commit: {detail}" if str(detail).startswith("http") else ""))
            if not DRY_RUN:
                clickup("POST", f"/task/{tid}/tag/{urllib.parse.quote(DONE_TAG)}/")
                clickup("DELETE", f"/task/{tid}/tag/{urllib.parse.quote(TRIGGER_TAG)}/")
                if DONE_STATUS:
                    clickup("PUT", f"/task/{tid}", data={"status": DONE_STATUS})
        else:
            comment(tid, f":x: Workflow **{filename}** failed.\n\n```\n{detail}\n```")
    return results


def main():
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log(f"workflow-factory start {started} repo={REPO} dry_run={DRY_RUN}")

    if not preflight():
        sys.exit(1)

    try:
        token = installation_token()
    except SystemExit as exc:
        annotate("error", "GitHub App auth failed", exc)
        raise
    except Exception as exc:  # noqa: BLE001
        annotate("error", "GitHub App auth crashed",
                 f"{type(exc).__name__}: {exc}")
        sys.exit(1)
    log("installation token acquired")
    annotate("notice", "auth ok", "installation token acquired")

    try:
        results = process_requests(token) + process_clickup(token)
    except Exception as exc:  # noqa: BLE001
        annotate("error", "factory crashed", f"{type(exc).__name__}: {exc}")
        raise

    summary = {"started_at": started,
               "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "repo": REPO,
               "run_url": f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
               "dry_run": DRY_RUN,
               "results": results}
    log("--- summary ---")
    log(json.dumps(summary, indent=2, ensure_ascii=False))

    for res in results:
        target = res.get("file") or res.get("task") or res.get("request") or "?"
        line = f"{target}: {res.get('state')} {res.get('detail', '')}"
        annotate("error" if res.get("state") == "error" else "notice",
                 "factory result", line)
    if not results:
        annotate("notice", "factory result",
                 "nothing to do: no request files matched and no tagged tasks found")

    if results and not DRY_RUN:
        state, detail = put_file(token, "automation/log/last-run.json",
                                 json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                 "factory: log last run")
        annotate("notice", "run log", f"automation/log/last-run.json {state}")

    if any(r.get("state") == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
