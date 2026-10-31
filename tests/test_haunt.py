"""Run: python tests/test_haunt.py   (no display needed; the ghost window is tested with Qt's offscreen mode)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HOME = tempfile.mkdtemp(prefix="haunt_test_")
os.environ["HAUNT_HOME"] = HOME
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import haunt  # noqa: E402

STATE = {"verdicts": [], "seen": []}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        last = body["messages"][-1]
        STATE["seen"].append(body)
        if body["model"] == "missing":
            self.send_response(404); self.end_headers(); self.wfile.write(b"{}"); return
        if "images" in last:
            assert body.get("format") == "json" and body["options"]["temperature"] == 0
            out = STATE["verdicts"].pop(0) if STATE["verdicts"] else '{"verdict":"unclear","evidence":"x"}'
        else:
            out = "  Do the task, mortal.\nSecond line"
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"message": {"role": "assistant", "content": out}}).encode())

    def log_message(self, *a):
        pass


SRV = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
HOST = f"127.0.0.1:{SRV.server_port}"


def fresh():
    p = haunt.tasks_path()
    if p.exists():
        p.unlink()
    STATE["verdicts"].clear(); STATE["seen"].clear()
    os.environ["OLLAMA_HOST"] = HOST
    haunt.MODEL = "gemma3:4b"


# ---------------------------------------------------------------- logic
def test_add_list_remove_and_concurrent_update():
    fresh()
    a = haunt.add_task("one"); b = haunt.add_task("two", every=5, first=0)
    assert (a["id"], b["id"]) == (1, 2) and b["next_haunt"] <= time.time() + 1
    haunt.add_task("added from another terminal")
    haunt.update_task(1, nags=3)            # the update must not drop task 3
    ts = haunt.load()
    assert len(ts) == 3 and ts[0]["nags"] == 3
    assert haunt.remove_task(2) and not haunt.remove_task(99) and len(haunt.load()) == 2


def test_file_proof():
    fresh()
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "report.md"
        t = haunt.add_task("write", proof=f"file:{f}")
        assert haunt.check_proof(t) == (False, "report.md does not exist yet")
        f.write_text("x")
        os.utime(f, (t["created"] - 100, t["created"] - 100))      # saved BEFORE the task was made
        assert haunt.check_proof(t)[0] is False
        os.utime(f, (t["created"] + 5, t["created"] + 5))
        assert haunt.check_proof(t) == (True, "report.md was saved")


def test_git_proof():
    fresh()
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@x", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@x"}
        subprocess.run(["git", "init", "-q", d], check=True, env=env)
        subprocess.run(["git", "-C", d, "commit", "-q", "--allow-empty", "-m", "old"], check=True, env=env)
        t = haunt.add_task("commit", proof=f"git:{d}")
        t["created"] = time.time() + 1                                  # the old commit is before the task
        assert haunt.check_proof(t)[0] is False
        t["created"] = time.time() - 3600
        assert haunt.check_proof(t) == (True, "a new commit landed")
    assert haunt.check_proof({"proof": "look", "created": 0}) == (False, "look")


def test_levels_and_verdict_parsing():
    assert [haunt.level_for(n) for n in (0, 1, 2, 3, 4, 9)] == [1, 1, 2, 2, 3, 3]
    assert haunt.parse_verdict('{"verdict":"DONE","evidence":"report open"}') == {"verdict": "done", "evidence": "report open"}
    assert haunt.parse_verdict('```json\n{"verdict":"not done","evidence":"youtube"}\n```')["verdict"] == "not_done"
    assert haunt.parse_verdict("rubbish")["verdict"] == "unclear"
    assert haunt.parse_verdict('{"verdict":"maybe"}')["verdict"] == "unclear"
    assert haunt.parse_verdict("[1,2]")["verdict"] == "unclear"


def test_voice_and_fallback():
    fresh()
    t = haunt.add_task("write the report")
    line, src = haunt.make_line(t, 2)
    assert src == "gemma" and line == "Do the task, mortal." and "\n" not in line   # first line only
    os.environ["OLLAMA_HOST"] = "127.0.0.1:1"
    line, src = haunt.make_line(t, 3)
    assert src == "fallback" and "write the report" in line


def test_judge_sends_image_and_errors_are_clear():
    fresh()
    STATE["verdicts"].append('{"verdict":"done","evidence":"Word open on the Conclusion"}')
    v = haunt.judge_screen({"title": "Finish report", "expect": "Word with a Conclusion"}, haunt.tiny_png())
    assert v == {"verdict": "done", "evidence": "Word open on the Conclusion"}
    msg = STATE["seen"][-1]["messages"][-1]
    assert len(msg["images"]) == 1 and "Word with a Conclusion" in msg["content"]
    haunt.MODEL = "missing"
    try:
        haunt.llm([{"role": "user", "content": "hi"}]); raise AssertionError("expected LLMError")
    except haunt.LLMError as e:
        assert "ollama pull missing" in str(e)
    os.environ["OLLAMA_HOST"] = "127.0.0.1:1"
    try:
        haunt.llm([{"role": "user", "content": "hi"}]); raise AssertionError("expected LLMError")
    except haunt.LLMError as e:
        assert "ollama serve" in str(e)


def test_cli_add_rejects_bad_proof():
    fresh()
    try:
        haunt.main(["add", "x", "--proof", "bogus"]); raise AssertionError("should exit")
    except SystemExit as e:
        assert "--proof" in str(e)
    haunt.main(["add", "ok task", "--every", "5", "--first", "0"])
    assert haunt.load()[0]["title"] == "ok task"


# ---------------------------------------------------------------- the ghost window, offscreen
def _qt():
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    import haunt_ui
    app = QApplication.instance() or QApplication([])
    return app, QTest, QPushButton, haunt_ui


def _wait(QTest, cond, secs=10):
    end = time.time() + secs
    while not cond() and time.time() < end:
        QTest.qWait(40)
    assert cond(), "timed out"


def _click(win, QPushButton, text):
    b = next(b for b in win.findChildren(QPushButton) if b.text().startswith(text))
    b.click()


class Args:
    snooze = 10.0
    quiet = True


def test_full_haunt_flow():
    fresh()
    app, QTest, QPushButton, ui = _qt()
    h = ui.Haunter(app, Args())
    h.timer.stop()
    t = haunt.add_task("Finish the report", expect="Word with a conclusion", every=5, first=0)
    h.poll()
    _wait(QTest, lambda: h.win is not None)
    assert "Do the task, mortal." in h.win.text.text()
    assert haunt.get_task(t["id"])["nags"] == 1
    # claim it while the screen shows something else: the ghost says what it sees and refuses
    STATE["verdicts"] += ['{"verdict":"not_done","evidence":"a YouTube video of cats"}',
                          '{"verdict":"done","evidence":"Word open on the conclusion"}']
    _click(h.win, QPushButton, "I did it")
    _wait(QTest, lambda: h.win is not None and "YouTube" in h.win.text.text())
    assert haunt.get_task(t["id"])["claims"] == 1 and haunt.get_task(t["id"])["status"] == "open"
    sent = [b for b in STATE["seen"] if "images" in b["messages"][-1]][0]
    assert len(sent["messages"][-1]["images"][0]) > 100                  # a real screenshot was attached
    _click(h.win, QPushButton, "I did it")
    _wait(QTest, lambda: haunt.get_task(t["id"])["status"] == "done")
    assert haunt.get_task(t["id"])["done_by"] == "look"
    _wait(QTest, lambda: h.win is not None and "Word open" in h.win.text.text())
    h.close_win()
    assert h.win is None and h.busy is False


def test_snooze_and_trust_button_and_file_proof():
    fresh()
    app, QTest, QPushButton, ui = _qt()
    h = ui.Haunter(app, Args()); h.timer.stop()
    a = haunt.add_task("Snoozer", every=5, first=0)
    h.poll(); _wait(QTest, lambda: h.win is not None)
    before = time.time()
    _click(h.win, QPushButton, "Snooze")
    t = haunt.get_task(a["id"])
    assert h.win is None and t["snoozes"] == 1 and t["next_haunt"] >= before + 9 * 60
    h.poll(); QTest.qWait(300)
    assert h.win is None, "a snoozed task must stay quiet"
    # two failed claims reveal the honour-system button
    STATE["verdicts"] += ['{"verdict":"not_done","evidence":"a desktop"}'] * 2
    haunt.update_task(a["id"], next_haunt=0)
    h.poll(); _wait(QTest, lambda: h.win is not None)
    for _ in range(2):
        _click(h.win, QPushButton, "I did it")
        _wait(QTest, lambda n=haunt.get_task(a["id"])["claims"]: haunt.get_task(a["id"])["claims"] > n and h.win is not None
              and h.win.isVisible())
    assert any(b.text() == "I swear I did" for b in h.win.findChildren(QPushButton))
    _click(h.win, QPushButton, "I swear")
    assert haunt.get_task(a["id"])["done_by"] == "trust"
    h.close_win()
    # a file task completes by itself, no AI involved
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "notes.txt"
        b = haunt.add_task("Write notes", proof=f"file:{f}", every=5, first=60)
        h.poll(); QTest.qWait(100)
        assert haunt.get_task(b["id"])["status"] == "open"
        f.write_text("done")
        os.utime(f, (b["created"] + 5, b["created"] + 5))
        h.poll(); QTest.qWait(100)
        assert haunt.get_task(b["id"])["status"] == "done" and haunt.get_task(b["id"])["done_by"] == "proof"
        h.close_win()


def test_fallback_voice_is_labelled_in_the_window():
    fresh()
    app, QTest, QPushButton, ui = _qt()
    os.environ["OLLAMA_HOST"] = "127.0.0.1:1"
    h = ui.Haunter(app, Args()); h.timer.stop()
    haunt.add_task("Offline task", every=5, first=0)
    h.poll(); _wait(QTest, lambda: h.win is not None)
    assert "Offline task" in h.win.text.text()
    from PySide6.QtWidgets import QLabel
    assert any("built-in" in l.text() for l in h.win.findChildren(QLabel))
    h.close_win()


def test_render_ghosts(out=os.environ.get("HAUNT_SHOTS")):
    app, QTest, QPushButton, ui = _qt()
    shots = []
    for name, level, mood, line in (("level1", 1, "haunt", "I drift here, waiting for 'Finish the report'."),
                                    ("level2", 2, "haunt", "The candles flicker. 'Finish the report' remains."),
                                    ("level3", 3, "haunt", "ENOUGH. 'Finish the report'. NOW."),
                                    ("look", 1, "look", "Hold still. Let me look at your screen..."),
                                    ("happy", 1, "happy", "I see it: Word open on the conclusion. Rest easy.")):
        w = ui.GhostWindow(line, level, mood, "voice: gemma3:4b", [("I did it", lambda: None), ("Snooze 10 min", lambda: None)])
        w.show(); QTest.qWait(60)
        img = w.grab()
        assert not img.isNull() and img.width() > 200
        if out:
            img.save(f"{out}/ghost_{name}.png")
        w.tick.stop(); w.close()


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                fails += 1; print("FAIL", name, type(e).__name__, e)
    SRV.shutdown()
    sys.exit(1 if fails else 0)
