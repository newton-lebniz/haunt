# Haunt

A small ghost that haunts your screen until it can **see** your task is done.
Its voice and its eyes are a local Gemma model run by Ollama. Your screen only ever goes to `localhost`.

- Add a task. Every N minutes the ghost fades in on top of whatever you are doing, with a line from Gemma.
- The longer you ignore it, the angrier it gets (whisper, eerie, furious).
- Click **I did it** and the ghost looks at your screen. If it does not see the work, it tells you what it does see
  ("I see a YouTube video of cats. That is not 'Finish the report'.") and stays.
- Tasks tied to a file or a git repo finish on their own the moment you save the file or commit. No AI involved.
- After two failed claims, an honour-system button appears, so a wrong judgement never traps you.

## Today: from zero to submitted

**Closes Sun 1 Nov, 12:29 PM IST. The event page says submit by Saturday to be judged in the final round, so aim for about 6 PM today.**

### 1. Install (20 min)
```
pip install -r requirements.txt
```
Install Ollama from https://ollama.com, then:
```
ollama pull gemma3:4b
python haunt.py check
```
You want `OK. The ghost can speak and see.` If `check` says vision failed, the model you picked cannot read images.
A newer Gemma works if it supports images: `python haunt.py --model <tag> ...` (tags are in `ollama list`).

Platform notes:
- **Windows:** nothing extra.
- **macOS:** System Settings, Privacy and Security, Screen Recording: allow your Terminal. Without it the ghost only sees your wallpaper.
- **Linux:** needs X11 or XWayland and a compositor for the see-through window. Pure Wayland blocks screenshots.

### 2. Try it (15 min)
Two tasks, so you see both kinds of proof. Use `--first 0` so the ghost appears straight away.
```
python haunt.py add "Finish the CS213 report" --expect "The report open with a finished conclusion" --first 0 --every 2
python haunt.py add "Write notes for tomorrow" --proof file:~/notes.txt --first 0 --every 2
python haunt.py run
```
Leave it running. Open YouTube, click **I did it**, and watch the ghost describe what it sees. Then really do the task and click again.
Save `~/notes.txt` and the second ghost leaves on its own. Stop with Ctrl+C. `python haunt.py list` shows what happened.

Write tasks as something visible: "Have the lab open with problem 3 passing" works for the eyes, "Think about algebra" does not.
`--expect` tells the ghost what the finished screen looks like and makes it far more accurate.

### 3. Measure the eyes (30 min). This is what makes the post credible
Take 10 screenshots: 5 where a task really is done, 5 where it is not (same task, e.g. "Finish the report").
```
python haunt.py judge --task "Finish the report" --expect "The report with a finished conclusion" --image shot1.png
```
Write down, for each: what the truth was and what the ghost said. Report the 2x2 table honestly, wrong answers included.
A tiny trial like this shows a rough rate, not a proven one, so say that.

### 4. Record the demo (30 min)
60 to 90 seconds, screen recording, ghost visible on a real desktop:
1. add a task with `--first 0` and start the ghost,
2. it appears, you ignore it, it comes back angrier (use `--every 1`),
3. you click **I did it** with YouTube open and it describes the video,
4. you do the work, click again, and it leaves happy.
Upload it (YouTube unlisted is fine) and keep the link.

### 5. Put the page online (30 min, the .tech category)
1. Claim a free `.tech` domain at https://hacktoberfest.com/my/promos.
2. In `docs/index.html` replace `YOUR_GITHUB_URL` and `YOUR_VIDEO_URL`. Then `grep -n YOUR_ docs/index.html` must print nothing.
3. Push this folder to a public GitHub repo. Repo Settings, Pages, deploy from branch `main`, folder `/docs`.
4. Put your `.tech` domain in the Pages "Custom domain" box and add the DNS record GitHub shows at your domain registrar.
   It can take a while to switch on, so do this first, then write the post while it propagates.

### 6. Write and submit (2 hours)
Use `POST_OUTLINE.md`. Writing quality is the heaviest criterion. Submit by about 6 PM.

## Categories to tick
Gemma (the voice and the eyes run on Gemma), `.tech` (once your domain is live and linked in the post).
Add Entire or DevRelay only if you really saved your agent sessions with them.

## When something breaks
| Symptom | Fix |
|---|---|
| `Cannot reach Ollama` | open the Ollama app, or run `ollama serve` |
| `Ollama does not have 'gemma3:4b'` | `ollama pull gemma3:4b`, or use `--model` with a tag from `ollama list` |
| Vision FAILED in `check` | use a model that accepts images |
| Ghost says "My eyes failed" | read the reason it gives; the honour-system button appears at once |
| Ghost judges slowly (30 to 90 s) | normal on a CPU laptop. A smaller model is faster, a bigger one is more accurate |
| Ghost never appears | `python haunt.py list`: the task may be snoozed or done. Use `--first 0` |
| Built-in lines instead of Gemma | the window says "voice: built-in". Ollama was not reachable |

Tasks live in `~/.haunt/tasks.json` (set `HAUNT_HOME` to change it).

## Limits (say these in the post)
- The eyes are a 4B-parameter vision model. They can be fooled and they can be too strict. That is why the honour button exists.
- Only the primary screen is captured.
- The ghost judges one screenshot, not what you did over an hour.

## Tests
`python tests/test_haunt.py` runs without a display: it checks the proofs, the escalation, the screenshot request (including that an image
really is attached), error messages, snooze, the honour button, and the whole haunt flow in Qt's offscreen mode against a stub Ollama.
