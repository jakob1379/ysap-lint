"""Every labelled example from https://style.ysap.sh/ (MIT, Dave Eddy).

guide_examples.json holds the guide's own snippets, indentation converted to
tabs. "right" snippets must lint clean; "wrong" ones must raise the listed
codes. A "wrong" snippet with no codes is a rule the linter does not enforce.
"""

import json
from pathlib import Path

import pytest

from ysap_lint.linter import lint

EXAMPLES = json.loads(
    (Path(__file__).parent / "guide_examples.json").read_text())


def _id(example):
    return f"{example['section']}:{example['source'].splitlines()[0][:30]}"


@pytest.mark.parametrize(
    "example", [e for e in EXAMPLES if e["kind"] == "right"], ids=_id)
def test_right_examples_are_clean(example):
    assert [(d.line + 1, d.code) for d in lint(example["source"])] == []


@pytest.mark.parametrize(
    "example", [e for e in EXAMPLES if e["kind"] == "wrong"], ids=_id)
def test_wrong_examples_are_flagged(example):
    found = {d.code for d in lint(example["source"])}
    assert set(example["expect"]) <= found


def test_unenforced_guide_rules_are_known():
    unenforced = [e["section"] for e in EXAMPLES
                  if e["kind"] == "wrong" and not e["expect"]]
    assert unenforced == ["Block Statements"]
