import os, sys, unittest, io, contextlib
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ats_scan

NOW = datetime.now(timezone.utc)
OLD = (NOW - timedelta(days=90)).isoformat()
NEW = (NOW - timedelta(days=2)).isoformat()
FEEDS = {
    ("greenhouse", "acme"): {"jobs": [
        {"title": "Sales Manager, Midwest", "location": {"name": "Columbus, OH"}, "first_published": NEW, "absolute_url": "u1"},
        {"title": "Sales Manager", "location": {"name": "Austin, TX"}, "first_published": NEW, "absolute_url": "u2"},
        {"title": "Sales Manager", "location": {"name": "Columbus, OH"}, "first_published": OLD, "absolute_url": "u3"},
        {"title": "Engineer", "location": {"name": "Columbus, OH"}, "first_published": NEW, "absolute_url": "u4"}]},
    ("lever", "beta"): [{"text": "Team Lead, Sales", "categories": {"allLocations": ["Remote - US"]}, "createdAt": int(NOW.timestamp() * 1000), "hostedUrl": "u5"}],
    ("ashby", "gamma"): {"jobs": [{"title": " Sales Director ", "location": "NYC", "isRemote": True, "publishedAt": None, "jobUrl": "u6"}]},
}


def fake(provider, slug):
    if (provider, slug) in FEEDS:
        return FEEDS[(provider, slug)]
    raise OSError("404")


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        ats_scan.main(list(args), fetch=fake)
    return out.getvalue().splitlines(), err.getvalue()


class T(unittest.TestCase):
    def test_filters_title_location_age(self):
        rows, _ = run("--company", "acme", "--keyword", "sales manager", "--location", "columbus", "--days", "30")
        self.assertEqual([r.split("\t")[4] for r in rows], ["u1"])

    def test_tries_all_providers_and_keeps_undated(self):
        rows, _ = run("--company", "beta", "--company", "gamma", "--keyword", "sales", "--location", "remote", "--days", "7")
        self.assertEqual(sorted(r.split("\t")[4] for r in rows), ["u5", "u6"])
        self.assertIn("undated", rows[1])

    def test_missing_feed_reported(self):
        rows, err = run("--company", "nope", "--keyword", "x")
        self.assertEqual(rows, []); self.assertIn("no feed found for nope", err)


if __name__ == "__main__":
    unittest.main()
