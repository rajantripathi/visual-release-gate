# LinkedIn post body

> This is the in-feed text (what people read before clicking). Attach
> `output/model-vs-labels.png` as the hero visual and (optionally) one Streamlit
> screenshot for authenticity. Replace `REPO_URL` with the public repo link
> before posting. The numbers below are real (Gemini 3.6 Flash, free tier) but
> scoped as provisional against author labels — that honesty is part of the
> story, not a weakness.

---

AI can generate a product image in seconds. Deciding whether it's safe to
*publish* is the hard part — so I built a system where the AI never gets to make
that call.

It's called **Visual Release Gate**.

Here's the idea in one line: **the model observes, code decides.**

A vision model looks at the image and reports what it sees — as structured data,
with an exact reference to *where* it saw it. Then plain, deterministic Python —
not the model — applies the rules and returns one of four decisions:

• **SHIP** — nothing blocking found
• **REJECT** — clear evidence of a real problem
• **HUMAN REVIEW** — the pixels are genuinely ambiguous
• **UNSUPPORTED** — we simply don't have the authority to ship (consent,
  licensing, ownership, legal sign-off)

That last distinction is the whole point. "This image is blurry" and "we don't
have the legal right to use this" are completely different problems — most
systems blur them together. This one keeps them apart, on purpose.

Why it matters: a model can hallucinate. If the model's answer is treated as
*evidence* rather than *authority*, a confident-but-wrong response can't quietly
push something live. The rules sit in code you can read, test, and audit.

A few things I care about that are built in:
• Every decision cites its source — you can trace *why*
• The demo runs fully offline — no uploads, no secrets, nothing leaves your machine
• It only spends real money under a hard budget cap
• Provider-neutral — I ran it on both Runware and Google Gemini by swapping one small adapter
• 52 tests + CI on every commit

On results — and I want to be careful here: on an early live run (Gemini 3.6
Flash, 19 of 24 fictional cases; the rest hit free-tier rate limits), the gate
agreed with my author labels **84% of the time** — and crucially, **0 unsafe
approvals**: it never said "ship" when the honest answer was reject or missing
authority. When it was wrong, it erred toward *blocking*, not shipping.

These labels are still provisional (mine, not yet independently reviewed), so I'm
making no polished accuracy claim — but building the measurement discipline
*before* the bragging was the whole point.

It's open source: REPO_URL

I'd genuinely welcome feedback from people working in multimodal ML, model
evaluation, creative operations, or AI governance — tell me where this breaks.

#AI #MachineLearning #AIGovernance #MLOps #ComputerVision #OpenSource
