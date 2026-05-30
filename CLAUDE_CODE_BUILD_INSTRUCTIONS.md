# Build instructions for Claude Code — staged, with review gates

Paste this into Claude Code at the start of the session, **alongside** the
consolidated brief (`CLAUDE_CODE_BRIEF_CONSOLIDATED.md`). The brief is the
specification; this document is the operational plan.

---

## Read these first, in this order

1. `CLAUDE_CODE_BRIEF_CONSOLIDATED.md` — the full specification.
2. `app.py` — the existing working app. This is your starting point; you are
   extending it, not replacing it. Read it carefully before touching anything.
3. `checkcif_reference/checkcif_alerts.json` (path may vary —
   inspect the working directory) — the alert reference. Index by `code`.
4. `assets/` — logo files referenced by the brief.

Do not start editing until you have read all four. Confirm in your first
response that you have read them and summarise back to me, in one paragraph,
what you understand the job to be. **Stop and wait for my confirmation before
writing any code.**

---

## Build in three phases, with a review pause at the end of each

I want to review the work at the end of each phase before you proceed to the
next. Do not chain phases without stopping.

### Phase 1 — curated area scaffolding + schema

Build:
- The new `🎓 Curated structures` tab as the fourth tab (existing three
  remain first and unchanged).
- `curated/` folder with `metadata.json`, `cif/`, `fcf/`,
  `teaching_notes/`, and `evidence_pointers.json` per the brief's §3.2–§3.5.
- Placeholder records: 2–3 entries demonstrating at least one synthetic
  `source_route`, one anchor (`assigned_groups: [1,2,3,4,5,6]`), and one
  group-specific assignment.
- Stub Markdown files in `teaching_notes/` matching the metadata.
- A starter `evidence_pointers.json` with sensible ranges for the alert
  families listed in the brief, plus a `default`.
- The per-structure UI from §3.8 — visible fields, download buttons, the
  CheckCIF link, the collapsed expander labelled exactly `"Open only after
  you've made your call"`. **At this phase the expander's contents read
  `"Teaching notes will be revealed during the group discussion."` for all
  cases — the reveal mechanism comes in Phase 3.**
- No group filtering yet — all curated cases show in this tab. Group
  filtering arrives in Phase 3.

Do NOT in Phase 1:
- Add the tutor (Phase 2).
- Add the group selector or instructor view (Phase 3).
- Read any teaching note files (Phase 3 wires this up).

Pause and report what you built. I will run it, confirm the three existing
tabs still work and the curated tab renders the placeholders, then approve
Phase 2.

### Phase 2 — the checkCIF Tutor

Build:
- The `💬 checkCIF Tutor` tab (fifth tab, after curated).
- The `render_tutor()` reusable function per the brief's §2.1.
- The Anthropic API wiring with `st.secrets["ANTHROPIC_API_KEY"]` per §2.4.
- The deterministic PLAT-code parse, JSON lookup, severity extraction, and
  evidence-pointer lookup per §2.3.
- The system prompt as the verbatim `TUTOR_SYSTEM_PROMPT` constant per §2.5.
- The structure-factor report gating per §2.6 (will only trigger when a
  curated structure ships one; for now the gate logic is in place but no
  curated case will exercise it).
- Wire the tutor into the curated area's per-structure UI per §3.8 (so it's
  reachable from both the tutor tab and within each curated case).
- `requirements.txt` updated with `anthropic`.
- `.streamlit/secrets.toml.example` entry for `ANTHROPIC_API_KEY`.

Verify in this phase:
- The app still runs without an API key (the COD tabs and curated downloads
  must work; the tutor shows a friendly error when the key is missing).
- Pasting a real PLAT code from the JSON produces a sensible Socratic reply.
- Pasting a fake PLAT code (e.g. `PLAT9999`) is reported as unknown rather
  than fabricated.
- The tutor never references teaching-note content (there is none yet, but
  the code path must not have a branch that could).

Pause and report. I will test the tutor against several real alerts and
approve Phase 3.

### Phase 3 — group selector + reveal gate + teaching-note lazy load

Build:
- Sidebar group selectbox per §3.7.
- Group filtering of the curated cases per the selected group.
- Reveal gate per §3.6: `REVEAL_ENABLED` and `REVEAL_PASSPHRASE` in
  `st.secrets`, sidebar passphrase input, in-session reveal flag.
- Lazy load of teaching-note Markdown files: read only when (a) the expander
  is opened by the user AND (b) the reveal flag is on. Otherwise the
  expander shows the placeholder text from Phase 1.
- Instructor view (`"Instructor view: show all groups"`) sidebar option
  appearing only after the passphrase is entered.
- `assigned_groups` badge shown in instructor view; hidden in student
  (group-selected) mode.
- `.streamlit/secrets.toml.example` entries for `REVEAL_ENABLED` and
  `REVEAL_PASSPHRASE`.

Verify in this phase:
- With no group selected, the curated tab shows the prompt.
- Selecting Group N shows only cases with N in `assigned_groups`. The anchor
  case (with all six groups) appears for every group.
- Without the passphrase, the expander text is the placeholder; teaching
  note files are not read.
- With the passphrase, the expander reads and renders Markdown.
- With the passphrase, the `"Instructor view"` option appears and unblocks
  all cases.
- Without the passphrase, the `"Instructor view"` option is not visible at
  all (no client-side hidden control).
- The tutor's behaviour is unchanged by the reveal flag's state.
- Empty `assigned_groups` cases are invisible in student mode and visible
  only in instructor view.

Pause and report. I will test the gating thoroughly and sign off.

---

## Working agreement for the session

- **Read before writing.** The brief is detailed and several decisions are
  load-bearing. If something is ambiguous, ask before guessing.
- **Don't expand scope.** If you spot something you'd like to add ("I could
  also build X"), surface it as a suggestion at a phase boundary rather than
  adding it. Scope creep here will make the review unreliable.
- **Don't rewrite the existing app.** The three COD tabs and their helpers
  are working and must keep working byte-for-byte. Extend the file; don't
  refactor it.
- **Respect the guardrails section (§4 of the brief) absolutely.** Several
  of those rules are subtle — particularly the "no preload of teaching
  notes," the "no developer bypass for the reveal gate," and the "tutor
  never sees teaching notes regardless of gate state." Treat any temptation
  to relax these as a signal to ask me first.
- **At each phase boundary, report what you built and what you did not
  build.** Explicit "did not" lists are how I confirm scope was held.

When you have read the brief and the existing `app.py`, reply with your
one-paragraph summary of the job and your readiness to start Phase 1. Then
wait for my go-ahead.
