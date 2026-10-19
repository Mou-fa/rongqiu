r"""GitHub API 小工具。

绒球仓库在 https://github.com/Mou-fa/rongqiu

这个脚本让「看仓库状态」和「改仓库」都能一条命令完成，
不用每次去网页点。

token 查找顺序：
    1. 环境变量 GITHUB_TOKEN
    2. %USERPROFILE%\.rongqiu\github.token      （本机默认位置）
    3. 项目根目录 .github-token                  （已在 gitignore 里）

用法：
    python scripts/gh.py info
    python scripts/gh.py commits 10
    python scripts/gh.py files
    python scripts/gh.py issues
    python scripts/gh.py issue "标题" "正文"
    python scripts/gh.py release v0.1.0 "第一个公开版本"

注意：这个脚本不带任何写死的密钥。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

OWNER = "Mou-fa"
REPO = "rongqiu"
API = "https://api.github.com"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def token() -> str:
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env
    candidates = [
        pathlib.Path(os.path.expanduser("~")) / ".rongqiu" / "github.token",
        ROOT / ".github-token",
    ]
    for p in candidates:
        try:
            # utf-8-sig：Windows 的 Set-Content 会写 BOM，
            # 不剥掉的话 Authorization 头会带一个 \ufeff，请求直接崩。
            t = p.read_text(encoding="utf-8-sig").strip()
            if t:
                return t
        except OSError:
            continue
    return ""


def call(method: str, path: str, body: dict | None = None) -> dict | list:
    tok = token()
    if not tok:
        raise SystemExit("找不到 GitHub token。见本文件开头的查找顺序。")
    url = API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + tok,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "rongqiu-gh-tool",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"GitHub API {exc.code}: {detail}")


def cmd_info() -> None:
    d = call("GET", f"/repos/{OWNER}/{REPO}")
    print(f"{d['full_name']}")
    print(f"  描述   {d.get('description') or '（无）'}")
    print(f"  可见性 {'公开' if not d.get('private') else '私有'}")
    print(f"  分支   {d.get('default_branch')}")
    print(f"  星标   {d.get('stargazers_count')}   分叉 {d.get('forks_count')}")
    print(f"  大小   {d.get('size')} KB")
    print(f"  地址   {d.get('html_url')}")
    if d.get("license"):
        print(f"  协议   {d['license'].get('spdx_id')}")


def cmd_commits(n: int = 10) -> None:
    d = call("GET", f"/repos/{OWNER}/{REPO}/commits?per_page={n}")
    for c in d:
        sha = c["sha"][:7]
        msg = c["commit"]["message"].splitlines()[0]
        date = c["commit"]["author"]["date"][:10]
        print(f"{sha}  {date}  {msg}")


def cmd_files() -> None:
    d = call("GET", f"/repos/{OWNER}/{REPO}/contents/")
    for item in sorted(d, key=lambda x: (x["type"] != "dir", x["name"])):
        mark = "📁" if item["type"] == "dir" else "  "
        print(f"{mark} {item['name']}")


def cmd_issues() -> None:
    d = call("GET", f"/repos/{OWNER}/{REPO}/issues?state=open&per_page=20")
    if not d:
        print("没有打开的 issue。")
        return
    for i in d:
        print(f"#{i['number']}  {i['title']}")


def cmd_issue(title: str, body: str = "") -> None:
    d = call("POST", f"/repos/{OWNER}/{REPO}/issues",
             {"title": title, "body": body})
    print(f"已创建 issue #{d['number']}: {d['html_url']}")


def cmd_release(tag: str, name: str = "") -> None:
    d = call("POST", f"/repos/{OWNER}/{REPO}/releases",
             {"tag_name": tag, "name": name or tag,
              "body": "由 gh.py 创建", "draft": False, "prerelease": False})
    print(f"已创建 release {d['tag_name']}: {d['html_url']}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "info":
        cmd_info()
    elif cmd == "commits":
        cmd_commits(int(rest[0]) if rest else 10)
    elif cmd == "files":
        cmd_files()
    elif cmd == "issues":
        cmd_issues()
    elif cmd == "issue":
        if not rest:
            raise SystemExit('用法: gh.py issue "标题" ["正文"]')
        cmd_issue(rest[0], rest[1] if len(rest) > 1 else "")
    elif cmd == "release":
        if not rest:
            raise SystemExit('用法: gh.py release v0.1.0 ["名称"]')
        cmd_release(rest[0], rest[1] if len(rest) > 1 else "")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
