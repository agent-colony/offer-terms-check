#!/usr/bin/env python3
"""Tests for offer_terms.py. Run: python3 -I test_offer_terms.py"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import offer_terms as ot  # noqa: E402


def run(args):
    """Call ot.main with captured stdout/stderr; return (code, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ot.main(args)
    return code, out.getvalue(), err.getvalue()


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ot.load_fixture(ot.DEFAULT_FIXTURE)

    def test_header_carries_a_read_date(self):
        self.assertRegex(self.fixture.get("read_at", ""), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")

    def test_at_least_five_posts(self):
        self.assertGreaterEqual(len(self.fixture["posts"]), 5)

    def test_every_post_has_an_id_url_read_date_and_hand_check(self):
        for post in self.fixture["posts"]:
            self.assertTrue(post["id"])
            self.assertTrue(post["url"].startswith("https://thecolony.ai/api/v1/posts/"))
            self.assertRegex(post["read_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")
            self.assertIn("hand_check", post)
            self.assertIn("payment_timing", post["hand_check"])

    def test_fixture_matches_the_hand_check(self):
        self.assertEqual(ot.fixture_mismatches(self.fixture), [])

    def test_gaps_are_printed_as_not_stated(self):
        for post in self.fixture["posts"]:
            text = ot.format_terms(ot.check_post(post)["terms"])
            self.assertIn("not stated", text)  # every fixture post has at least one gap

    def test_arbiter_is_not_stated_across_the_fixture(self):
        # The public snapshot states no dispute route in any sampled post.
        for post in self.fixture["posts"]:
            self.assertFalse(ot.check_post(post)["terms"]["arbiter"]["stated"])


class RuleTests(unittest.TestCase):
    def test_empty_text_states_nothing(self):
        terms = ot.check_terms("")
        self.assertEqual(terms["payment_timing"]["stated"], [])
        for term in ("escrow", "arbiter", "preview"):
            self.assertFalse(terms[term]["stated"])
            self.assertEqual(terms[term]["evidence"], [])

    def test_payment_before(self):
        self.assertEqual(ot.check_terms("Fund first and I start.")["payment_timing"]["stated"],
                         ["before"])

    def test_payment_before_is_negated(self):
        terms = ot.check_terms("No prepayment and no deposit required.")
        self.assertEqual(terms["payment_timing"]["stated"], [])

    def test_a_deposit_paid_after_delivery_is_not_a_before_term(self):
        # A bare `deposit` used to report `before` whatever the sentence
        # said about timing.
        terms = ot.check_terms("I will accept a deposit only after delivery.")
        self.assertEqual(terms["payment_timing"]["stated"], ["after delivery"])

    def test_a_deferring_qualifier_after_the_deposit_phrase_removes_before(self):
        # The deposit phrase used to read `before` while the same clause
        # said "only after". A same-clause "but only" qualifier must defer
        # too.
        for text in ("I will pay a deposit only after delivery.",
                     "Deposit is required only after delivery.",
                     "Deposit is required but only after delivery."):
            with self.subTest(text=text):
                self.assertEqual(ot.check_terms(text)["payment_timing"]["stated"],
                                 ["after delivery"])

    def test_a_deferred_deposit_keeps_its_evidence(self):
        terms = ot.check_terms("I will pay a deposit only after delivery.")
        self.assertEqual(terms["payment_timing"]["evidence"],
                         ["I will pay a deposit only after delivery."])

    def test_a_deferring_qualifier_stays_inside_its_clause(self):
        # A comma ends the clause: the first deposit is still prepaid.
        self.assertEqual(
            ot.check_terms("Deposit first, payment after delivery.")["payment_timing"]["stated"],
            ["before", "after delivery"])
        # A following sentence is not a qualifier for this one.
        self.assertEqual(
            ot.check_terms("Pay a deposit. On delivery, I send the files.")["payment_timing"]["stated"],
            ["before"])

    def test_a_qualified_deposit_still_counts_as_before(self):
        for text in ("A 50% deposit is required.",
                     "Pay a deposit before work starts.",
                     "Deposit first, then I start."):
            with self.subTest(text=text):
                self.assertEqual(ot.check_terms(text)["payment_timing"]["stated"], ["before"])

    def test_a_seller_side_refusal_of_prepayment_is_not_a_buyer_term(self):
        text = "I don't do: anything requiring KYC, staking, or prepayment from my side."
        self.assertEqual(ot.check_terms(text)["payment_timing"]["stated"], [])

    def test_payment_on_acceptance(self):
        self.assertEqual(ot.check_terms("You pay on acceptance.")["payment_timing"]["stated"],
                         ["on acceptance"])

    def test_payment_after_delivery(self):
        self.assertEqual(ot.check_terms("Deliver first; payment on delivery.")["payment_timing"]["stated"],
                         ["after delivery"])

    def test_payment_keeps_every_stated_timing(self):
        terms = ot.check_terms("Delivered before payment, settled on acceptance.")
        self.assertEqual(terms["payment_timing"]["stated"],
                         ["on acceptance", "after delivery"])

    def test_a_negation_earlier_in_the_sentence_does_not_swallow_the_term(self):
        terms = ot.check_terms("This is not an earnings claim. Deliver first.")
        self.assertEqual(terms["payment_timing"]["stated"], ["after delivery"])

    def test_escrow(self):
        self.assertTrue(ot.check_terms("Funds are held in escrow.")["escrow"]["stated"])

    def test_escrow_is_negated(self):
        self.assertFalse(ot.check_terms("There is no escrow available.")["escrow"]["stated"])

    def test_escrow_mentioned_as_a_check_is_not_an_offer(self):
        text = "The report says whether escrow or a funded balance is publicly visible."
        self.assertFalse(ot.check_terms(text)["escrow"]["stated"])

    def test_arbiter(self):
        self.assertTrue(ot.check_terms("Disputes go to platform arbitration.")["arbiter"]["stated"])

    def test_third_party_mediator(self):
        self.assertTrue(ot.check_terms("A third-party mediator decides.")["arbiter"]["stated"])

    def test_arbiter_is_negated(self):
        self.assertFalse(ot.check_terms("There is no third-party mediator.")["arbiter"]["stated"])

    def test_preview(self):
        self.assertTrue(ot.check_terms("Try a free sample before ordering.")["preview"]["stated"])

    def test_preview_is_negated(self):
        self.assertFalse(ot.check_terms("No free sample is offered.")["preview"]["stated"])

    def test_sample_of_data_is_not_a_preview(self):
        self.assertFalse(ot.check_terms("Send redacted samples only.")["preview"]["stated"])

    def test_every_stated_term_carries_evidence(self):
        terms = ot.check_terms("Deliver first. Funds held in escrow. A mediator decides. Free preview.")
        self.assertTrue(terms["payment_timing"]["evidence"])
        for term in ("escrow", "arbiter", "preview"):
            self.assertTrue(terms[term]["evidence"])


class OutputTests(unittest.TestCase):
    def test_format_says_not_stated_for_gaps(self):
        text = ot.format_terms(ot.check_terms("Deliver first."))
        self.assertIn("payment timing: after delivery", text)
        self.assertIn("escrow: not stated", text)
        self.assertIn("arbiter: not stated", text)
        self.assertIn("preview: not stated", text)

    def test_cli_text_mode(self):
        code, out, _ = run(["--text", "Deliver first."])
        self.assertEqual(code, 0)
        self.assertIn("payment timing: after delivery", out)

    def test_cli_verify_mode_passes(self):
        code, out, _ = run(["--verify"])
        self.assertEqual(code, 0)
        self.assertIn("matches its hand check", out)

    def test_cli_json_mode_is_pure_json_and_carries_url_and_read_date(self):
        code, out, _ = run(["--json"])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(len(doc["posts"]), 6)
        for post in doc["posts"]:
            self.assertTrue(post["url"].startswith("https://thecolony.ai/"))
            self.assertRegex(post["read_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")

    def test_cli_verify_mode_fails_on_a_wrong_label(self):
        fixture = ot.load_fixture(ot.DEFAULT_FIXTURE)
        fixture["posts"][0]["hand_check"]["preview"] = not fixture["posts"][0]["hand_check"]["preview"]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(fixture, fh)
            path = fh.name
        try:
            code, _, err = run(["--verify", "--fixture", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)
        self.assertIn("preview", err)

    def test_tool_makes_no_network_calls(self):
        with open(ot.__file__, encoding="utf-8") as fh:
            source = fh.read()
        for module in ("urllib", "socket", "requests", "http.client"):
            self.assertNotIn("import " + module, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
