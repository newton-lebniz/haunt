#!/usr/bin/env python3
"""Haunt: a small ghost that haunts your screen until it can SEE your task is done.

The ghost's voice and its eyes are a local Gemma model served by Ollama.
Your screen is only ever sent to localhost, never to a server.

  python haunt.py check
  python haunt.py add "Finish the CS213 report" --proof file:~/cs213/report.pdf
  python haunt.py add "Open the lab and solve problem 3" --expect "A code editor with problem 3 solved and tests passing"
  python haunt.py run
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

MODEL = os.environ.get("HAUNT_MODEL", "gemma3:4b")


# ------------------------------------------------------------------ storage
def data_dir() -> Path:
    d = Path(os.environ.get("HAUNT_HOME") or Path.home() / ".haunt")
    d.mkdir(parents=True, exist_ok=True)
    return d


def tasks_path() -> Path:
    return data_dir() / "tasks.json"


def load() -> list[dict]:
    p = tasks_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(tasks: list[dict]) -> None:
    p = tasks_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def add_task(title: str, proof: str = "look", expect: str = "", every: float = 20, first: float | None = None) -> dict:
    tasks = load()
    now = time.time()
    t = {"id": max([x["id"] for x in tasks], default=0) + 1, "title": title.strip(), "proof": proof, "expect": expect.strip(),
         "created": now, "every": float(every), "next_haunt": now + 60 * (every if first is None else first),
         "status": "open", "nags": 0, "snoozes": 0, "claims": 0, "done_by": "", "done_at": 0}
    _save(tasks + [t])
    return t


def get_task(tid: int) -> dict | None:
    return next((t for t in load() if t["id"] == tid), None)


def update_task(tid: int, **fields) -> None:
    """Re-read the file, change one task, write back. So a task added from another terminal is never lost."""
    tasks = load()
    for t in tasks:
        if t["id"] == tid:
            t.update(fields)
    _save(tasks)


def remove_task(tid: int) -> bool:
    tasks = load()
    keep = [t for t in tasks if t["id"] != tid]
    _save(keep)
    return len(keep) != len(tasks)


# ------------------------------------------------------------------ proof (no AI needed)
def check_proof(t: dict) -> tuple[bool, str]:
    """file:PATH is satisfied when that file is saved after the task was created.
    git:REPO is satisfied when a commit lands in that repo after the task was created.
    Anything else ('look') can only be settled by the ghost's eyes, see judge_screen()."""
    proof = t.get("proof", "look")
    if proof.startswith("file:"):
        p = Path(proof[5:]).expanduser()
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return False, f"{p.name} does not exist yet"
        if mtime > t["created"]:
            return True, f"{p.name} was saved"
        return False, f"{p.name} has not been saved since you made this task"
    if proof.startswith("git:"):
        repo = Path(proof[4:]).expanduser()
        try:
            r = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct"], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return False, "git is not available"
        out = r.stdout.strip()
        if r.returncode == 0 and out.isdigit() and int(out) > t["created"]:
            return True, "a new commit landed"
        return False, f"no new commit in {repo.name}"
    return False, "look"


def level_for(nags: int) -> int:
    """The longer you ignore the ghost, the angrier it gets: 1 whisper, 2 eerie, 3 furious."""
    return 1 if nags < 2 else 2 if nags < 4 else 3


# ------------------------------------------------------------------ the local model
class LLMError(Exception):
    pass


def llm(messages: list[dict], fmt: str | None = None, temperature: float = 0.8, num_predict: int = 80, timeout: int = 60) -> str:
    host = os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if "://" not in host:
        host = "http://" + host
    host = host.replace("0.0.0.0", "localhost").rstrip("/")
    body = {"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_predict": num_predict}}
    if fmt:
        body["format"] = fmt
    req = urllib.request.Request(host + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LLMError(f"Ollama does not have '{MODEL}'. Run: ollama pull {MODEL}  (or set HAUNT_MODEL to a tag from `ollama list`)") from e
        raise LLMError(f"Ollama error {e.code}: {e.read().decode(errors='replace')[:200]}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise LLMError(f"Cannot reach Ollama at {host}. Open the Ollama app, or run `ollama serve`.") from e
    except (KeyError, ValueError) as e:
        raise LLMError(f"Unexpected reply from Ollama: {e}") from e


VOICE_SYS = (
    "You are a small, theatrical ghost haunting someone's computer until they finish one task. "
    "Write exactly ONE line of at most 22 words, spoken to them, in character. "
    "Level 1: wistful and gentle. Level 2: eerie and pointed. Level 3: furious and dramatic, but funny. "
    "Never cruel. Never about their body, their grades or their worth. Mention the task. "
    "No emoji, no hashtags, no quotation marks, no stage directions."
)

FALLBACK = {
    1: ["I drift here, waiting for '{task}'.", "A small cold draught reminds you about '{task}'.", "Psst. '{task}' is still waiting."],
    2: ["'{task}' is still undone. I can wait. I have all eternity.", "The candles flicker. '{task}' remains.",
        "I have haunted this screen for a while now. '{task}'."],
    3: ["ENOUGH. '{task}'. NOW.", "I am the ghost of '{task}', and I will not rest!", "Do '{task}' or I move into your wallpaper forever!"],
}


def clean_line(text: str) -> str:
    text = text.strip().splitlines()[0] if text.strip() else ""
    return text.strip().strip("\"'“”").strip()[:170]


def make_line(t: dict, level: int) -> tuple[str, str]:
    """Returns (line, source). source is 'gemma' or 'fallback' so the UI can say which voice you are hearing."""
    mins = int((time.time() - t["created"]) / 60)
    user = (f"Level: {level}\nTask: {t['title']}\nMinutes since the task was made: {mins}\n"
            f"Times already haunted: {t['nags']}\nTimes snoozed: {t['snoozes']}")
    try:
        line = clean_line(llm([{"role": "system", "content": VOICE_SYS}, {"role": "user", "content": user}],
                              temperature=0.9, num_predict=70, timeout=45))
        if line:
            return line, "gemma"
    except LLMError as e:
        print(f"[haunt] using built-in lines: {e}", file=sys.stderr)
    return random.choice(FALLBACK[level]).format(task=t["title"]), "fallback"


# ------------------------------------------------------------------ the ghost's eyes
JUDGE_SYS = (
    "You are a strict but fair inspector. You are shown one screenshot and one task. "
    "Decide whether the screenshot shows clear evidence that the task is finished. Only trust what is visibly on screen. "
    "Reply with JSON only: {\"verdict\": \"done\" or \"not_done\" or \"unclear\", \"evidence\": \"one short sentence naming what you actually see\"}."
)


def parse_verdict(text: str) -> dict:
    obj = None
    try:
        obj = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except ValueError:
                obj = None
    if not isinstance(obj, dict):
        return {"verdict": "unclear", "evidence": "the model did not answer in a way I could read"}
    v = str(obj.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
    return {"verdict": v if v in ("done", "not_done", "unclear") else "unclear", "evidence": str(obj.get("evidence", "")).strip()[:200]}


def judge_screen(t: dict, jpeg: bytes) -> dict:
    """Ask the local vision model whether the screenshot shows the task done. Only 'done' counts."""
    want = f"What the screen should show if it is finished: {t['expect']}\n" if t.get("expect") else ""
    user = f"Task: {t['title']}\n{want}The person says it is done. Does this screenshot show that?"
    msg = {"role": "user", "content": user, "images": [base64.b64encode(jpeg).decode()]}
    return parse_verdict(llm([{"role": "system", "content": JUDGE_SYS}, msg], fmt="json", temperature=0, num_predict=120, timeout=240))


def tiny_png(size: int = 64) -> bytes:
    """A plain white PNG, no imaging library needed. Used by `check` to test that the model accepts images."""
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * size for _ in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ command line
def cmd_check(a):
    print(f"Model: {MODEL}")
    try:
        print("text :", llm([{"role": "user", "content": "Say 'boo' in one word."}], num_predict=10, timeout=120) or "(empty)")
    except LLMError as e:
        sys.exit(f"FAILED: {e}")
    try:
        msg = {"role": "user", "content": "Describe this image in five words.", "images": [base64.b64encode(tiny_png()).decode()]}
        print("vision:", llm([msg], num_predict=30, timeout=240) or "(empty)")
    except LLMError as e:
        sys.exit(f"Text works but vision FAILED: {e}\nThe ghost needs a vision-capable model (gemma3:4b is).")
    print("\nOK. The ghost can speak and see.")


def cmd_add(a):
    proof = a.proof
    if proof.startswith("file:"):
        proof = "file:" + str(Path(proof[5:]).expanduser().resolve())
    elif proof.startswith("git:"):
        repo = Path(proof[4:]).expanduser().resolve()
        if not (repo / ".git").exists():
            sys.exit(f"{repo} is not a git repo")
        proof = "git:" + str(repo)
    elif proof != "look":
        sys.exit("--proof must be 'look', 'file:PATH' or 'git:REPO'")
    t = add_task(a.title, proof, a.expect or "", a.every, a.first)
    first = a.every if a.first is None else a.first
    print(f"Task {t['id']} added. The ghost first appears in {first:g} min, then every {a.every:g} min. Proof: {proof}")


def cmd_list(a):
    tasks = load()
    if not tasks:
        print("No tasks. Add one with: python haunt.py add \"...\"")
    for t in tasks:
        print(f"{t['id']:>3}  {t['status']:<5}  {t['title']}   [{t['proof']}]  haunted {t['nags']}x, snoozed {t['snoozes']}x"
              + (f", done by {t['done_by']}" if t["status"] == "done" else ""))


def cmd_rm(a):
    print("removed" if remove_task(a.id) else f"no task {a.id}")


def cmd_judge(a):
    """Try the ghost's eyes on a screenshot file. Handy for measuring how often it is right."""
    t = {"title": a.task, "expect": a.expect or ""}
    print(json.dumps(judge_screen(t, Path(a.image).read_bytes()), indent=2))


def cmd_run(a):
    try:
        import haunt_ui
    except ImportError as e:
        sys.exit(f"Cannot start the ghost window: {e}\nInstall it with: pip install PySide6")
    haunt_ui.main(a)


def main(argv=None):
    global MODEL
    ap = argparse.ArgumentParser(prog="haunt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help=f"Ollama model tag (default {MODEL}); must support images")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check", help="test that Ollama and the model can speak and see"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("add", help="add a task to haunt you")
    s.add_argument("title")
    s.add_argument("--proof", default="look", help="'look' (the ghost checks your screen), 'file:PATH' or 'git:REPO'")
    s.add_argument("--expect", help="what the screen should show when it is done (helps the ghost's eyes)")
    s.add_argument("--every", type=float, default=20, help="minutes between hauntings (default 20)")
    s.add_argument("--first", type=float, help="minutes until the first haunting (default: same as --every; 0 = right away)")
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("list", help="show tasks"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("rm", help="delete a task"); s.add_argument("id", type=int); s.set_defaults(fn=cmd_rm)
    s = sub.add_parser("judge", help="ask the ghost's eyes about a screenshot file")
    s.add_argument("--task", required=True); s.add_argument("--expect"); s.add_argument("--image", required=True)
    s.set_defaults(fn=cmd_judge)
    s = sub.add_parser("run", help="start haunting (keep this running; Ctrl+C to stop)")
    s.add_argument("--snooze", type=float, default=10, help="minutes a snooze lasts (default 10)")
    s.add_argument("--quiet", action="store_true", help="no sound")
    s.set_defaults(fn=cmd_run)
    a = ap.parse_args(argv)
    if a.model:
        MODEL = a.model
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    a.fn(a)


if __name__ == "__main__":
    main()
