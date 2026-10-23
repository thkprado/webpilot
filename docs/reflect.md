# End-of-session reflection (WebPilot)

Goal: make the next session faster and cheaper by learning from this one's workflow.

1. Run `webpilot reflect-data`. Add `--days 7` when the session was short or spanned several days.
2. For each item under **Suggestions**:
   - **"Write a parser for X"**: if the site will be read again, open a representative page and follow README §3:
     1. `webpilot parser fixture <name>`
     2. Write `parsers_user/<name>.py`.
     3. `webpilot parser test <name> --show`
     4. Confirm `webpilot extract` uses it.

     Pages of different types on the same site (list vs. detail) can be separate parsers, or a single parser that branches on the URL.
   - **"Record the flow on X"**: the reads were taken to find refs before clicking or typing (forms, quizzes, wizards), so a parser would not replace them. Write the steps that worked (URLs, `text=` targets, `--wait-text`) under the site's heading in `parsers_user/NOTES.md`; if the flow will be run again, a script in `parsers_user/scripts/` is better. Write a parser only if the page's data itself will be needed again.
   - **"Fix parser X" / "returned empty data"**: save a new fixture of the current page, find which selector broke, fix it, and keep the old fixtures passing.
   - **"Large output"**: if the content was useful, write a parser. Otherwise, record in `parsers_user/NOTES.md` which `--selector` to use on that site.
   - **"`eval` returned ... data URLs"**: a script keeps an exported image (a canvas's `toDataURL()`) from stdout. Switch it to `eval --out FILE`, which writes the decoded file and is not counted as a read.
   - **"Repeated error"**: find the cause (wrong ref, slow page, wrong selector) and record the workaround in `NOTES.md`. If it is a WebPilot bug, describe it to the user.
   - **"Page never went quiet"**: the site keeps changing the DOM (a clock, an animation) or polling, so every action waited until the cap. Pass `--wait-text`/`--wait-for` with a marker of the next step (for checkboxes, `--wait-for "<target>:checked"`) and record it in `NOTES.md`.
   - **"Slow"**: consider `extract` instead of snapshot plus several clicks, or direct URLs (search/filter query strings) instead of navigating through the UI.
3. Look at the session's commands as a whole. Are there multi-step sequences that will repeat, like login, filters or pagination? Record them in `parsers_user/NOTES.md` under a heading for the site, with the URLs and selectors that work. For loops, a small Python script using `webpilot.Browser` saved in `parsers_user/scripts/` is fine.
4. Run `uv run --project <webpilot> pytest -q` to make sure every parser still passes.
5. Report a short summary to the user: what was created or changed, and what was left as a suggestion.

Do not create a parser for a site visited only once, and do not change sites' behaviour or the user's accounts during the reflection.
