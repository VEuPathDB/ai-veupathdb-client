from __future__ import annotations

from pathlib import Path

import pytest

from veupathdb.devtools.param_equality import main, scan

_FORMS = {
    "wire": "def f(a, b):\n    return a.to_wire() == b.to_wire()\n",
    "function": "def f(a, b):\n    return to_wire(a) != to_wire(b)\n",
    "map": "def f(a, b):\n    return wire_map(a) == wire_map(b)\n",
    "dumps": "def f(a, b):\n    return json.dumps(a) != b\n",
    "encoded": "def f(a, b):\n    return encode_wdk_params(a) != encode_wdk_params(b)\n",
    "set": "def f(a, b):\n    return {to_wire(v) for v in a} == {to_wire(v) for v in b}\n",
    "length": "def f(rows, n):\n    return len({r.params[n].to_wire() for r in rows}) > 1\n",
    "member": "def f(v, seen):\n    return v.to_wire() in seen\n",
    "absent": "def f(v, seen):\n    return to_wire(v) not in seen\n",
    "str": "def f(a, b):\n    return str(a) == b\n",
    "dump": "def f(a, b):\n    return a.model_dump() == b.model_dump()\n",
    "get": "def f(a, b, n):\n    return wire_map(a).get(n) == b\n",
    "local": "def f(a, b):\n    x = a.to_wire()\n    y = b.to_wire()\n    return x == y\n",
    "tuple": "def f(a, b, n):\n    return (n, to_wire(a)) == (n, to_wire(b))\n",
}


@pytest.mark.parametrize("form", sorted(_FORMS))
def test_a_wire_text_comparison_is_found(tmp_path: Path, form: str) -> None:
    (tmp_path / "mod.py").write_text(_FORMS[form])

    assert [f.key for f in scan([tmp_path], tmp_path)] == ["mod.py:f"]


@pytest.mark.parametrize(
    "source",
    [
        "def f(a, b):\n    return a == b\n",
        "def f(a, b):\n    return a.parameters != b.parameters\n",
        "def f(n, values):\n    return n in wire_map(values)\n",
        "def f(v, seen):\n    return v in seen\n",
        "def f(v):\n    text = v.to_wire()\n    return len(text) > 40\n",
    ],
    ids=["values", "maps", "key-membership", "value-membership", "text-length"],
)
def test_a_value_comparison_is_not_found(tmp_path: Path, source: str) -> None:
    (tmp_path / "mod.py").write_text(source)

    assert scan([tmp_path], tmp_path) == []


def test_the_equality_module_is_not_read(tmp_path: Path) -> None:
    module = tmp_path / "veupathdb" / "domain" / "parameters" / "value_equality.py"
    module.parent.mkdir(parents=True)
    module.write_text(_FORMS["wire"])

    assert scan([tmp_path], tmp_path) == []


def test_an_allowed_comparison_passes_and_a_stale_allowance_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text(_FORMS["wire"])
    allow = tmp_path / "allowed.txt"
    allow.write_text("mod.py:f\n")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 0

    allow.write_text("mod.py:f\nmod.py:g\n")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 1
    assert "mod.py:g is allowed but compares nothing" in capsys.readouterr().out


def test_a_comparison_not_allowed_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text(_FORMS["local"])
    allow = tmp_path / "allowed.txt"
    allow.write_text("")

    assert main([str(tmp_path), "--allow", str(allow), "--base", str(tmp_path)]) == 1
    assert "mod.py:4 f: compares the wire text held in x" in capsys.readouterr().out
