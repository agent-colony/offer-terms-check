#!/usr/bin/env python3
"""Read-only check of payment terms stated in a TheColony for-hire post.

Given the text of one post, list which payment terms it states:

- payment timing: ``before``, ``on acceptance`` or ``after delivery``
- escrow or held funds
- arbiter or dispute route
- preview or sample policy

A term the text does not state is reported as "not stated". The check is a
conservative phrase read: it never guesses and never fetches anything.

Stdlib only. Run ``python3 -I offer_terms.py`` to check the fixture
against its hand labels, or ``--text`` to check one piece of text.

This is not advice on whether to trust a seller. It reports stated terms only.
It does not verify that an escrow exists, that funds are held, or that anyone
delivers.
"""

import argparse
import json
import os
import re
import sys

DEFAULT_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "offer_terms_fixture.json")

TERM_ORDER = ("before", "on acceptance", "after delivery")

# --- phrase rules -----------------------------------------------------------
# Each rule is (label, compiled regex). Matching is case-insensitive. A match
# is ignored when it is immediately negated ("no prepayment", "no escrow").
def _p(pattern):
    return re.compile(pattern, re.IGNORECASE)


PAYMENT_RULES = [
    ("before", _p(r"\bfund(?:ed|ing)?\s+(?:escrow\s+)?first\b")),
    ("before", _p(r"\bfund(?:ed)?\s+before\b")),
    ("before", _p(r"\bfunded\s+milestone\b")),
    ("before", _p(r"\bpay(?:ment)?\s+before\b")),
    ("before", _p(r"\bpay(?:ment)?\s+(?:up\s?front|in\s+advance)\b")),
    ("before", _p(r"\bup\s?front\s+payment\b")),
    ("before", _p(r"\bprepay(?:ment)?\s+(?:required|first|before|upfront|up\s?front)\b")),
    ("before", _p(r"\bdeposit\s+(?:is\s+)?(?:required|first|up\s?front|in\s+advance|before\s+(?:delivery|work|start|the\s+work))\b")),
    ("before", _p(r"\b(?:pay|paid|paying|send|sent|provide|require|required)\s+(?:a\s+|the\s+)?(?:\d+(?:\.\d+)?\s*%\s*)?(?:of\s+the\s+\w+\s+)?deposit\b")),
    ("on acceptance", _p(r"\b(?:on|upon)\s+acceptance\b")),
    ("on acceptance", _p(r"\bpay\s+only\s+(?:if|when)\s+you\s+accept\b")),
    ("on acceptance", _p(r"\bwhen\s+you\s+accept\b")),
    ("after delivery", _p(r"\bdeliver(?:y)?[-\s]first\b")),
    ("after delivery", _p(r"\bdelivered\s+before\s+payment\b")),
    ("after delivery", _p(r"\bdeliver(?:ed)?[-\s]then[-\s]you[-\s]pay\b")),
    ("after delivery", _p(r"\b(?:deposit|payment)\s+(?:only\s+)?(?:after|upon|on)\s+(?:delivery|completion)\b")),
    # "Deposit is required only after delivery", "payment will be paid upon
    # completion": the timing word can sit behind a short qualifier.
    ("after delivery", _p(
        r"\b(?:deposit|payment|paid)\s+(?:(?:is|are|will\s+be|to\s+be)\s+)?"
        r"(?:(?:paid|made|payable|due|required|expected|sent|provided|released)\s+)?"
        r"(?:only\s+)?(?:after|upon|on|once)\s+(?:delivery|completion|receipt|receiving)\b")),
    ("after delivery", _p(
        r"\bpay(?:ment)?\s+(?:after|on|upon)\s+(?:delivery|completion)\b")),
    ("after delivery", _p(r"\bpayment\s+released\s+on\s+delivery\b")),
    ("after delivery", _p(
        r"\bpay\s+(?:only\s+)?after\s+you\s+(?:review|read|check)\b")),
    ("after delivery", _p(
        r"\bthe\s+artifact\s+arrives\s+before\s+you\s+pay\b")),
]

ESCROW_RULES = [
    _p(r"\bfunded\s+escrow\b"),
    _p(r"\bescrow(?:ed)?\s+(?:first|settlement)\b"),
    _p(r"\bheld\s+in\s+escrow\b"),
    _p(r"\bin\s+escrow\b"),
    _p(r"\bvia\s+escrow\b"),
    _p(r"\buse\s+escrow\b"),
    _p(r"\bescrow\s+(?:is\s+)?(?:fine|available|accepted|offered)\b"),
    _p(r"\bor\s+escrow\b"),
]

ARBITER_RULES = [
    _p(r"\barbiter\b"),
    _p(r"\barbitrat(?:ion|or)\b"),
    _p(r"\bdispute\s+(?:route|resolution|process|window)\b"),
    _p(r"\bthird[-\s]party\s+(?:arbiter|arbitration|mediator)\b"),
    _p(r"\bmediator\b"),
    _p(r"\bplatform\s+(?:decides|resolves|arbitrates)\b"),
]

PREVIEW_RULES = [
    _p(r"\bpreview(?:[-\s]first)?\b"),
    _p(r"\bfree[-\s]first\b"),
    _p(r"\bfree\s+(?:sample|preview|trial)\b"),
    _p(r"\bfree\s+for\s+one\b"),
    _p(r"\btry\s+(?:it\s+)?free\b"),
    _p(r"\bjudge\s+before\s+pay"),
    _p(r"\bfree\s+in\s+full\b"),
    _p(r"\bsample\s+(?:audit|report|deliverable)\b"),
    _p(r"\bexample\s+deliverable\b"),
    _p(r"\bdemo\b"),
]

_NEGATION_TAIL = re.compile(
    r"\b(?:no|not|never|without|nor|declines?|declined|refuses?|refused)\s+"
    r"(?:\w+[-\s]+){0,2}$",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _normalise(text):
    """Collapse whitespace so phrase rules see one spaced line."""
    return re.sub(r"\s+", " ", text or "").strip()


def _negated(text, start):
    """True when the match at start is immediately negated ("no prepayment")."""
    tail = text[max(0, start - 40):start]
    return bool(_NEGATION_TAIL.search(tail))


_CLAUSE_END = re.compile(r"[,;.!?\n]")
_DEFERRED = re.compile(
    r"^\s*(?:(?:is|are|will\s+be|to\s+be)\s+)?"
    r"(?:(?:paid|made|payable|due|required|expected|sent|provided|released)\s+)?"
    r"(?:but\s+)?(?:only\s+)?(?:after|upon|on|once)\s+"
    r"(?:delivery|completion|receipt|receiving|you\s+receive)\b",
    re.IGNORECASE,
)


def _deferred(text, end):
    """True when the rest of the clause defers payment to after delivery.

    "Pay a deposit only after delivery" names a deposit but states no
    prepayment: the timing qualifier sits after the phrase that matched. The
    qualifier counts only inside the same clause, so "Deposit first, payment
    after delivery" keeps its `before` term.
    """
    rest = text[end:end + 80]
    cut = _CLAUSE_END.search(rest)
    if cut:
        rest = rest[:cut.start()]
    return bool(_DEFERRED.match(rest))


def _sentence(text, start, end, limit=240):
    """Return the sentence around text[start:end], trimmed to limit chars."""
    bounds = [0] + [m.end() for m in _SENTENCE_SPLIT.finditer(text)] + [len(text)]
    lo, hi = 0, bounds[-1]
    for i in range(len(bounds) - 1):
        if bounds[i] <= start < bounds[i + 1]:
            lo, hi = bounds[i], bounds[i + 1]
            break
    sentence = text[lo:hi].strip()
    if len(sentence) > limit:
        sentence = sentence[:limit - 1].rstrip() + "…"
    return sentence


def _unique(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _matches(text, start, end):
    """Return (start, end, sentence) for one valid, non-negated match."""
    return (start, end, _sentence(text, start, end))


def check_terms(text):
    """List the payment terms one post text states.

    Returns a dict keyed ``payment_timing``, ``escrow``, ``arbiter`` and
    ``preview``. ``payment_timing["stated"]`` is a list of values in fixed
    order; each other term has a boolean ``stated``. Every term carries the
    sentences that evidence it, and an empty list when it is not stated.
    """
    text = _normalise(text)

    timing, timing_evidence = [], []
    for label, rule in PAYMENT_RULES:
        for m in rule.finditer(text):
            if _negated(text, m.start()):
                continue
            if label == "before" and _deferred(text, m.end()):
                # "pay a deposit only after delivery" is not a prepayment.
                if "after delivery" not in timing:
                    timing.append("after delivery")
            elif label not in timing:
                timing.append(label)
            timing_evidence.append(_sentence(text, m.start(), m.end()))
    timing = [value for value in TERM_ORDER if value in timing]

    result = {
        "payment_timing": {
            "stated": timing,
            "evidence": _unique(timing_evidence),
        }
    }
    for name, rules in (("escrow", ESCROW_RULES),
                        ("arbiter", ARBITER_RULES),
                        ("preview", PREVIEW_RULES)):
        evidence = []
        for rule in rules:
            for m in rule.finditer(text):
                if _negated(text, m.start()):
                    continue
                evidence.append(_sentence(text, m.start(), m.end()))
        result[name] = {"stated": bool(evidence), "evidence": _unique(evidence)}
    return result


def check_post(post):
    """Check one fixture post (title + body) and keep its source metadata."""
    text = (post.get("title") or "") + "\n" + (post.get("body") or "")
    return {
        "id": post.get("id"),
        "url": post.get("url"),
        "read_at": post.get("read_at"),
        "title": post.get("title"),
        "terms": check_terms(text),
    }


def load_fixture(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def fixture_mismatches(fixture):
    """Compare the tool's output on each post with its hand label."""
    mismatches = []
    for post in fixture.get("posts", []):
        result = check_post(post)["terms"]
        label = post.get("hand_check") or {}
        got_timing = set(result["payment_timing"]["stated"])
        want_timing = set(label.get("payment_timing") or [])
        if got_timing != want_timing:
            mismatches.append(
                "%s payment_timing: tool=%s hand=%s" % (
                    post.get("id"), sorted(got_timing), sorted(want_timing)))
        for term in ("escrow", "arbiter", "preview"):
            got = bool(result[term]["stated"])
            want = bool(label.get(term))
            if got != want:
                mismatches.append(
                    "%s %s: tool=%s hand=%s" % (post.get("id"), term, got, want))
    return mismatches


def format_terms(terms):
    """Render one result as four lines, saying "not stated" for a gap."""
    lines = []
    timing = terms["payment_timing"]["stated"]
    lines.append("payment timing: %s" % (", ".join(timing) if timing else "not stated"))
    for term in ("escrow", "arbiter", "preview"):
        lines.append("%s: %s" % (term, "stated" if terms[term]["stated"] else "not stated"))
    return "\n".join(lines)


def _run_fixture(path, as_json):
    fixture = load_fixture(path)
    results = [check_post(post) for post in fixture.get("posts", [])]
    if as_json:
        print(json.dumps({"read_at": fixture.get("read_at"), "posts": results},
                         ensure_ascii=False, indent=2))
    else:
        print("fixture: %s" % path)
        print("read at: %s" % fixture.get("read_at"))
        for result in results:
            print("")
            print("%s  %s" % (result["id"], result["title"]))
            print("  url: %s" % result["url"])
            for line in format_terms(result["terms"]).splitlines():
                print("  " + line)
    mismatches = fixture_mismatches(fixture)
    if mismatches:
        print("\nfixture does not match its hand check:", file=sys.stderr)
        for item in mismatches:
            print("  " + item, file=sys.stderr)
        return 1
    if not as_json:
        print("\nfixture matches its hand check for every term.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="List the payment terms one for-hire post states.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE,
                        help="fixture JSON to check (default: the bundled one)")
    parser.add_argument("--text", help="check this text instead of the fixture")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--verify", action="store_true",
                        help="with --fixture, only report hand-check mismatches")
    args = parser.parse_args(argv)

    if args.text is not None:
        terms = check_terms(args.text)
        if args.json:
            print(json.dumps(terms, ensure_ascii=False, indent=2))
        else:
            print(format_terms(terms))
        return 0

    if args.verify:
        mismatches = fixture_mismatches(load_fixture(args.fixture))
        if mismatches:
            for item in mismatches:
                print(item, file=sys.stderr)
            return 1
        print("fixture matches its hand check for every term.")
        return 0

    return _run_fixture(args.fixture, args.json)


if __name__ == "__main__":
    sys.exit(main())
