import os, sys, tempfile, unittest, io, contextlib
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tracker


def run(f, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = tracker.main(["--file", f, *args])
        except SystemExit as e:
            code = e.code
    return code, out.getvalue().strip()


class T(unittest.TestCase):
    def setUp(self):
        self.f = os.path.join(tempfile.mkdtemp(), "sub", "t.csv")

    def test_add_dedupe_and_commas(self):
        self.assertEqual(run(self.f, "add", "--company", "Acme, Inc.", "--title", "Welder", "--notes", "a, b")[1], "added 1")
        self.assertEqual(run(self.f, "add", "--company", "ACME Inc", "--title", "welder")[1], "duplicate 1")
        self.assertEqual(run(self.f, "list")[1].split("\t")[3], "Acme, Inc.")

    def test_dedupe_by_linkedin_id(self):
        run(self.f, "add", "--company", "A", "--title", "X", "--url", "https://www.linkedin.com/jobs/view/12345678/")
        self.assertEqual(run(self.f, "seen", "--company", "B", "--title", "Y", "--url", "https://www.linkedin.com/jobs/view/some-title-12345678?x=1")[0], 0)
        self.assertEqual(run(self.f, "seen", "--company", "B", "--title", "Y")[0], 1)

    def test_update_validates_and_appends_notes(self):
        run(self.f, "add", "--company", "A", "--title", "X")
        self.assertNotEqual(run(self.f, "update", "1", "--status", "bogus")[0], 0)
        self.assertNotEqual(run(self.f, "update", "1", "--followup", "tomorrow")[0], 0)
        run(self.f, "update", "1", "--notes", "one")
        run(self.f, "update", "1", "--notes", "two")
        rows = tracker.load(self.f)
        self.assertIn("one", rows[0]["notes"]); self.assertIn("two", rows[0]["notes"])
        self.assertNotEqual(run(self.f, "update", "9", "--status", "applied")[0], 0)

    def test_due_only_open_and_past(self):
        for c in "ABC":
            run(self.f, "add", "--company", c, "--title", "X")
        past = (date.today() - timedelta(days=1)).isoformat()
        future = (date.today() + timedelta(days=5)).isoformat()
        run(self.f, "update", "1", "--status", "applied", "--followup", past)
        run(self.f, "update", "2", "--status", "applied", "--followup", future)
        run(self.f, "update", "3", "--status", "rejected", "--followup", past)
        out = run(self.f, "due")[1]
        self.assertTrue(out.startswith("1\t")); self.assertEqual(len(out.splitlines()), 1)

    def test_formula_guard_and_accents_roundtrip(self):
        run(self.f, "add", "--company", "Caf\u00e9 N\u00fa\u00f1ez", "--title", '=HYPERLINK("http://x","y")', "--notes", "+5 years")
        raw = open(self.f, encoding="utf-8-sig").read()
        self.assertIn("'=HYPERLINK", raw); self.assertIn("'+5 years", raw)
        self.assertTrue(open(self.f, "rb").read().startswith(b"\xef\xbb\xbf"))
        r = tracker.load(self.f)[0]
        self.assertEqual((r["company"], r["title"], r["notes"]), ("Caf\u00e9 N\u00fa\u00f1ez", '=HYPERLINK("http://x","y")', "+5 years"))
        self.assertEqual(run(self.f, "seen", "--company", "Caf\u00e9 N\u00fa\u00f1ez", "--title", '=HYPERLINK("http://x","y")')[0], 0)
        self.assertIn("found\t1", run(self.f, "summary")[1])

    def test_location_fit_and_nudges(self):
        run(self.f, "add", "--company", "Acme", "--title", "Welder", "--location", "Dayton")
        self.assertEqual(run(self.f, "add", "--company", "Acme", "--title", "Welder", "--location", "Toledo")[1], "added 2")
        self.assertEqual(run(self.f, "add", "--company", "Acme", "--title", "Welder", "--location", "dayton")[1], "duplicate 1")
        self.assertNotEqual(run(self.f, "update", "1", "--fit", "banana")[0], 0)
        self.assertNotEqual(run(self.f, "add", "--company", "B", "--title", "X", "--fit", "9")[0], 0)
        past = (date.today() - timedelta(days=1)).isoformat()
        run(self.f, "update", "1", "--status", "applied", "--followup", past)
        self.assertEqual(len(run(self.f, "due")[1].splitlines()), 1)
        run(self.f, "update", "1", "--sent"); run(self.f, "update", "1", "--sent")
        self.assertEqual(tracker.load(self.f)[0]["nudges"], "2")
        self.assertEqual(run(self.f, "due")[1], "")


if __name__ == "__main__":
    unittest.main()
