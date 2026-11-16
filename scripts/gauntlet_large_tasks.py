"""Task families for the large gauntlet (synthetic repos, stdlib unittest verifiers + hidden intent tests).

Every task has a visible verifier (what the pipeline may use) and a hidden test (never shown to any model or
resolver) that encodes the true intent; a pipeline acceptance whose hidden test fails is a false accept.
Roles: cold (1), heldout (3), warm (2), near (near-miss: same failure shape, reviewed resolver not applicable),
decoy (resolver applies but its edit is wrong -> verifier must refuse), far (no family), dual (lattice composite).
"""
from __future__ import annotations

import json
from typing import Any

PY = "/usr/bin/python3"


def _task(family: str, role: str, pkg: str, files: dict[str, str], target: str, visible: str, hidden: str,
          tests_run: int = 2) -> dict[str, Any]:
    files = {f"{pkg}/__init__.py": "", **files, f"test_{pkg}_contract.py": visible}
    return {"family": family, "role": role, "pkg": pkg, "files": files, "target": target,
            "verify": [PY, "-m", "unittest", f"test_{pkg}_contract"], "tests_run": tests_run,
            "hidden": {f"test_{pkg}_hidden.py": hidden}, "hidden_verify": [PY, "-m", "unittest", f"test_{pkg}_hidden"]}


def _unit(imports: str, cases: list[tuple[str, str]]) -> str:
    body = "".join(f"    def test_{name}(self):\n" + "".join(f"        {line}\n" for line in code.split("\n")) + "\n"
                   for name, code in cases)
    return f"import unittest\n{imports}\n\n\nclass Contract(unittest.TestCase):\n{body}"


# -- F1 config constant -----------------------------------------------------------------------------------------
def constant(role: str, pkg: str, name: str, old: Any, new: Any, other: tuple[str, Any]) -> dict[str, Any]:
    cfg = f'"""{pkg} configuration."""\n\n{other[0]} = {other[1]!r}\n{name} = {old!r}\n'
    vis = _unit(f"from {pkg}.config import {name}, {other[0]}",
                [(f"{name.lower()}_contract", f"self.assertEqual({name}, {new!r})"),
                 (f"{other[0].lower()}_unchanged", f"self.assertEqual({other[0]}, {other[1]!r})")])
    hid = _unit(f"from {pkg} import config", [("intent", f"self.assertEqual(config.{name}, {new!r})\n"
                                                         f"self.assertEqual(config.{other[0]}, {other[1]!r})")])
    return _task("fix-config-constant", role, pkg, {f"{pkg}/config.py": cfg}, f"{pkg}/config.py", vis, hid)


def constant_near(pkg: str) -> dict[str, Any]:
    cfg = f'"""{pkg} configuration."""\n\nMIN_WORKERS = 3\nRETRY_LIMIT = 3\n'
    vis = _unit(f"from {pkg}.config import RETRY_LIMIT, MIN_WORKERS",
                [("retry_limit_contract", "self.assertEqual(RETRY_LIMIT, 5)"),
                 ("min_workers_unchanged", "self.assertEqual(MIN_WORKERS, 3)")])
    hid = _unit(f"from {pkg} import config", [("intent", "self.assertEqual((config.RETRY_LIMIT, config.MIN_WORKERS), (5, 3))")])
    return _task("fix-config-constant", "near", pkg, {f"{pkg}/config.py": cfg}, f"{pkg}/config.py", vis, hid)


def constant_decoy(pkg: str) -> dict[str, Any]:
    cfg = f'"""{pkg} policy."""\n\nRETRIES = 3\n\n\ndef max_attempts():\n    return RETRIES\n'
    vis = _unit(f"from {pkg}.config import RETRIES, max_attempts",
                [("max_attempts_includes_initial_and_final", "self.assertEqual(max_attempts(), 5)"),
                 ("retries_pinned", "self.assertEqual(RETRIES, 3)")])
    hid = _unit(f"from {pkg} import config", [("intent", "self.assertEqual((config.RETRIES, config.max_attempts()), (3, 5))")])
    return _task("fix-config-constant", "decoy", pkg, {f"{pkg}/config.py": cfg}, f"{pkg}/config.py", vis, hid)


# -- shared single-function module ---------------------------------------------------------------------------------
def _function_task(family: str, role: str, pkg: str, fn: str, params: str, body: str, test: str, hidden: str,
                   mod: str = "core") -> dict[str, Any]:
    src = (f'"""{pkg} {mod}."""\n\n\ndef {fn}({params}):\n' + "".join(f"    {line}\n" for line in body.split("\n"))
           + "\n\ndef size(items):\n    return len(items)\n")
    vis = _unit(f"from {pkg}.{mod} import {fn}, size", [(f"{fn}_contract", test), ("size_unchanged", "self.assertEqual(size([1, 2]), 2)")])
    hid = _unit(f"from {pkg}.{mod} import {fn}", [("intent", hidden)])
    return _task(family, role, pkg, {f"{pkg}/{mod}.py": src}, f"{pkg}/{mod}.py", vis, hid)


def operator(role: str, pkg: str, fn: str, params: str, expr: str, test: str, hidden: str) -> dict[str, Any]:
    return _function_task("fix-logic-operator", role, pkg, fn, params, f"return {expr}", test, hidden)


def boundary(role: str, pkg: str, fn: str, params: str, expr: str, test: str, hidden: str) -> dict[str, Any]:
    return _function_task("fix-off-by-one", role, pkg, fn, params, f"return {expr}", test, hidden)


def guard(role: str, pkg: str, fn: str, params: str, body: str, test: str, hidden: str) -> dict[str, Any]:
    return _function_task("fix-unhandled-exception", role, pkg, fn, params, body, test, hidden)


def guard_near(pkg: str) -> dict[str, Any]:
    t = guard("near", pkg, "average", "values", f"from {pkg}.helpers import mean\nreturn mean(values)",
              "self.assertIsNone(average([]))", "self.assertIsNone(average([]))\nself.assertEqual(average([2, 4]), 3.0)")
    t["files"][f"{pkg}/helpers.py"] = "def mean(values):\n    return sum(values) / len(values)\n"
    return t


# -- F5 multi-file rename ------------------------------------------------------------------------------------------
def rename(role: str, pkg: str, old: str, new: str, extra_public: str = "") -> dict[str, Any]:
    core = (f'"""{pkg} core."""\n\n\ndef {old}(items):\n    return sum(items)\n\n\n'
            'def format_money(value):\n    return f"${value:.2f}"\n')
    if extra_public:
        core += f"\n\ndef {extra_public}(items):\n    return sum(items) * 2\n"
    files = {f"{pkg}/core.py": core,
             f"{pkg}/report.py": f"from {pkg}.core import {old}, format_money\n\n\ndef summary(items):\n    return format_money({old}(items))\n",
             f"{pkg}/cli.py": f"from {pkg} import core\n\n\ndef main(items):\n    return core.{old}(items)\n"}
    vis = _unit(f"from {pkg}.core import {new}\nfrom {pkg}.report import summary\nfrom {pkg}.cli import main",
                [("renamed_symbol", f"self.assertEqual({new}([1, 2]), 3)"),
                 ("call_sites", "self.assertEqual(summary([1, 2]), '$3.00')\nself.assertEqual(main([4]), 4)")])
    hid = _unit(f"from {pkg} import core, report, cli",
                [("intent", f"self.assertFalse(hasattr(core, {old!r}))\nself.assertEqual(core.{new}([2]), 2)\n"
                            "self.assertEqual(report.summary([1]), '$1.00')\nself.assertEqual(cli.main([1, 1]), 2)")])
    return _task("refactor-rename-symbol", role, pkg, files, f"{pkg}/core.py", vis, hid)


# -- F6 tool-chain regenerate ----------------------------------------------------------------------------------------
GEN_TOOL = '''"""Regenerate {pkg}/generated.py from spec.json (repo-declared tool)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[{depth}]


def render(spec):
    lines = ["# generated by {tool} from spec.json -- do not edit"]
    lines += [f"{{key}} = {{spec[key]!r}}" for key in sorted(spec)]
    return "\\n".join(lines) + "\\n"


if __name__ == "__main__":
    (ROOT / "{pkg}" / "generated.py").write_text(render(json.loads((ROOT / "spec.json").read_text())))
'''


def toolchain(role: str, pkg: str, spec: dict[str, Any], stale: dict[str, Any], tool: str = "tools/gen_constants.py",
              hint: str = "tools/gen_constants.py") -> dict[str, Any]:
    depth = tool.count("/")
    mod = tool[:-3].replace("/", ".")
    gen = ["# generated by " + tool + " from spec.json -- do not edit"] + [f"{k} = {stale[k]!r}" for k in sorted(stale)]
    files = {"spec.json": json.dumps(spec, indent=2) + "\n", "tools/__init__.py": "",
             tool: GEN_TOOL.format(pkg=pkg, tool=tool, depth=depth), f"{pkg}/generated.py": "\n".join(gen) + "\n"}
    if depth > 1:
        files[tool.rsplit("/", 1)[0] + "/__init__.py"] = ""
    vis = _unit(f"import json\nimport pathlib\nfrom {mod} import render",
                [("generated_is_fresh", "root = pathlib.Path(__file__).resolve().parent\n"
                                        "expected = render(json.loads((root / 'spec.json').read_text()))\n"
                                        f"actual = (root / '{pkg}' / 'generated.py').read_text()\n"
                                        f"self.assertTrue(actual == expected, 'generated.py is stale: run {hint}')"),
                 ("spec_parses", "root = pathlib.Path(__file__).resolve().parent\n"
                                 "self.assertIsInstance(json.loads((root / 'spec.json').read_text()), dict)")])
    hid = _unit(f"from {pkg} import generated", [("intent", "\n".join(f"self.assertEqual(generated.{k}, {v!r})" for k, v in spec.items()))])
    return _task("toolchain-regenerate", role, pkg, files, f"{pkg}/generated.py", vis, hid)


# -- lattice dual-bug (constant + off-by-one) --------------------------------------------------------------------------
def dual(role: str, pkg: str, const: str, old: int, new: int) -> dict[str, Any]:
    src = f'"""{pkg} paging."""\n\n{const} = {old}\n\n\ndef last_n(items, n):\n    return items[-n - 1:]\n'
    vis = _unit(f"from {pkg}.paging import {const}, last_n",
                [(f"{const.lower()}_contract", f"self.assertEqual({const}, {new})"),
                 ("last_n_contract", "self.assertEqual(last_n([1, 2, 3, 4, 5], 2), [4, 5])")])
    hid = _unit(f"from {pkg} import paging", [("intent", f"self.assertEqual(paging.{const}, {new})\n"
                                                         "self.assertEqual(paging.last_n([1, 2, 3], 1), [3])")])
    return _task("composite", role, pkg, {f"{pkg}/paging.py": src}, f"{pkg}/paging.py", vis, hid)


def dual_diff(role: str, pkg: str, const: str, old: int, new: int) -> dict[str, Any]:
    """Two capabilities, but the second differs from the lattice's (constant + operator bug, not off-by-one)."""
    src = f'"""{pkg} totals."""\n\n{const} = {old}\n\n\ndef net(gross, fee):\n    return gross + fee\n'
    vis = _unit(f"from {pkg}.totals import {const}, net",
                [(f"{const.lower()}_contract", f"self.assertEqual({const}, {new})"),
                 ("net_contract", "self.assertEqual(net(100, 5), 95)")])
    hid = _unit(f"from {pkg} import totals", [("intent", f"self.assertEqual(totals.{const}, {new})\n"
                                                         "self.assertEqual(totals.net(9, 4), 5)")])
    return _task("composite-diff", role, pkg, {f"{pkg}/totals.py": src}, f"{pkg}/totals.py", vis, hid)


def fresh_lattice_tasks(seed: int) -> dict[str, dict[str, Any]]:
    """Generated at run time from a seed (never seen by distillation, held-out or the composite's promotion)."""
    import random

    rng = random.Random(seed)
    tag = f"{rng.randrange(16**4):04x}"
    old = rng.choice([12, 16, 24, 40])
    out = {
        f"fresh-dual-{tag}": dual("fresh", f"orders{tag}", f"ORDER_PAGE_{tag.upper()}", old, old * 3),
        f"fresh-single-{tag}": constant("fresh", f"quota{tag}", f"QUOTA_{tag.upper()}", old, old + 7, ("REGION", "af")),
        f"fresh-diff-{tag}": dual_diff("fresh", f"ledger{tag}", f"LEDGER_CAP_{tag.upper()}", old, old * 2),
    }
    for task in out.values():
        task["family"] = {"composite": "fresh-lattice", "composite-diff": "fresh-lattice-diff"}.get(task["family"], "fresh-single")
    return out


# -- harder lattice: multi-file rename + unhandled exception (rename_symbol then guard_exception) ---------------------
def refguard(role: str, pkg: str, old: str, new: str, *, second: str = "guard") -> dict[str, Any]:
    """Four-module package; the public function must be renamed repo-wide AND its empty-input crash guarded.

    ``second="operator"`` swaps the second capability for an operator bug (negative control: lattice must not complete it).
    """
    if second == "guard":
        body, case = "return sum(items) / len(items)", ("empty_is_none", f"from {pkg}.report import summary\nself.assertIsNone(summary([]))")
        intent = (f"self.assertIsNone(report.summary([]))\nself.assertEqual(core.{new}([2, 4]), 3.0)\n"
                  "self.assertEqual(cli.main([1, 3]), 2.0)\nself.assertEqual(api.handle({'items': [5]}), {'value': 5.0})")
        sample = "self.assertEqual({new}([2, 4]), 3.0)"
    else:
        body, case = "return sum(items) + len(items)", ("net_of_count", f"from {pkg}.report import summary\nself.assertEqual(summary([5, 5]), 8)")
        intent = (f"self.assertEqual(report.summary([4]), 3)\nself.assertEqual(core.{new}([2, 4]), 4)\n"
                  "self.assertEqual(cli.main([1, 3]), 2)\nself.assertEqual(api.handle({'items': [5]}), {'value': 4})")
        sample = "self.assertEqual({new}([2, 4]), 4)"
    files = {f"{pkg}/core.py": f'"""{pkg} core."""\n\n\ndef {old}(items):\n    {body}\n\n\ndef format_value(value):\n    return f"{{value:.2f}}"\n',
             f"{pkg}/report.py": f"from {pkg}.core import {old}\n\n\ndef summary(items):\n    return {old}(items)\n",
             f"{pkg}/cli.py": f"from {pkg} import core\n\n\ndef main(items):\n    return core.{old}(items)\n",
             f"{pkg}/api.py": f"from {pkg}.core import {old}\n\n\ndef handle(payload):\n    return {{'value': {old}(payload['items'])}}\n"}
    vis = _unit("", [("a_renamed_symbol", f"from {pkg}.core import {new}\n" + sample.format(new=new)), (f"b_{case[0]}", case[1])])
    hid = _unit(f"from {pkg} import api, cli, core, report",
                [("intent", f"self.assertFalse(hasattr(core, {old!r}))\n" + intent)])
    family = "composite-refguard" if second == "guard" else "composite-refguard-diff"
    return _task(family, role, pkg, files, f"{pkg}/core.py", vis, hid)


def fresh_lattice2_tasks(seed: int) -> dict[str, dict[str, Any]]:
    """Fresh tasks for the rename+guard lattice, generated from a seed after its promotion."""
    import random

    rng = random.Random(seed)
    tag = f"{rng.randrange(16**4):04x}"
    noun = rng.choice(["score", "latency", "basket", "rating"])
    out = {
        f"fresh-refguard-{tag}": refguard("fresh", f"metrics{tag}", f"calc_{noun}_mean", f"compute_{noun}_mean"),
        f"fresh-rename-{tag}": rename("fresh", f"books{tag}", f"get_{noun}_total", f"fetch_{noun}_total"),
        f"fresh-refop-{tag}": refguard("fresh", f"tally{tag}", f"calc_{noun}_net", f"compute_{noun}_net", second="operator"),
    }
    fam = {"composite-refguard": "fresh-lattice2", "composite-refguard-diff": "fresh-lattice2-diff",
           "refactor-rename-symbol": "fresh-single2"}
    for task in out.values():
        task["family"] = fam[task["family"]]
    return out


def far_tasks() -> list[dict[str, Any]]:
    slug = _function_task("far", "far", "slugs", "slugify", "text", "raise NotImplementedError('slugify')",
                          "self.assertEqual(slugify('Hello World'), 'hello-world')",
                          "self.assertEqual(slugify('A  B c'), 'a-b-c')\nself.assertEqual(slugify('x'), 'x')")
    label = _function_task("far", "far", "labels", "total_label", "total", "return 'total: ' + total",
                           "self.assertEqual(total_label(5), 'total: 5')", "self.assertEqual(total_label(12), 'total: 12')")
    return [slug, label]


def all_tasks() -> dict[str, dict[str, Any]]:
    T: dict[str, dict[str, Any]] = {}
    add = T.__setitem__
    # F1
    add("const-cold", constant("cold", "billing", "INVOICE_RETRY_LIMIT", 3, 5, ("GRACE_DAYS", 14)))
    add("const-h1", constant("heldout", "scheduler", "MAX_WORKERS", 4, 8, ("TICK_MS", 250)))
    add("const-h2", constant("heldout", "auth", "TOKEN_TTL_MINUTES", 15, 30, ("SKEW_SECONDS", 30)))
    add("const-h3", constant("heldout", "cache", "CACHE_MAX_ENTRIES", 512, 1024, ("SHARDS", 8)))
    add("const-w1", constant("warm", "ingest", "BATCH_SIZE", 100, 250, ("LINGER_MS", 20)))
    add("const-w2", constant("warm", "notify", "MAX_EMAILS_PER_HOUR", 50, 60, ("QUIET_HOUR", 22)))
    add("const-near", constant_near("workers"))
    add("const-decoy", constant_decoy("attempts"))
    # F2
    add("op-cold", operator("cold", "fees", "net_amount", "gross, fee", "gross + fee",
                            "self.assertEqual(net_amount(100, 5), 95)", "self.assertEqual(net_amount(10, 3), 7)"))
    add("op-h1", operator("heldout", "geometry", "area", "width, height", "width + height",
                          "self.assertEqual(area(3, 4), 12)", "self.assertEqual(area(5, 2), 10)"))
    add("op-h2", operator("heldout", "gates", "both_ok", "a, b", "a or b",
                          "self.assertEqual(both_ok(True, False), False)\nself.assertEqual(both_ok(True, True), True)",
                          "self.assertFalse(both_ok(False, True))\nself.assertTrue(both_ok(True, True))"))
    add("op-h3", operator("heldout", "ratios", "ratio", "a, b", "a * b",
                          "self.assertEqual(ratio(10, 4), 2.5)", "self.assertEqual(ratio(9, 3), 3)"))
    add("op-w1", operator("warm", "refunds", "refund", "paid, cost", "paid + cost",
                          "self.assertEqual(refund(50, 20), 30)", "self.assertEqual(refund(9, 4), 5)"))
    add("op-w2", operator("warm", "flags", "either_flag", "a, b", "a and b",
                          "self.assertEqual(either_flag(True, False), True)", "self.assertTrue(either_flag(False, True))\nself.assertFalse(either_flag(False, False))"))
    add("op-near", operator("near", "orders", "order_total", "price, qty, fee", "price + qty - fee",
                            "self.assertEqual(order_total(10, 3, 2), 32)", "self.assertEqual(order_total(5, 2, 1), 11)"))
    # F3
    add("obo-cold", boundary("cold", "window", "last_n", "items, n", "items[-n - 1:]",
                             "self.assertEqual(last_n([1, 2, 3, 4, 5], 2), [4, 5])", "self.assertEqual(last_n([1, 2, 3], 1), [3])"))
    add("obo-h1", boundary("heldout", "counter", "count_up", "n", "list(range(1, n))",
                           "self.assertEqual(count_up(3), [1, 2, 3])", "self.assertEqual(count_up(1), [1])"))
    add("obo-h2", boundary("heldout", "ages", "is_adult", "age", "age > 18",
                           "self.assertTrue(is_adult(18))\nself.assertFalse(is_adult(17))", "self.assertTrue(is_adult(30))\nself.assertFalse(is_adult(0))"))
    add("obo-h3", boundary("heldout", "limits", "within", "x, hi", "x < hi",
                           "self.assertTrue(within(10, 10))\nself.assertFalse(within(11, 10))", "self.assertTrue(within(1, 2))\nself.assertFalse(within(3, 2))"))
    add("obo-w1", boundary("warm", "heads", "first_n", "items, n", "items[:n - 1]",
                           "self.assertEqual(first_n([1, 2, 3], 2), [1, 2])", "self.assertEqual(first_n([5, 6], 1), [5])"))
    add("obo-w2", boundary("warm", "evens", "evens_upto", "n", "[i for i in range(0, n, 2)]",
                           "self.assertEqual(evens_upto(4), [0, 2, 4])", "self.assertEqual(evens_upto(2), [0, 2])"))
    add("obo-near", boundary("near", "spans", "span", "lo, hi", "list(range(lo + 1, hi))",
                             "self.assertEqual(span(2, 4), [2, 3, 4])", "self.assertEqual(span(0, 1), [0, 1])"))
    # F4
    add("exc-cold", guard("cold", "fracs", "ratio_of", "text", "num, den = text.split('/')\nreturn int(num) / int(den)",
                          "self.assertIsNone(ratio_of('1/0'))", "self.assertIsNone(ratio_of('5/0'))\nself.assertEqual(ratio_of('6/3'), 2.0)"))
    add("exc-h1", guard("heldout", "ports", "parse_port", "text", "return int(text)",
                        "self.assertEqual(parse_port('abc'), 0)", "self.assertEqual(parse_port('x'), 0)\nself.assertEqual(parse_port('80'), 80)"))
    add("exc-h2", guard("heldout", "tables", "lookup", "table, key", "return table[key]",
                        "self.assertIsNone(lookup({}, 'x'))", "self.assertIsNone(lookup({}, 'y'))\nself.assertEqual(lookup({'a': 1}, 'a'), 1)"))
    add("exc-h3", guard("heldout", "lists", "first", "items", "return items[0]",
                        "self.assertIsNone(first([]))", "self.assertIsNone(first([]))\nself.assertEqual(first([7]), 7)"))
    add("exc-w1", guard("warm", "division", "safe_div", "a, b", "return a / b",
                        "self.assertEqual(safe_div(1, 0), 0.0)", "self.assertEqual(safe_div(4, 0), 0.0)\nself.assertEqual(safe_div(4, 2), 2.0)"))
    add("exc-w2", guard("warm", "settings", "setting", "cfg, key", "return cfg[key]",
                        "self.assertEqual(setting({}, 'mode'), '')", "self.assertEqual(setting({}, 'x'), '')\nself.assertEqual(setting({'m': 'a'}, 'm'), 'a')"))
    add("exc-near", guard_near("stats"))
    # F5
    add("ren-cold", rename("cold", "ledger", "calc_total", "compute_total"))
    add("ren-h1", rename("heldout", "users", "fetch_user", "load_user"))
    add("ren-h2", rename("heldout", "reports", "make_report", "build_report"))
    add("ren-h3", rename("heldout", "configs", "parse_cfg", "parse_config"))
    add("ren-w1", rename("warm", "mailer", "send_mail", "send_email"))
    add("ren-w2", rename("warm", "exporter", "dump_json", "write_json"))
    add("ren-near", rename("near", "totals", "calc_total", "compute_total", extra_public="sum_total"))
    # F6
    add("tool-cold", toolchain("cold", "release", {"VERSION": "1.4.0", "CHANNEL": "stable"}, {"VERSION": "1.3.0", "CHANNEL": "stable"}))
    add("tool-h1", toolchain("heldout", "flagset", {"DARK_MODE": True, "BETA": False}, {"DARK_MODE": False, "BETA": False}))
    add("tool-h2", toolchain("heldout", "regions", {"DEFAULT": "af-south-1", "FALLBACK": "eu-west-1"}, {"DEFAULT": "eu-west-1", "FALLBACK": "eu-west-1"}))
    add("tool-h3", toolchain("heldout", "quotas", {"MAX_RPS": 200, "BURST": 50}, {"MAX_RPS": 100, "BURST": 50}))
    add("tool-w1", toolchain("warm", "pricing", {"CURRENCY": "ZAR", "VAT": 0.15}, {"CURRENCY": "ZAR", "VAT": 0.14}))
    add("tool-w2", toolchain("warm", "localeconf", {"LANG": "en-ZA", "TZ": "Africa/Johannesburg"}, {"LANG": "en-US", "TZ": "UTC"}))
    add("tool-near", toolchain("near", "build", {"TARGET": "x86_64", "OPT": 2}, {"TARGET": "x86_64", "OPT": 0},
                               tool="tools/build/gen_constants.py", hint="tools/gen_constants.py"))
    # lattice composite (constant + off-by-one)
    add("dual-h1", dual("heldout", "pager", "PAGE_SIZE", 10, 20))
    add("dual-h2", dual("heldout", "feed", "FEED_LIMIT", 25, 50))
    add("dual-h3", dual("heldout", "inbox", "INBOX_MAX", 100, 200))
    add("dual-w1", dual("warm", "timeline", "TIMELINE_DEPTH", 30, 60))
    add("refguard-h1", refguard("heldout", "grades", "calc_grade_mean", "compute_grade_mean"))
    add("refguard-h2", refguard("heldout", "sensors", "avg_reading", "mean_reading"))
    add("refguard-h3", refguard("heldout", "carts", "calc_cart_average", "compute_cart_average"))
    add("refguard-w1", refguard("warm", "surveys", "calc_survey_mean", "compute_survey_mean"))
    for i, t in enumerate(far_tasks()):
        add(f"far-{i + 1}", t)
    return T


FAMILY_ORDER = ["fix-config-constant", "fix-logic-operator", "fix-off-by-one", "fix-unhandled-exception",
                "refactor-rename-symbol", "toolchain-regenerate"]
PREFIX = {"fix-config-constant": "const", "fix-logic-operator": "op", "fix-off-by-one": "obo",
          "fix-unhandled-exception": "exc", "refactor-rename-symbol": "ren", "toolchain-regenerate": "tool"}
