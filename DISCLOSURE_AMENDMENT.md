# Amendment to CLAUDE_CODE_BRIEF_CONSOLIDATED.md — three-level disclosure (hint / tutor / reveal) and blind mode

## D.0 What this amendment does

Restructures the disclosure model in the curated area into three explicit levels
of help available to a stuck group:

1. **Hint** — student-controllable expander revealing the case's
   `pathology_category` (one short phrase).
2. **Tutor** — already present; unchanged.
3. **Reveal** — the full teaching note, already gated by the reveal
   passphrase; unchanged.

Default rendering of a curated case is **blind**: no pathology category, no
source_route, no citation/DOI/deposited_id, no label visible. The student sees
the title, the data files, and the three controls. An instructor-controlled
**non-blind mode** restores the previous behaviour where `pathology_category`
is permanently visible.

This amendment supersedes the parts of `CLAUDE_CODE_BRIEF_CONSOLIDATED.md`
§3.8 that specified always-visible `pathology_category`, `citation`, `doi`,
and `deposited_id`. The reveal-gate and group-selector mechanisms from earlier
amendments are unchanged and continue to apply.

## D.1 Visibility rules

| Field | Student (blind, default) | Student (non-blind) | Instructor view |
|---|---|---|---|
| `title` | yes (must be non-revealing — see §D.5) | yes | yes |
| Download buttons (CIF, FCF) | yes | yes | yes |
| Tutor affordance | yes | yes | yes |
| "Need a hint?" expander | yes (reveals `pathology_category` on open) | not shown — category already visible | yes |
| `pathology_category` (inline) | no | yes | yes |
| `label` | no | no | yes |
| `source_route` | no | no | yes |
| `citation`, `doi`, `deposited_id` | no | no | yes |
| `assigned_groups` badge | no | no | yes |
| Teaching note (full reveal) | only when reveal passphrase entered | only when reveal passphrase entered | only when reveal passphrase entered |

The "Open only after you've made your call" expander is shown to students in
both modes; its contents follow the existing reveal-gate logic from
`TEACHING_NOTES_AMENDMENT.md`.

## D.2 Blind-mode default

Add `st.secrets["BLIND_MODE_DEFAULT"]` (boolean) read at app startup. Default
to `true` if not set. This controls the *default* render mode for student
views.

- `true` (recommended) → curated cases render blind by default; the "Need a
  hint?" expander is shown.
- `false` → curated cases render with `pathology_category` inline; no hint
  expander.

This is a deploy-time choice. To switch modes during a course, the instructor
restarts the app with the other setting. Runtime mid-class global flipping is
intentionally not supported via UI — it would require server-side global state
beyond what the current design uses.

Document `BLIND_MODE_DEFAULT` in `.streamlit/secrets.toml.example` alongside
the existing entries.

## D.3 Instructor in-session override

When the reveal passphrase has been correctly entered (existing mechanism), the
instructor's sidebar gains an additional toggle: **"Show pathology category
inline (this session)"**. This affects only the instructor's own browser
session — useful for prep, demonstration, or verifying what the non-blind
alternative looks like. It does not affect students on their own browsers.

Piggy-backs on the existing reveal-passphrase gate. No new secret required.

## D.4 UI changes per-case

The curated case render becomes:

```
<title>
  [Download CIF]  [Download FCF (if present)]
  [Run CheckCIF in a new tab — link]

  Tutor box (existing render_tutor function)

  ▸ Need a hint?                                (only if blind mode is active)
  ▸ Open only after you've made your call       (existing reveal-gated expander)

  Instructor badge bar (only in instructor view):
    source_route · assigned_groups · citation · DOI · deposited_id · label
```

The "Need a hint?" expander label must be **neutral** — do not encode the hint
into the label text. Acceptable: `"Need a hint?"`, `"Show pathology category"`,
`"Stuck? Click for a category hint"`. The `pathology_category` string itself
is rendered only inside the expander body.

**Page source note.** The `pathology_category` value lives in
`curated/metadata.json` which is loaded into memory, and Streamlit's expander
may include the body content in rendered HTML even when collapsed. This is
acceptable — the audience is cooperative students at a PhD school, not
adversaries, and the actual answer-key (the teaching note) remains protected
by the existing gate, which is the part that matters. Do **not** add
lazy-loading infrastructure for the hint specifically.

## D.5 Placeholder cleanup

Current placeholder titles encode the answer (e.g. `"Placeholder group-1 case
— atom misassignment"`). Rewrite placeholder titles to be **non-revealing**:

- Acceptable: `"Case 02"`, `"Case 02 — small organic, Cu radiation, 100 K"`,
  `"Structure A"`
- Not acceptable: anything containing the pathology family name or hinting at
  it

The same rule applies to `label` if it ever appears in student view (it does
not, per §D.1, but rewriting is cheap insurance).

## D.6 Guardrails — do NOT do these

In addition to the guardrails of the consolidated brief §4:

- Do **not** render `source_route`, `citation`, `doi`, `deposited_id`,
  `label`, or `assigned_groups` in any student-facing view (blind or
  non-blind). Instructor-view-only.
- Do **not** encode the hint into the expander label.
- Do **not** make the tutor's behaviour dependent on whether the hint
  expander has been opened. The tutor never reads case-level state.
- Do **not** log hint views — no per-case session state for hint usage.
- Do **not** add a separate gate for non-blind mode. The reveal passphrase
  governs both the teaching-note reveal and the in-session non-blind
  override; one passphrase, one instructor mode.
- Do **not** read `BLIND_MODE_DEFAULT` anywhere except at app startup.
  Runtime mid-session UI flipping is intentionally not supported.

## D.7 Deliverables

- Updated curated-case render per §D.4.
- Visibility rules in instructor view (badges for fields now always-hidden
  from students).
- `.streamlit/secrets.toml.example` updated with `BLIND_MODE_DEFAULT`.
- Placeholder titles rewritten per §D.5.
- README addition: the three-level disclosure design, the
  `BLIND_MODE_DEFAULT` setting, the rationale for blind-by-default, and how
  to flip mode for a future course (restart with the other secret value).
