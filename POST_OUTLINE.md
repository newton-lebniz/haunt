# Post outline (write it after you have the demo video and the 10-screenshot trial)

Writing quality is weighted most. The thesis that makes this post different from the repo-séance pile:

> A ghost that watches your screen is creepy. That is the joke, and it is only acceptable if the eyes are local.

Fill every [bracket] with something real. Delete anything you cannot back up.

## Title (pick one or write your own)
- I built a ghost that haunts me until it sees my work. Its eyes never leave my laptop.
- Haunt: the ghost that will not leave until you finish
- A ghost that watches my screen (and why that only works with an open model)

## Opening (about 120 words)
A real task you kept dodging and the hour you were avoiding it. What you did instead. No tools yet.
End with: "So I built something that would not let me."

## What it does (about 100 words, with the demo video or a GIF)
Four lines: it appears, it escalates, you claim "done", it looks. Say that tasks tied to a file or a git commit finish by themselves
with no AI, and only the visual tasks use the model.

## How it sees (about 200 words)
- Hide the ghost, take one screenshot, shrink it, send it to Gemma on localhost with the task and what the finished screen should show.
- The model must answer in JSON: done, not done or unclear, plus one sentence naming what it actually sees. Only "done" counts.
- That sentence is what the ghost says back to you. Show your best real example.
- Show the escalation: whisper, eerie, furious.

## Does it work? (about 150 words): the honest numbers
Your 10-screenshot trial as a 2x2 table: truth (done / not done) against the ghost's verdict.
Write the sentence the table supports and nothing bigger. Ten screenshots is a rough guide, so say so.

## Where it was wrong (about 120 words): required
One real failure: it accepted something it should not have, or refused real work. What it saw, why you think it erred,
what you changed (the `--expect` field? the honour button?). This is the part judges remember.

## Why open mattered here (about 150 words)
- **Privacy is the whole product.** The ghost screenshots your desktop: mail, messages, whatever is open. With a hosted model every
  screenshot would be uploaded. Here it goes to localhost and is never stored. (Check this claim against the code before you make it:
  the screenshot is held in memory and sent to Ollama; nothing is written to disk.)
- **It works offline.** [Say whether you tried it with the network off. Only claim it if you did.]
- **I could swap the model.** [Name what you compared: a smaller or bigger Gemma, speed against accuracy.]
- **It costs nothing per nag.** A ghost that looks every few minutes is only affordable when each look is free.

## What I would change next (about 60 words)
One or two honest ideas: judging a few screenshots over time, a per-task strictness setting.

## Close (about 40 words)
Back to the opening task. Did the ghost get you to do it? One line, no moral.

## Links
- Live page: [your .tech domain]
- Code: [GitHub]
- Demo video: [link]

## Tags and categories
Use `#devchallenge` and `#hf26challenge` (the first two on every post in the feed), then `#gemma` and `#opensource`.
Pick the categories you really used: Gemma, and .tech if your domain is live and linked above.
Use the template from the challenge page's "Submission Template" link.

## Before you publish
- [ ] The opening is a real story with a real task
- [ ] The trial table matches your notes exactly
- [ ] One real failure is described
- [ ] The video plays and shows the ghost on a real desktop
- [ ] No private window (mail, chats, tabs) is visible in any screenshot or the video
- [ ] The live link works on your phone and `grep -n YOUR_ docs/index.html` prints nothing
- [ ] The post says which Gemma tag you ran
