"""Test `ci_cd.tasks.update_deps()`."""
# pylint: disable=line-too-long,too-many-lines
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal


def test_update_deps(tmp_path: "Path", caplog: pytest.LogCaptureFixture) -> None:
    """Check update_deps runs with defaults."""
    import re

    import tomlkit
    from invoke import MockContext

    from ci_cd.tasks import update_deps

    original_dependencies = {
        "invoke": "1.7",
        "tomlkit": "0.11.4",
        "mike": "1.1",
        "pytest": "7.1",
        "pytest-cov": "3.0",
        "pre-commit": "2.20",
        "pylint": "2.13",
    }

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data=f"""
[project]
requires-python = "~=3.7"

dependencies = [
    "invoke ~={original_dependencies['invoke']}",
    "tomlkit[test,docs] ~={original_dependencies['tomlkit']}",
]

[project.optional-dependencies]
docs = [
    "mike >={original_dependencies['mike']},<3",
]
testing = [
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~={original_dependencies['pytest-cov']}",
]
dev = [
    "mike >={original_dependencies['mike']},<3",
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~={original_dependencies['pytest-cov']}",
    "pre-commit ~={original_dependencies['pre-commit']}",
    "pylint ~={original_dependencies['pylint']}",
]

# List from https://peps.python.org/pep-0508/#complete-grammar
pep_508 = [
    "A",
    "A.B-C_D",
    "aa",
    "name",
    "name1<=1",
    "name2>=3",
    "name3>=3,<2",
    "name4@http://foo.com",
    "name5 [fred,bar] @ http://foo.com ; python_version=='2.7'",
    "name6[quux, strange];python_version<'2.7' and platform_version=='2'",
    "name7; os_name=='a' or os_name=='b'",
    # Should parse as (a and b) or c
    "name8; os_name=='a' and os_name=='b' or os_name=='c'",
    # Overriding precedence -> a and (b or c)
    "name9; os_name=='a' and (os_name=='b' or os_name=='c')",
    # should parse as a or (b and c)
    "name10; os_name=='a' or os_name=='b' and os_name=='c'",
    # Overriding precedence -> (a or b) and c
    "name11; (os_name=='a' or os_name=='b') and os_name=='c'",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            **{
                re.compile(r".*invoke$"): "invoke (1.7.1)\n",
                re.compile(r".*tomlkit$"): "tomlkit (1.0.0)",
                re.compile(r".*mike$"): "mike (1.0.1)",
                re.compile(r".*pytest$"): "pytest (7.1.0)",
                re.compile(r".*pytest-cov$"): "pytest-cov (3.1.0)",
                re.compile(r".*pre-commit$"): "pre-commit (2.20.0)",
                re.compile(r".*pylint$"): "pylint (2.14.0)",
                re.compile(r".* A$"): "A (1.2.3)",
                re.compile(r".*A.B-C_D$"): "A.B-C_D (1.2.3)",
                re.compile(r".*aa$"): "aa (1.2.3)",
                re.compile(r".*name$"): "name (1.2.3)",
            },
            **{re.compile(rf".*name{i}$"): f"name{i} (1.2.3)" for i in range(1, 12)},
        }
    )

    update_deps(
        context,
        root_repo_path=str(tmp_path),
    )

    pyproject = tomlkit.loads(pyproject_file.read_bytes())

    dependencies: list[str] = pyproject.get("project", {}).get("dependencies", [])
    for optional_deps in (
        pyproject.get("project", {}).get("optional-dependencies", {}).values()
    ):
        dependencies.extend(optional_deps)

    for line in dependencies:
        if any(
            line.startswith(package_name)
            for package_name in ["invoke ", "pytest ", "pre-commit "]
        ):
            package_name = line.split(maxsplit=1)[0]
            assert line == f"{package_name} ~={original_dependencies[package_name]}"
        elif "tomlkit" in line:
            # Should be three version digits, since the original dependency had three.
            assert line == "tomlkit[test,docs] ~=1.0.0"
        elif "mike" in line:
            assert line == "mike >=1.0,<3"
        elif "pytest-cov" in line:
            assert line == "pytest-cov ~=3.1"
        elif "pylint" in line:
            assert line == "pylint ~=2.14"
        elif any(
            package_name == line for package_name in ["A", "A.B-C_D", "aa", "name"]
        ) or any(
            line.startswith(package_name)
            for package_name in [f"name{i}" for i in range(6, 12)]
        ):
            package_name = line.split(";", maxsplit=1)[0].strip()
            assert (
                f"{package_name!r} is not version restricted and will be skipped."
                in caplog.text
            )
            if ";" in line:
                assert "os_name" in line or (
                    "python_version" in line and "platform_version" in line
                )
        elif "name1" in line:
            assert line == "name1<=1"
        elif "name2" in line:
            assert line == "name2>=3"
        elif "name3" in line:
            assert line == "name3>=3,<2"
        elif "name4" in line:
            assert line == "name4@http://foo.com"
            assert "'name4' is pinned to a URL and will be skipped" in caplog.text
        elif "name5" in line:
            assert line == "name5 [fred,bar] @ http://foo.com ; python_version=='2.7'"
            assert (
                "'name5 [fred,bar]' is pinned to a URL and will be skipped"
                in caplog.text
            )
        else:
            pytest.fail(f"Unknown package in line: {line}")


@pytest.mark.parametrize(
    argnames=("entries", "separator", "expected_outcome"),
    argvalues=[
        (
            ["dependency-name=test...versions=>2.2.2"],
            "...",
            {"test": {"versions": [">2.2.2"]}},
        ),
        (
            [
                "dependency-name=test...versions=>2.2.2...update-types=version-update:semver-patch"
            ],
            "...",
            {
                "test": {
                    "versions": [">2.2.2"],
                    "update-types": ["version-update:semver-patch"],
                }
            },
        ),
        (
            [
                "dependency-name=test;versions=>2.2.2;update-types=version-update:semver-patch"
            ],
            ";",
            {
                "test": {
                    "versions": [">2.2.2"],
                    "update-types": ["version-update:semver-patch"],
                }
            },
        ),
        (
            [
                "dependency-name=test...versions=>2.2.2...update-types=version-update:semver-patch",
                "dependency-name=test...versions=<3",
            ],
            "...",
            {
                "test": {
                    "versions": [">2.2.2", "<3"],
                    "update-types": ["version-update:semver-patch"],
                }
            },
        ),
        (
            [
                "dependency-name=test;versions=>2.2.2;update-types=version-update:semver-patch",
                "dependency-name=test;versions=<3",
            ],
            ";",
            {
                "test": {
                    "versions": [">2.2.2", "<3"],
                    "update-types": ["version-update:semver-patch"],
                }
            },
        ),
        (
            [
                "dependency-name=test...versions=>2.2.2...update-types=version-update:semver-patch",
                "dependency-name=test...versions=<3...update-types=version-update:semver-major",
            ],
            "...",
            {
                "test": {
                    "versions": [">2.2.2", "<3"],
                    "update-types": [
                        "version-update:semver-patch",
                        "version-update:semver-major",
                    ],
                }
            },
        ),
        (
            [
                "dependency-name=test;versions=>2.2.2;update-types=version-update:semver-patch",
                "dependency-name=test;versions=<3;update-types=version-update:semver-major",
            ],
            ";",
            {
                "test": {
                    "versions": [">2.2.2", "<3"],
                    "update-types": [
                        "version-update:semver-patch",
                        "version-update:semver-major",
                    ],
                }
            },
        ),
        (["dependency-name=test"], "...", {"test": {}}),
    ],
)
def test_parse_ignore_entries(
    entries: list[str],
    separator: str,
    expected_outcome: 'dict[str, dict[Literal["dependency-name", "versions", "update-types"], str]]',
) -> None:
    """Check the `--ignore` option values are parsed as expected."""
    from ci_cd.tasks.update_deps import parse_ignore_entries

    parsed_entries = parse_ignore_entries(
        entries=entries,
        separator=separator,
    )
    assert (
        parsed_entries == expected_outcome
    ), f"""Failed for:
  entries={entries}
  separator={separator}

Expected outcome:
{expected_outcome}

Instead, parse_ignore_entries() returned:
{parsed_entries}
"""


@pytest.mark.parametrize(
    argnames=("rules", "expected_outcome"),
    argvalues=[
        ({"versions": [">2.2.2"]}, ([{"operator": ">", "version": "2.2.2"}], {})),
        (
            {"versions": [">2.2.2"], "update-types": ["version-update:semver-patch"]},
            ([{"operator": ">", "version": "2.2.2"}], {"version-update": ["patch"]}),
        ),
        (
            {
                "versions": [">2.2.2", "<3"],
                "update-types": ["version-update:semver-patch"],
            },
            (
                [
                    {"operator": ">", "version": "2.2.2"},
                    {"operator": "<", "version": "3"},
                ],
                {"version-update": ["patch"]},
            ),
        ),
        (
            {
                "versions": [">2.2.2", "<3"],
                "update-types": [
                    "version-update:semver-patch",
                    "version-update:semver-major",
                ],
            },
            (
                [
                    {"operator": ">", "version": "2.2.2"},
                    {"operator": "<", "version": "3"},
                ],
                {"version-update": ["patch", "major"]},
            ),
        ),
        ({}, ([{"operator": ">=", "version": "0"}], {})),
    ],
)
def test_parse_ignore_rules(
    rules: 'dict[Literal["versions", "update-types"], list[str]]',
    expected_outcome: "tuple[list[dict[Literal['operator', 'version'], str]], dict[Literal['version-update'], list[Literal['major', 'minor', 'patch']]]]",
) -> None:
    """Check a specific set of ignore rules is parsed as expected."""
    from ci_cd.tasks.update_deps import parse_ignore_rules

    parsed_rules = parse_ignore_rules(rules=rules)
    assert (
        parsed_rules == expected_outcome
    ), f"""Failed for:
  rules={rules}

Expected outcome:
{expected_outcome}

Instead, parse_ignore_rules() returned:
{parsed_rules}
"""


def _parametrize_ignore_version() -> (
    "dict[str, tuple[str, str, list[dict[Literal['operator', 'version'], str]], dict[Literal['version-update'], list[Literal['major', 'minor', 'patch']]], bool]]"
):
    """Utility function for `test_ignore_version()`.

    The parametrized inputs are created in this function in order to have more
    meaningful IDs in the runtime overview.
    """
    test_cases: "list[tuple[str, str, list[dict[Literal['operator', 'version'], str]], dict[Literal['version-update'], list[Literal['major', 'minor', 'patch']]], bool]]" = [
        ("1.1.1", "2.2.2", [{"operator": ">", "version": "2.2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": ">", "version": "2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": ">", "version": "2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": ">=", "version": "2.2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": ">=", "version": "2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": ">=", "version": "2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "<", "version": "2.2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "<", "version": "2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "<", "version": "2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "<=", "version": "2.2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "<=", "version": "2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "<=", "version": "2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "==", "version": "2.2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "==", "version": "2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "==", "version": "2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "!=", "version": "2.2.2"}], {}, False),
        ("1.1.1", "2.2.2", [{"operator": "!=", "version": "2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "!=", "version": "2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "~=", "version": "2.2.2"}], {}, True),
        ("1.1.1", "2.2.2", [{"operator": "~=", "version": "2.2"}], {}, True),
        ("1.1.1", "1.1.2", [{"operator": "~=", "version": "1.1"}], {}, True),
        ("1.1.1", "1.1.2", [{"operator": "~=", "version": "1.0"}], {}, True),
        ("1.1.1", "1.1.2", [{"operator": "~=", "version": "1.2"}], {}, False),
        ("1.1.1", "2.2.2", [], {"version-update": ["major"]}, True),
        ("1.1.1", "2.2.2", [], {"version-update": ["minor"]}, False),
        ("1.1.1", "2.2.2", [], {"version-update": ["patch"]}, False),
        ("1.1.1", "1.2.2", [], {"version-update": ["major"]}, False),
        ("1.1.1", "2.1.2", [], {"version-update": ["minor"]}, False),
        ("1.1.1", "2.2.1", [], {"version-update": ["patch"]}, False),
        ("1.1.1", "1.2.1", [], {"version-update": ["minor"]}, True),
        ("1.1.1", "1.1.2", [], {"version-update": ["patch"]}, True),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">", "version": "2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": ">=", "version": "2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<", "version": "2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "<=", "version": "2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "==", "version": "2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            False,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "!=", "version": "2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "2.2.2",
            [{"operator": "~=", "version": "2.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.1"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.1"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.1"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.0"}],
            {"version-update": ["major"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.0"}],
            {"version-update": ["minor"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.0"}],
            {"version-update": ["patch"]},
            True,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.2"}],
            {"version-update": ["major"]},
            False,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.2"}],
            {"version-update": ["minor"]},
            False,
        ),
        (
            "1.1.1",
            "1.1.2",
            [{"operator": "~=", "version": "1.2"}],
            {"version-update": ["patch"]},
            True,
        ),
        ("1.1.1", "1.1.2", [], {}, True),
    ]
    res: "dict[str, tuple[str, str, list[dict[Literal['operator', 'version'], str]], dict[Literal['version-update'], list[Literal['major', 'minor', 'patch']]], bool]]" = (
        {}
    )
    for test_case in test_cases:
        if test_case[2] and test_case[3]:
            operator_version = ",".join(
                f"{_['operator']}{_['version']}" for _ in test_case[2]
            )
            res[
                f"{operator_version} + "
                f"semver-{test_case[3]['version-update']}-latest={test_case[1]}"
            ] = test_case
        elif test_case[2]:
            res[
                ",".join(f"{_['operator']}{_['version']}" for _ in test_case[2])
            ] = test_case
        elif test_case[3]:
            res[
                f"semver-{test_case[3]['version-update']}-latest={test_case[1]}"
            ] = test_case
        else:
            res["no rules"] = test_case
    assert len(res) == len(test_cases)
    return res


@pytest.mark.parametrize(
    argnames=("current", "latest", "version_rules", "semver_rules", "expected_outcome"),
    argvalues=list(_parametrize_ignore_version().values()),
    ids=list(_parametrize_ignore_version()),
)
def test_ignore_version(
    current: str,
    latest: str,
    version_rules: "list[dict[Literal['operator', 'version'], str]]",
    semver_rules: "dict[Literal['version-update'], list[Literal['major', 'minor', 'patch']]]",
    expected_outcome: bool,
) -> None:
    """Check the expected ignore rules are resolved correctly."""
    from ci_cd.tasks.update_deps import ignore_version

    assert (
        ignore_version(
            current=current.split("."),
            latest=latest.split("."),
            version_rules=version_rules,
            semver_rules=semver_rules,
        )
        == expected_outcome
    ), f"""Failed for:
  current={current.split(".")}
  latest={latest.split(".")}
  version_rules={version_rules}
  semver_rules={semver_rules}

Expected outcome: {expected_outcome}
Instead, ignore_version() is {not expected_outcome}
"""


def test_ignore_version_fails() -> None:
    """Ensure `InputParserError` is raised for unknown ignore options."""
    from ci_cd.exceptions import InputError, InputParserError
    from ci_cd.tasks.update_deps import ignore_version

    with pytest.raises(InputParserError, match=r"^Unknown ignore options 'versions'.*"):
        ignore_version(
            current="1.1.1".split("."),
            latest="2.2.2".split("."),
            version_rules=[{"operator": "===", "version": "2.2.2"}],
            semver_rules={},
        )

    with pytest.raises(
        InputParserError, match=r"^Only valid values for 'version-update' are.*"
    ):
        ignore_version(
            current="1.1.1".split("."),
            latest="2.2.2".split("."),
            version_rules=[],
            semver_rules={"version-update": ["build"]},  # type: ignore[list-item]
        )

    with pytest.raises(
        InputError, match=r"Ignore option value error. For the 'versions' config key.*"
    ):
        ignore_version(
            current="1.1.1".split("."),
            latest="2.2.2".split("."),
            version_rules=[{"operator": "~=", "version": "2"}],
            semver_rules={},
        )


def test_ignore_rules_logic(tmp_path: "Path") -> None:
    """Check the workflow of multiple interconnecting ignore rules are respected."""
    import re

    import tomlkit
    from invoke import MockContext

    from ci_cd.tasks import update_deps

    original_dependencies = {
        "invoke": "1.7",
        "tomlkit": "0.11.4",
        "mike": "1.1",
        "pytest": "7.1",
        "pytest-cov": "3.0",
        "pre-commit": "2.20",
        "pylint": "2.13",
    }

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data=f"""
[project]
requires-python = "~=3.7"

dependencies = [
    "invoke ~={original_dependencies['invoke']}",
    "tomlkit[test,docs] ~={original_dependencies['tomlkit']}",
]

[project.optional-dependencies]
docs = [
    "mike >={original_dependencies['mike']},<3",
]
testing = [
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~={original_dependencies['pytest-cov']}",
]
dev = [
    "mike >={original_dependencies['mike']},<3",
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~={original_dependencies['pytest-cov']}",
    "pre-commit ~={original_dependencies['pre-commit']}",
    "pylint ~={original_dependencies['pylint']}",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            re.compile(r".*invoke$"): "invoke (1.7.1)",
            re.compile(r".*tomlkit$"): "tomlkit (1.0.0)",
            re.compile(r".*mike$"): "mike (1.0.1)",
            re.compile(r".*pytest$"): "pytest (7.2.0)",
            re.compile(r".*pytest-cov$"): "pytest-cov (3.1.0)",
            re.compile(r".*pre-commit$"): "pre-commit (2.20.0)",
            re.compile(r".*pylint$"): "pylint (2.14.0)",
        },
    )

    update_deps(
        context,
        root_repo_path=str(tmp_path),
        ignore=[
            "dependency-name=*...update-types=version-update:semver-major",
            "dependency-name=invoke...versions=>=2",
            "dependency-name=mike...versions=<1",
            "dependency-name=mike...versions=<=1.0.0",
            "dependency-name=pylint...versions=~=2.14",
            "dependency-name=pytest-cov...update-types=version-update:semver-minor",
            "dependency-name=pytest",
        ],
        ignore_separator="...",
    )

    pyproject = tomlkit.loads(pyproject_file.read_bytes())

    dependencies: list[str] = pyproject.get("project", {}).get("dependencies", [])
    for optional_deps in (
        pyproject.get("project", {}).get("optional-dependencies", {}).values()
    ):
        dependencies.extend(optional_deps)

    for line in dependencies:
        if "invoke" in line:
            # Not affected by package-specific rule
            assert line == "invoke ~=1.7"
        elif "tomlkit" in line:
            # Affected by "*" rule
            assert line == "tomlkit[test,docs] ~=0.11.4"
        elif "mike" in line:
            # Not affected by any of its package-specific rules
            assert line == "mike >=1.0,<3"
        elif "pytest-cov" in line:
            # Affected by its package-specific update-types rule
            assert line == "pytest-cov ~=3.0"
        elif "pytest" in line:
            # Affected by package-specific rule (ignore all updates)
            assert line == "pytest ~=7.1"
        elif "pre-commit" in line:
            # Not affected by "*" rule - no updates
            assert line == "pre-commit ~=2.20"
        elif "pylint" in line:
            # Affected by its package-specific version rule
            assert line == "pylint ~=2.13"
        else:
            pytest.fail(f"Unknown package in line: {line}")