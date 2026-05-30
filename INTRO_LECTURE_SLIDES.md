# Intro lecture — slide-by-slide design

**Audience:** ~30 PhD-level chemists/pharmacists, one-day crystallography validation course, Bucharest.
**Duration:** 60 minutes including 5 min buffer.
**Style:** sparse visuals; you do the work in speech; ~1 min/slide baseline, slower at the three pause cues.
**Spine:** stance-heavy. The Box quote is the organising principle. Vocabulary and content are scaffolding around it.

The notes under each slide are *starters*, not scripts. Key phrases are flagged in **bold** so your eye catches them mid-talk.

---

## Section 1 — Opening (5 min)

### Slide 1 — The Box quote
**Visual:** Just the quote, centred, large. No image, no logo.

> "All models are wrong, but some are useful."
> — George E. P. Box

**Speaker notes (slow — let this sit for 10 seconds before you speak):**
This is going to be the **frame** for the whole hour. Box was talking about statistical models, but it's the perfect frame for crystallography. **Every crystal structure you read in the literature is a model fit to diffraction data.** Every one of them is wrong in some way — the question is *how*, *by how much*, and *whether it matters for what you'd use it for*.

> [Pause cue — wait. Don't fill the silence. Let them be unsettled by the idea that every published structure they've ever used is wrong in some way.]

---

### Slide 2 — The JIMBUC molecule
**Visual:** Side-by-side: the **wrong** structure (with the misassigned O) on the left, the **correct** structure (with NH) on the right. ORTEP-style or simple ball-and-stick. Label both unmistakably as "Published" and "Correct".

**Speaker notes:**
This is JIMBUC — a putative antineoplastic natural product, published in the structural literature. The structure on the left is the published one. On the right is what the molecule *actually* is. The difference is one atom: an oxygen that should have been an NH.

**Several research groups spent years trying to synthesise the published compound.** They were trying to make the wrong molecule.

This is not ancient history; this is the kind of thing that still happens. The crystallography was technically competent — low R, no flagrant alerts. But the **chemistry was wrong**, and the wrongness cost real time, real money, real careers.

---

### Slide 3 — The pharma framing
**Visual:** Three icons or simple line drawings stacked or in a row: a regulatory filing (a stack of documents), a synthetic route (an arrow with intermediates), a patent (a stamped document). Each labelled simply: "Regulatory filing", "Synthesis design", "Patent claim".

**Speaker notes:**
Imagine that JIMBUC structure was the basis for **a synthesis your team was going to scale**. Or the polymorph you were claiming **in a patent**. Or the active form in **a regulatory filing**.

The cost of "wrong in a way that matters" is real, and it lands on people downstream of the crystallographer.

The question — *would I trust this structure for the decision I'm about to make?* — is one you, as chemists and pharmacists, are going to be asked. Maybe by your boss. Maybe by a regulator. Maybe by yourself in five years. Today is about learning to answer it.

---

## Section 2 — The validation mindset (15 min)

### Slide 4 — Wrongness has a structure
**Visual:** Title only, large. Optional: a small visual motif you'll reuse — maybe a magnifying glass over a molecule, or simply the Box quote in small text at the bottom as a callback.

> Wrongness has a structure.

**Speaker notes:**
If every structure is wrong in some way, the skill of validation is **learning to see the shapes that wrongness takes**.

There are four families I want you to recognise. We're not going to be exhaustive — we're going to **name** them. Once you can name them, you can start to look for them.

---

### Slide 5 — Geometric wrongness
**Visual:** A molecular fragment with an obviously wrong bond length highlighted — e.g. a C–O bond drawn impossibly long, with the measured value annotated. Pick a real published example from your collection if you have one; otherwise a clear schematic.

**Speaker notes:**
**Geometric wrongness.** The atoms are in the wrong places, or the bonds are the wrong lengths, or the angles don't make sense.

You can often see this in **Mercury** in thirty seconds. A C–O bond that's 1.6 Å instead of 1.4 Å is the kind of thing your chemical intuition catches before any software does.

The most famous example is the rhodium-that's-actually-silver case — a "rhodium amide" complex whose Rh–N distance was wildly wrong because the metal was actually Ag. The crystallography software didn't care. The **chemistry** told the story.

---

### Slide 6 — Statistical wrongness
**Visual:** A checkCIF-style alert excerpt, or a chart showing R-factor vs resolution falling apart at high angle. Whatever signals "the data couldn't constrain the model".

**Speaker notes:**
**Statistical wrongness.** The model fits the data, but the data wasn't sufficient to constrain the model. High R-factors. Low data-to-parameter ratio. Missing wedges. Resolution too low to determine ADPs reliably.

This is the wrongness that **the report itself** flags most loudly — and the one you'll see most often in the workshop this afternoon.

The key point: a structure with high R isn't necessarily *wrong*, but the model is **less determined by the data**. Which means the *next* piece of wrongness can hide in the slack.

---

### Slide 7 — Chemical wrongness
**Visual:** A structure showing an impossible protonation state, or an atom misassignment with the difference-density peak that should have flagged it. The JIMBUC case again, briefly, or a schematic of "the geometry is fine but the element is wrong".

**Speaker notes:**
**Chemical wrongness.** The geometry refines beautifully. The R is low. And the chemistry is impossible — the atom is the wrong element, the molecule wouldn't exist at that pH, the oxidation state isn't accessible.

This is the wrongness **the software is worst at catching**, and the wrongness **you** are best at catching. You know what a reasonable C–N bond looks like. You know what protonation states make sense. You know which oxidation states an atom can occupy. **That's not a deficit, that's a strength.** Crystallographers can spend years not noticing things that a competent chemist sees in five seconds.

> [Aside: this is the slide that gives them confidence. Linger here. Make eye contact. They need to believe their chemistry training is a *weapon* in this room.]

---

### Slide 8 — Symmetric wrongness
**Visual:** Two unit cells side by side — one in P1, one in P-1 with the inversion centre marked. Or the classic "looks lower symmetry, is actually higher symmetry" sketch.

**Speaker notes:**
**Symmetric wrongness.** The model imposes the wrong symmetry on the structure — usually *too low*, occasionally too high. A structure refined in P1 that's actually P-1. A structure in P2₁ that's actually P2₁/c.

This one has its own dedicated detective in PLATON, called **ADDSYM**, and we'll see it in the workshop. The diagnostic is subtle but the symptoms are characteristic: chemically equivalent bonds that refine to slightly different lengths, ADPs that look strangely twinned, a feeling that the structure is *trying* to have more symmetry than the model allows.

---

### Slide 9 — checkCIF
**Visual:** A clean screenshot of the checkCIF upload page, or its logo, or a stylised version of a report. Whichever you find most visually clean.

**Speaker notes:**
**checkCIF** is the IUCr's automated tool for detecting these shapes of wrongness. It runs every test PLATON has, organises the results by severity, and produces a report.

Every paper submitted to an IUCr journal goes through it automatically. Many other journals require it too. It is, effectively, **the standard**.

After lunch, you'll spend three hours reading checkCIF reports on real structures. So let's spend the next fifteen minutes on **just enough vocabulary** to read them intelligently.

---

## Section 3 — Reading the report (15 min)

### Slide 10 — Three letters
**Visual:** Just three letters, big, in coloured boxes: **A** (red), **B** (orange), **C** (yellow). Maybe a fourth, **G** (grey/blue), for general information.

**Speaker notes:**
checkCIF organises its findings by severity. **A** is the most severe, **C** is the mildest. **G** is general information, not really an alert.

But — and this is the part most people get wrong — **A is not always damning, and C is not always benign**.

---

### Slide 11 — Severity ≠ verdict
**Visual:** A two-column comparison or a simple statement. Could just be the text, large.

> **A-alert:** unusual.
> **A-alert ≠ wrong.**

> **No alerts:** the standard tests passed.
> **No alerts ≠ right.**

**Speaker notes:**
The severity reflects how **unusual** the value is, statistically. A bond that's two standard deviations off the Cambridge Structural Database mean fires an A-alert. That bond *might* be wrong — or it might be a sterically constrained molecule where the unusual value is exactly what you'd expect.

**The severity is a flag, not a verdict.** Your job — and the workshop's lesson — is to **read the flag and decide**.

Conversely: a structure with no A-alerts hasn't been certified correct. It's passed the standard tests. Those tests don't cover everything.

> [Pause cue — this is the second slide that needs silence. The "A is not always damning" reframe will be the most counter-intuitive thing you say in the hour, and it has to land.]

---

### Slide 12 — Where the evidence lives
**Visual:** A four-quadrant matrix, or a clean list. Each row is a kind of question + where you look.

| What you're asking | Where the answer lives |
|---|---|
| Are the bonds and angles sensible? | **Mercury** (or any viewer) |
| Are the ADPs sensible? | **Mercury** (ellipsoids at 50%) |
| Is the residual density acceptable? | **The checkCIF report** (not Mercury) |
| Is the data adequate? | **The report** (R, completeness, resolution) |
| Is there hidden symmetry? | **PLATON's ADDSYM** output |
| Is the chemistry sensible? | **Your head.** Always. |

**Speaker notes:**
This is the **most practically important slide of the hour**. If you remember nothing else, remember this.

Different questions live in different places. A residual-density problem will not show up in Mercury — there's nothing to see; the relevant number lives in the report. Geometric wrongness, conversely, is what Mercury is *for*.

Students often waste twenty minutes opening a structure in Mercury looking for evidence of a problem that doesn't live there. **Don't be those students.** When you read an alert, ask first: *where does the evidence for this live?*

The bottom row is the most important. **Your head, always.** No tool replaces chemical reasoning.

---

### Slide 13 — Four families of evidence (recap)
**Visual:** A simple 2×2 grid, or four icons. Geometry / ADPs / Residual density / Data quality. Each with a one-word descriptor.

**Speaker notes:**
So: four families of evidence you'll see this afternoon. **Geometry** — bond lengths, angles. **Displacement parameters** — the thermal ellipsoids, which tell you how well-determined each atom is. **Residual density** — the leftover electrons the model doesn't account for. **Data quality** — resolution, completeness, R-factors, the bones of the dataset.

Each of those has a chapter in the checkCIF report. Each has tools that show you the relevant evidence. And each has a way of going wrong that the workshop will give you practice spotting.

---

## Section 4 — The trap (10 min) — when wrongness is invisible

### Slide 14 — Section title
**Visual:** Just the text. Large. Centred.

> Sometimes the structure looks fine.
> Sometimes the structure *is* fine.
> Sometimes the structure looks fine — and isn't.

**Speaker notes:**
We're going to spend the last fifteen minutes on the most important kind of wrongness: **the kind checkCIF doesn't catch**.

This is the wrongness that gets through peer review. That gets cited. That ends up in patents. That ends up in your reaction scheme.

I'm going to show you one case.

---

### Slide 15 — A chiral molecule, well-refined
**Visual:** A clean ORTEP of a chiral molecule with stereocentres labelled. Pick something with a clear pharmacological flavour if possible — a drug-like molecule with an unambiguous stereochemistry claim. Show one enantiomer.

Caption underneath: **R₁ = 0.038. wR₂ = 0.094. No A-alerts. Published.**

**Speaker notes:**
Here's a structure. R-factors are excellent. checkCIF runs clean — no A-alerts, a couple of routine C-alerts, nothing concerning. Published in a respectable journal. The authors claim, in the paper and the deposited CIF, that this is the **(S)** enantiomer.

Would you trust this for a synthetic decision? Would you trust it for a patent? Would you trust it for an IND filing?

> [Pause cue — wait. Let some students nod. Let some look uncertain. This is the moment.]

---

### Slide 16 — The data wavelength
**Visual:** Two simple labelled wavelengths, like badges. **Mo Kα (0.71 Å)** on one side, **Cu Kα (1.54 Å)** on the other. The Mo side is highlighted/circled.

Caption: **The data was collected at Mo Kα.**
Sub-caption: **The molecule contains only C, H, N, O.**

**Speaker notes:**
Here's the catch. The data was collected with **Mo Kα radiation**. The molecule contains only **C, H, N, O** — light atoms.

Determining absolute configuration from X-ray data requires an **anomalous scattering signal** — a small wavelength-dependent asymmetry that distinguishes one enantiomer from its mirror image. The strength of that signal depends on the heaviest atom in the structure and on the wavelength.

For C, H, N, O at Mo Kα, **the anomalous signal is essentially zero**. The data **cannot distinguish** the S enantiomer from the R enantiomer. The two refine identically. R₁ is the same. wR₂ is the same. checkCIF doesn't flag it because the model is internally consistent.

**The S claim in the CIF is not supported by the data.** It might be right; it might be wrong. The crystallography cannot tell you which.

---

### Slide 17 — The trap, named
**Visual:** Plain text, large.

> The model was useful.
> The model was wrong in a way the standard tests don't see.
> **The Box quote earns its keep.**

**Speaker notes:**
This is the trap. The structure is *useful* for many things — the connectivity is right, the geometry is right, the conformation is right. But **the specific claim that it's the S enantiomer** is not supported by the data.

If you were the pharma chemist downstream, planning a synthesis to the S enantiomer because the crystal structure said so — you'd be in trouble.

This is why **the standard tests are necessary but not sufficient**. Why **judgement** is required. Why **your chemistry training matters**.

> [Aside: this is where you can mention you may add a personal example. If you find one, swap it in or follow this slide with one more.]

---

### Slide 18 — The lesson
**Visual:** Title only.

> Alerts tell you what looks wrong.
> They don't tell you what is wrong.
> They don't tell you what's missing.
> You do.

**Speaker notes:**
Alerts tell you what looks **unusual**. They don't tell you what's **wrong**. They especially don't tell you what's **missing** — what the data couldn't constrain, what the model didn't capture, what the report doesn't think to ask about.

Validation is what you do **after** the tools have done their part.

That's what the rest of the day is about.

---

## Section 5 — The day ahead (10 min)

### Slide 19 — The afternoon
**Visual:** A simple three-block timeline. "Curated structures (2 h)" → "COD mining game (1.5 h)" → "Presentations + discussion".

**Speaker notes:**
This afternoon, in groups of five, you'll work through a curated set of structures. Each group has **six cases**. The cases were chosen — and in some cases **deliberately modified** — to give you practice with the kinds of wrongness we just talked about.

Then we'll move to the **mining game**: searching the Crystallography Open Database for structures of your own choosing, and arguing for the most interesting case of wrongness you find.

At the end, each group presents. Five minutes per group. We discuss.

---

### Slide 20 — Three levels of help
**Visual:** Three labelled boxes or a staircase, climbing from left to right.
1. **Hint** — the category
2. **Tutor** — the vocabulary
3. **Reveal** — the answer

**Speaker notes:**
Each curated case is **blind by default** — you see the structure, the data, and the tools, but not what the lesson is.

If you're stuck, three levels of help are available, in order:

The **hint** tells you the *category* of wrongness — "atom misassignment", "missed symmetry", "unmodelled solvent". One word. It narrows the search; it doesn't end it.

The **tutor** — that's the chatbot in the app. It will explain what a checkCIF alert *means*. **It will not tell you whether the structure is good or bad.** That's deliberate. The verdict is yours.

The **reveal** is the full answer — the teaching note. It's hidden until the discussion phase. *Don't try to peek; you'll spoil it for yourselves.*

---

### Slide 21 — The prize, framed
**Visual:** A trophy or medal icon, with the rubric underneath in clean text.

> The prize goes to the team
> whose **argument** is best —
> not the structure
> whose **numbers** are worst.

**Speaker notes:**
For the mining game, we're going to score the **best argued case**, not the numerically worst structure.

A team that finds a subtle, interesting problem and tells a compelling story about it — *what's wrong, what evidence convinced them, what decision it would mislead* — beats a team that finds an R = 35% basket case and shrugs.

This is deliberate. The skill is **argument from evidence**, not **finding the most broken thing**.

---

### Slide 22 — Callback
**Visual:** The Box quote returns, alone on the slide.

> "All models are wrong, but some are useful."

**Speaker notes:**
Every structure you'll see today is wrong in some way.

Your job is to figure out **how** wrong, **where** wrong, and **whether it matters** for the decision someone might make based on it.

That's the skill. That's the day. Let's get to work.

> [Final pause cue — this is your sign-off. Don't rush past it. Let the quote sit, then move into the break or into the workshop.]

---

## Notes on the design

- **Total: 22 slides at ~1 min each plus three pause cues that buy you 30–60 seconds each = roughly 55 minutes.** That leaves 5 min buffer for the inevitable overrun or a quick question.
- **Pause cues are at slides 1, 11, and 15** — the Box quote, the "A is not always damning" reframe, and the chirality reveal. These are the slides whose ideas have to *land*, not just be heard.
- **The chirality trap (slides 14–18) is the lecture's centre of gravity** in pedagogical terms. If you only nail one section, nail this one. Practice it.
- **Slide 7 (chemical wrongness)** is the slide where you give the audience permission to use their chemistry training. It's emotionally important even though it looks like just another category.
- **Slide 12 (where the evidence lives)** is the slide that will save the most time in the workshop. Consider printing it as a handout if you want — students looking at a one-page reference during the workshop is fine, and it removes the "I forget where to look" failure mode.

## Things deliberately not included

- No history of crystallography.
- No recap of the X-ray experiment.
- No live demo of the app or Mercury or checkCIF.
- No exhaustive list of alert codes or test categories.
- No reflection on AI/LLMs.
- No reference to specific software beyond Mercury, checkCIF, PLATON, COD — the four tools they'll actually touch today.
