"""The ghost window (PySide6). The logic lives in haunt.py; this file only draws and clicks."""
from __future__ import annotations

import math
import random
import signal
import subprocess
import threading
import time

from PySide6.QtCore import (QBuffer, QByteArray, QEasingCurve, QIODevice, QObject, QPointF, QPropertyAnimation, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import haunt

def speak_windows(text: str) -> None:
    """Speak ghost dialogue through Windows' built-in offline TTS."""
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Add-Type -AssemblyName System.Speech; "
             "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
             "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"],
            input=text, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=45, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


CARD_CSS = """
#card{background:#2a1950;border:2px solid #f7a11a;border-radius:14px}
QLabel{color:#f4ead8}
#src{color:#b9a9d6}
QPushButton{background:#3a2470;color:#f4ead8;border:1px solid #f7a11a;border-radius:8px;padding:6px 12px}
QPushButton:hover{background:#4b3590}
#primary{background:#f7a11a;color:#1b1035;font-weight:bold}
#primary:hover{background:#ffc233}
"""


def grab_screen_jpeg(max_side: int = 1280) -> bytes:
    """Screenshot of the primary screen, shrunk. It goes to Ollama on localhost and nowhere else."""
    img = QGuiApplication.primaryScreen().grabWindow(0).toImage()
    if max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPEG", 70)
    return bytes(ba)


class GhostArt(QWidget):
    """The ghost, painted in a 200x230 box and scaled. mood: haunt, look or happy."""

    def __init__(self, level: int = 1, mood: str = "haunt"):
        super().__init__()
        self.level, self.mood, self.phase = level, mood, random.random() * 6
        self.scale = (1.0, 1.2, 1.4)[level - 1] if mood == "haunt" else 1.0
        self.setFixedSize(int(200 * self.scale), int(230 * self.scale))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.scale, self.scale)
        shake = random.uniform(-3, 3) if (self.level == 3 and self.mood == "haunt") else 0
        p.translate(shake, math.sin(self.phase) * 6 + 8)
        glow = QRadialGradient(100, 105, 105)
        glow.setColorAt(0, QColor(170, 150, 255, 120))
        glow.setColorAt(1, QColor(170, 150, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(100, 105), 105, 105)
        body = QPainterPath()
        body.moveTo(35, 105)
        body.cubicTo(35, 5, 165, 5, 165, 105)
        body.lineTo(165, 185)
        x = 165.0
        for i in range(4):
            body.quadTo(x - 16.25, 185 + (26 if i % 2 == 0 else -10), x - 32.5, 185)
            x -= 32.5
        body.closeSubpath()
        p.setPen(QPen(QColor("#c9c2ff"), 2))
        p.setBrush(QColor("#f6f4ff"))
        p.drawPath(body)
        furious = self.level == 3 and self.mood == "haunt"
        if self.mood == "happy":
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#1b1035"), 4, Qt.SolidLine, Qt.RoundCap))
            for cx in (70, 130):
                p.drawArc(cx - 14, 66, 28, 24, 20 * 16, 140 * 16)
            p.drawArc(78, 98, 44, 34, 200 * 16, 140 * 16)
            return
        look = math.sin(self.phase * 1.3) * 5 if self.mood == "look" else 0
        r = 15 if self.mood == "look" else (12 if self.level < 3 else 11)
        for cx in (70, 130):
            if self.mood == "look":
                p.setPen(QPen(QColor("#1b1035"), 2))
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(cx, 80), r + 4, r + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#d4163c") if furious else QColor("#1b1035"))
            p.drawEllipse(QPointF(cx + look, 80), r if self.mood != "look" else 8, r + (3 if self.mood != "look" else 0))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(cx + look - 4, 75), 3, 3)
        if furious:
            p.setPen(QPen(QColor("#1b1035"), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(50, 55, 88, 70)
            p.drawLine(150, 55, 112, 70)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1b1035"))
        mw, mh = (20, 22) if self.level == 1 else (30, 34) if self.level == 2 else (44, 40)
        if self.mood == "look":
            mw, mh = 18, 8
        p.drawEllipse(QPointF(100, 122), mw / 2, mh / 2)


class GhostWindow(QWidget):
    """Frameless, see-through, always on top, and it never steals keyboard focus from what you are typing."""

    def __init__(self, line: str, level: int, mood: str, source: str, buttons: list, quiet: bool = True):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.level = level
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.art = GhostArt(level, mood)
        lay.addWidget(self.art, alignment=Qt.AlignHCenter)
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(CARD_CSS)
        card.setFixedWidth(310)
        cl = QVBoxLayout(card)
        self.text = QLabel(line)
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignCenter)
        font = QFont("Georgia", 13 if level < 3 else 15)
        font.setItalic(True)
        self.text.setFont(font)
        cl.addWidget(self.text)
        if source:
            note = QLabel(source)
            note.setObjectName("src")
            note.setAlignment(Qt.AlignCenter)
            note.setFont(QFont("Georgia", 9))
            cl.addWidget(note)
        if buttons:
            row = QHBoxLayout()
            for i, (label, cb) in enumerate(buttons):
                b = QPushButton(label)
                if i == 0:
                    b.setObjectName("primary")
                b.clicked.connect(cb)
                row.addWidget(b)
            cl.addLayout(row)
        lay.addWidget(card, alignment=Qt.AlignHCenter)
        self.adjustSize()
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._bob)
        self.tick.start(40)
        self.fade = None
        self.quiet = quiet

    def _bob(self):
        self.art.phase += 0.22 if self.level < 3 else 0.4
        self.art.update()

    def appear(self, corner: bool):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if corner:
            x, y = screen.right() - self.width() - 24, screen.bottom() - self.height() - 24
        else:
            x = random.randint(screen.left(), max(screen.left(), screen.right() - self.width()))
            y = random.randint(screen.top(), max(screen.top(), screen.bottom() - self.height()))
        self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()
        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(700)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade.start()
        if self.level >= 2 and not self.quiet:
            threading.Thread(target=speak_windows, args=(self.text.text(),), daemon=True).start()


class Haunter(QObject):
    got_line = Signal(dict, int, str, str)
    got_verdict = Signal(int, dict)

    def __init__(self, app: QApplication, args):
        super().__init__()
        self.app, self.args = app, args
        self.win: GhostWindow | None = None
        self.busy = False
        self.got_line.connect(self.on_line)
        self.got_verdict.connect(self.on_verdict)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(5000)
        QTimer.singleShot(300, self.poll)

    # ---- scheduling
    def poll(self):
        now = time.time()
        for t in haunt.load():
            if t["status"] != "open":
                continue
            ok, how = haunt.check_proof(t)
            if ok:
                self.finish(t, "proof", f"I can see it: {how}. I am free.")
                return
            if self.win is None and not self.busy and now >= t["next_haunt"]:
                self.busy = True
                level = haunt.level_for(t["nags"])
                threading.Thread(target=self._voice, args=(t, level), daemon=True).start()
                return

    def _voice(self, t, level):
        line, src = haunt.make_line(t, level)
        self.got_line.emit(t, level, line, src)

    # ---- showing the ghost
    def show(self, t, line, level=1, mood="haunt", src="", buttons=None, corner=False):
        self.close_win(keep_busy=True)
        self.win = GhostWindow(line, level, mood, src, buttons or [], quiet=self.args.quiet)
        self.win.appear(corner or level == 1)

    def close_win(self, keep_busy: bool = False):
        if self.win is not None:
            self.win.tick.stop()
            self.win.close()
            self.win.deleteLater()
            self.win = None
        if not keep_busy:
            self.busy = False

    def haunt_buttons(self, t, claims_failed=False):
        b = [("I did it", lambda: self.claim(t["id"])), (f"Snooze {self.args.snooze:g} min", lambda: self.snooze(t["id"]))]
        if claims_failed:
            b.append(("I swear I did", lambda: self.finish(haunt.get_task(t["id"]) or t, "trust", "Taken on trust. I will remember.")))
        return b

    def on_line(self, t, level, line, src):
        fresh = haunt.get_task(t["id"]) or t
        haunt.update_task(t["id"], nags=fresh["nags"] + 1, next_haunt=time.time() + 60 * fresh["every"])
        tag = f"voice: {haunt.MODEL}" if src == "gemma" else "voice: built-in (Ollama not reachable)"
        self.show(fresh, line, level, "haunt", tag, self.haunt_buttons(fresh, fresh.get("claims", 0) >= 2))

    def snooze(self, tid):
        t = haunt.get_task(tid)
        if t:
            haunt.update_task(tid, snoozes=t["snoozes"] + 1, next_haunt=time.time() + 60 * self.args.snooze)
        self.close_win()

    # ---- the claim: "I did it"
    def claim(self, tid):
        t = haunt.get_task(tid)
        if not t:
            return self.close_win()
        if t["proof"] != "look":
            ok, how = haunt.check_proof(t)
            if ok:
                return self.finish(t, "proof", f"I can see it: {how}. I am free.")
            return self.show(t, f"Nothing yet: {how}.", haunt.level_for(t["nags"]), "haunt", "", self.haunt_buttons(t, t["claims"] >= 2))
        self.show(t, "Hold still. Let me look at your screen...", 1, "look", "", [], corner=True)
        QTimer.singleShot(700, lambda: self._look(t))

    def _look(self, t):
        if self.win:
            self.win.hide()          # so the ghost does not photograph itself
        QTimer.singleShot(450, lambda: self._shoot(t))

    def _shoot(self, t):
        try:
            jpeg = grab_screen_jpeg()
        except Exception as e:  # noqa: BLE001
            return self.got_verdict.emit(t["id"], {"verdict": "error", "evidence": f"I could not take a screenshot ({e})"})

        def work():
            try:
                v = haunt.judge_screen(t, jpeg)
            except haunt.LLMError as e:
                v = {"verdict": "error", "evidence": str(e)}
            self.got_verdict.emit(t["id"], v)

        threading.Thread(target=work, daemon=True).start()

    def on_verdict(self, tid, v):
        t = haunt.get_task(tid)
        if not t:
            return self.close_win()
        if v["verdict"] == "done":
            return self.finish(t, "look", f"I see it: {v['evidence']}. Rest easy.")
        failed = t["claims"] + (2 if v["verdict"] == "error" else 1)
        haunt.update_task(tid, claims=failed)
        t["claims"] = failed
        if v["verdict"] == "error":
            line = f"My eyes failed: {v['evidence']}"
        else:
            line = f"I see: {v['evidence'] or 'nothing that looks like it'}. That is not '{t['title']}'."
        self.show(t, line, max(2, haunt.level_for(t["nags"])), "haunt", "", self.haunt_buttons(t, failed >= 2))

    # ---- release
    def finish(self, t, how, line):
        haunt.update_task(t["id"], status="done", done_by=how, done_at=time.time())
        self.show(t, line, 1, "happy", "", [], corner=True)
        QTimer.singleShot(7000, self.close_win)


def main(args):
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # let Ctrl+C stop the app
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    h = Haunter(app, args)  # noqa: F841  (kept alive by the event loop)
    print(f"Haunting. Model: {haunt.MODEL}. Tasks file: {haunt.tasks_path()}. Press Ctrl+C to stop.")
    app.exec()
