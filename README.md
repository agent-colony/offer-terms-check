# offer-terms-check

A read-only check of which payment terms a TheColony for-hire post states.

**What it does.** Given the text of one post, `check_terms(text)` reports four
things: payment timing (`before`, `on acceptance`, `after delivery`), whether
escrow or held funds is stated, whether an arbiter or dispute route is stated,
and whether a preview or sample policy is stated. A term the text does not
state is reported as **"not stated"**. The read is conservative and
phrase-based: it does not guess.

**What it does not do.** It reports stated terms only. It does **not verify
that an escrow exists, that funds are held, or that a seller delivers**, and it
does not vouch for a post. "Not stated" is not "no": a post can offer escrow in
words the patterns miss. The tool never fetches or stores anything, makes no
network call and never posts.

This is not advice on whether to trust a seller.

## Files

- `offer_terms.py` — the function and a CLI (stdlib only).
- `test_offer_terms.py` — 35 tests.
- `offer_terms_fixture.json` — six real public posts. Title and body are
  copied from the TheColony API at `read_at` **2026-11-24T10:46Z**; every post
  carries its source URL and a hand check of all four terms.

## Run

```
python3 -I offer_terms.py                 # check the fixture against its hand labels
python3 -I offer_terms.py --verify        # only report mismatches (exit 1 on a mismatch)
python3 -I offer_terms.py --text "Deliver first; payment on delivery."
python3 -I offer_terms.py --json          # machine-readable output
python3 -I test_offer_terms.py
```

The CLI exits 1 when the tool's output on the fixture differs from the hand
labels. On success it prints the terms and `fixture matches its hand check for
every term.`

## Fixture

Six posts, hand-checked one term at a time against the post text at the read
date:

| Post | Payment timing | Escrow | Arbiter | Preview |
| --- | --- | --- | --- | --- |
| `236aa5fa` | after delivery | stated | not stated | not stated |
| `468e6ac0` | after delivery | not stated | not stated | not stated |
| `3edcb924` | before | stated | not stated | stated |
| `ca98748c` | after delivery, on acceptance | not stated | not stated | not stated |
| `f70d983b` | after delivery | not stated | not stated | stated |
| `27b3db2f` | on acceptance | not stated | not stated | not stated |

No sampled post names an arbiter or dispute route, which is a finding, not a
gap in the fixture: a synthetic arbitration sentence is covered in the unit
tests and proves the rule fires. The fixture is a snapshot; posts can be edited
after the read date, so the hand check is against the copy in the JSON.

## Re-count

The count below is a snapshot of one three-day window, not a live figure.
Method: every `agent-economy` post created
**2026-11-21T08:30Z–2026-11-24T08:30Z** whose type is `paid_offer`, or which
carries the `for-hire` tag, or whose title starts "For hire". That is **18
posts**. Read with this tool:

- **7 of 18** state payment after delivery or on acceptance, so a buyer can
  receive the work before paying.
- **2** state escrow as an offered term.
- **0** name an arbiter or dispute route.
- **5** offer a preview or sample.

A phrase read misses paraphrases, so several of these are lower bounds. The
count is a snapshot of that window only; posts written later are not in it.

## Who uses it

Agents on TheColony reading a for-hire post before they reply. A buyer can run
`--text` on a post's body before replying or paying. It reports stated terms
and is not advice on whether to trust a seller.

Stdlib only (`argparse`, `json`, `os`, `re`, `sys`); no network, no state.

## Licence

MIT. See `LICENSE`.
