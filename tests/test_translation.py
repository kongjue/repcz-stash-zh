import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sync_upstream import NAMES, ROOT, translate, validate


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "upstream/Stash.yaml").read_text()
        self.original = yaml.safe_load(self.source)
        self.result = yaml.safe_load(translate(self.source, "example/stash-zh"))

    def test_only_labels_references_and_rule_hosts_change(self):
        restored = copy.deepcopy(self.result)
        inverse = {v: k for k, v in NAMES.items()}
        for group in restored["proxy-groups"]:
            group["name"] = inverse[group["name"]]
            if "proxies" in group:
                group["proxies"] = [inverse.get(n, n) for n in group["proxies"]]
        restored["rules"] = [
            ",".join(r.split(",")[:-1] + [inverse.get(r.split(",")[-1], r.split(",")[-1])])
            for r in restored["rules"]
        ]
        for name, provider in restored["rule-providers"].items():
            provider["url"] = self.original["rule-providers"][name]["url"]
        self.assertEqual(restored, self.original)

    def test_no_subscription_is_embedded(self):
        self.assertEqual(self.result["proxy-providers"], self.original["proxy-providers"])
        self.assertEqual(self.result.get("subscribe-url"), self.original.get("subscribe-url"))

    def test_new_upstream_group_requires_review(self):
        changed = self.source.replace("name: Manual,", "name: NewUpstreamGroup,", 1)
        with self.assertRaises(ValueError):
            translate(changed, "example/stash-zh")

    def test_broken_references_and_cycles_rejected(self):
        broken = copy.deepcopy(self.result)
        broken["proxy-groups"][0]["proxies"] = ["missing-group"]
        with self.assertRaises(ValueError):
            validate(broken)
        broken["proxy-groups"][0]["proxies"] = [broken["proxy-groups"][0]["name"]]
        with self.assertRaises(ValueError):
            validate(broken)


if __name__ == "__main__":
    unittest.main()
