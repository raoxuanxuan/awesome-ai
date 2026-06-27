#!/usr/bin/env python3
"""Run current qmx_user_asset lyric cleanup code against a raw LRC file."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


def read_module(repo: Path) -> str:
    go_mod = repo / "go.mod"
    for line in go_mod.read_text(encoding="utf-8").splitlines():
        if line.startswith("module "):
            return line.split(None, 1)[1].strip()
    raise ValueError(f"module line not found in {go_mod}")


def build_runner(module: str) -> str:
    return textwrap.dedent(
        f'''
        package main

        import (
            "context"
            "encoding/json"
            "fmt"
            "os"
            "strconv"

            "{module}/common"
        )

        type Result struct {{
            Function string `json:"function"`
            LyricStartTime int64 `json:"lyric_start_time"`
            OK bool `json:"ok"`
            Txt string `json:"txt"`
        }}

        func main() {{
            if len(os.Args) != 3 {{
                fmt.Fprintln(os.Stderr, "usage: runner <lrc-file> <lyric-start-time>")
                os.Exit(2)
            }}
            lrcBytes, err := os.ReadFile(os.Args[1])
            if err != nil {{
                panic(err)
            }}
            lyricStartTime, err := strconv.ParseInt(os.Args[2], 10, 64)
            if err != nil {{
                panic(err)
            }}
            var txt string
            var ok bool
            fn := "common.LrcToTxt"
            if lyricStartTime > 0 {{
                fn = "common.ClearLyricHeader"
                txt, ok = common.ClearLyricHeader(context.Background(), string(lrcBytes), lyricStartTime)
            }} else {{
                txt, ok = common.LrcToTxt(context.Background(), string(lrcBytes))
            }}
            out, err := json.MarshalIndent(Result{{
                Function: fn,
                LyricStartTime: lyricStartTime,
                OK: ok,
                Txt: txt,
            }}, "", "  ")
            if err != nil {{
                panic(err)
            }}
            fmt.Println("__QMX_LYRIC_DIAG_JSON__")
            fmt.Println(string(out))
        }}
        '''
    ).strip() + "\n"


def first_lines(text: str, limit: int = 20) -> list[str]:
    return text.splitlines()[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="/Users/saberrao/work/vemus/qmx_user_asset", help="qmx_user_asset repo path.")
    parser.add_argument("--lrc-file", required=True, help="Raw LRC file extracted from online logs.")
    parser.add_argument("--lyric-start-time", type=int, default=0, help="Online lyric_start_time.")
    parser.add_argument("--go-bin", default=shutil.which("go") or "go", help="Go binary.")
    parser.add_argument("--timeout", type=int, default=120, help="go run timeout in seconds.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    lrc_file = Path(args.lrc_file).resolve()
    module = read_module(repo)

    with tempfile.TemporaryDirectory(prefix="qmx-lyric-diag-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "go.mod").write_text(
            f"module qmxlyricdiag\n\ngo 1.24.1\n\nrequire {module} v0.0.0\n\nreplace {module} => {repo}\n",
            encoding="utf-8",
        )
        (tmp_path / "main.go").write_text(build_runner(module), encoding="utf-8")
        cmd = [args.go_bin, "run", "-mod=mod", ".", str(lrc_file), str(args.lyric_start_time)]
        proc = subprocess.run(
            cmd,
            cwd=tmp_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
        )
    if proc.returncode != 0:
        print(json.dumps({
            "repo": str(repo),
            "module": module,
            "ok": False,
            "error": "go run failed",
            "stderr": proc.stderr[-4000:],
        }, ensure_ascii=False, indent=2))
        return proc.returncode

    marker = "__QMX_LYRIC_DIAG_JSON__"
    stdout = proc.stdout
    if marker in stdout:
        stdout = stdout.split(marker, 1)[1].strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        print(proc.stdout)
        return 0
    txt = payload.get("txt")
    if isinstance(txt, str):
        payload["txt_char_len"] = len(txt)
        payload["txt_byte_len"] = len(txt.encode("utf-8"))
        payload["first_lines"] = first_lines(txt)
    payload["repo"] = str(repo)
    payload["module"] = module
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
