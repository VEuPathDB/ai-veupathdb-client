from __future__ import annotations

from pathlib import Path

import pytest

from veupathdb.devtools.param_equality import main, scan

_COMPARISONS = {
    "wire": "def f(a, b):\n    return a.to_wire() == b.to_wire()\n",
    "dumps": "import json\ndef f(a, b):\n    return json.dumps(a) != b\n",
    "maps": "def f(a, b):\n    return dict(a.parameters) != dict(b.parameters)\n",
    "entry": "def f(a, b, n):\n    return a.params[n] == b\n",
    "kind": "def f(a):\n    return a == MultiPickValue(values=['x'])\n",
}


@pytest.mark.parametrize("source", sorted(_COMPARISONS))
def test_a_comparison_outside_the_equality_is_found(
    tmp_path: Path, source: str
) -> None:
    (tmp_path / "mod.py").write_text(_COMPARISONS[source])

    assert [(f.key, f.line) for f in scan([tmp_path], tmp_path)] == [
        ("mod.py:f", 2 if source != "dumps" else 3)
    ]


def test_a_value_compared_through_the_equality_is_not_found(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "def f(n, a, b):\n    return same_param_value(n, None, a, b) and a is not b\n"
    )

    assert scan([tmp_path], tmp_path) == []


def test_the_equality_module_is_not_read(tmp_path: Path) -> None:
    module = tmp_path / "veupathdb" / "domain" / "parameters" / "value_equality.py"
    module.parent.mkdir(parents=True)
    module.write_text(_COMPARISONS["wire"])

    assert scan([tmp_path], tmp_path) == []


def test_an_allowed_comparison_passes_and_a_stale_allowance_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text(_COMPARISONS["wire"])
    allow = tmp_path / "allowed.txt"
    allow.write_text("mod.py:f\n")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 0

    allow.write_text("mod.py:f\nmod.py:g\n")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 1
    assert "mod.py:g is allowed but compares nothing" in capsys.readouterr().out


def test_a_comparison_not_allowed_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text(_COMPARISONS["maps"])
    allow = tmp_path / "allowed.txt"
    allow.write_text("")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 1
    assert "mod.py:2 f: compares a parameter map" in capsys.readouterr().out
