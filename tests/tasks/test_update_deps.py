"""Test `ci_cd.tasks.update_deps()`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def test_update_deps(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Check update_deps runs with defaults."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    original_dependencies = {
        "invoke": "1.7",
        "tomlkit": "0.11.4",
        "mike": "1!1.1",
        "pytest": "7.1",
        "pytest-cov": "3.0",
        "pre-commit": "2.20",
        "pylint": "2.13",
    }

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data=f"""
[project]
name = "test"
requires-python = "~=3.7"

dependencies = [
    "invoke ~={original_dependencies['invoke']}",
    "tomlkit[test,docs] ~={original_dependencies['tomlkit']}",
]

[project.optional-dependencies]
docs = [
    "mike >={original_dependencies['mike']},<1!3",
]
testing = [
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~={original_dependencies['pytest-cov']},!=3.1",
    "test-pkg <=1!3,!=1!2.0.1",
]
dev = [
    "mike >={original_dependencies['mike']},<1!3",
    "pre-commit~={original_dependencies['pre-commit']}",
    # "pylint ~={original_dependencies['pylint']},!=2.14.*",
    "test[testing]",
]

# Test epochs
epoch = [
    "epoch>=2!1.2,<2!2",
    "epoch1~=2023.1.1",
    "epoch2~=1!1.0",
    "epoch3~=1!1.0.1",
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
            re.compile(r".*invoke$"): "invoke (1.7.1.post1)\n",
            re.compile(r".*tomlkit$"): "tomlkit (1.0.0)",
            re.compile(r".*mike$"): "mike (1!1.1.1)",
            re.compile(r".*pytest$"): "pytest (7.1.0)",
            re.compile(r".*pytest-cov$"): "pytest-cov (3.1.5)",
            re.compile(r".*pre-commit$"): "pre-commit (2.21.5)",
            re.compile(r".*pylint$"): "pylint (2.14.2)",
            re.compile(r".* A$"): "A (1.2.3)",
            re.compile(r".*A.B-C_D$"): "A.B-C_D (1.2.3)",
            re.compile(r".*aa$"): "aa (1.2.3)",
            re.compile(r".*name$"): "name (1.2.3)",
            re.compile(r".*test-pkg$"): "test-pkg (1!2.3)",
            re.compile(r".*epoch$"): "epoch (2!2.0.4.post1)",
            re.compile(r".*epoch1$"): "epoch1 (1!1.0.0)",
            re.compile(r".*epoch2$"): "epoch2 (1!2.1.0)",
            re.compile(r".*epoch3$"): "epoch3 (1!1.1.0.post1)",
            **{re.compile(rf".*name{i}$"): f"name{i} (3.2.1)" for i in range(1, 12)},
        }
    )

    # Expected changes:
    # - Extras should be sorted alphabetically (tomlkit).
    # - Original white space between name and specifiers should be respected
    #   (pep_508 vs. the rest)
    # - All name# with a version specifier should be updated to include the latest
    #   version (explicit change in name1)
    # - Similar formatting, even if the dependency is otherwise skipped
    #   (name4 to name11)
    # - Acknowledge that !=3.1 expands to !=3.1.0, so 3.1.5 is allowed (pytest-cov)
    # - TODO: Acknowledge that !=2.14.* includes not wanting *all* sub-versions of 2.14,
    #   so 2.14.2 is excluded and should not be part of the updated specifier set
    #   (pylint)
    expected_updated_pyproject_file = f"""
[project]
name = "test"
requires-python = "~=3.7"

dependencies = [
    "invoke ~={original_dependencies['invoke']}",
    "tomlkit[docs,test] >={original_dependencies['tomlkit']},<2",
]

[project.optional-dependencies]
docs = [
    "mike >={original_dependencies['mike']},<1!3",
]
testing = [
    "pytest ~={original_dependencies['pytest']}",
    "pytest-cov ~=3.1,!=3.1",
    "test-pkg <=1!3,!=1!2.0.1",
]
dev = [
    "mike >={original_dependencies['mike']},<1!3",
    "pre-commit~=2.21",
    # "pylint ~={original_dependencies['pylint']},!=2.14.*",
    "test[testing]",
]

# Test epochs
epoch = [
    "epoch>=2!1.2,<2!3",
    "epoch1~=2023.1.1,==1!1.0.0",
    "epoch2>=1!1.0.0,<1!3",
    "epoch3~=1!1.1.0",
]

# List from https://peps.python.org/pep-0508/#complete-grammar
pep_508 = [
    "A",
    "A.B-C_D",
    "aa",
    "name",
    "name1<=3",
    "name2>=3",
    "name3>=3,<2",
    "name4@ http://foo.com",
    "name5[bar,fred] @ http://foo.com ; python_version == '2.7'",
    "name6[quux,strange]; python_version < '2.7' and platform_version == '2'",
    "name7; os_name == 'a' or os_name == 'b'",
    # Should parse as (a and b) or c
    "name8; os_name == 'a' and os_name == 'b' or os_name == 'c'",
    # Overriding precedence -> a and (b or c)
    "name9; os_name == 'a' and (os_name == 'b' or os_name == 'c')",
    # should parse as a or (b and c)
    "name10; os_name == 'a' or os_name == 'b' and os_name == 'c'",
    # Overriding precedence -> (a or b) and c
    "name11; (os_name == 'a' or os_name == 'b') and os_name == 'c'",
]
"""

    update_deps(
        context,
        root_repo_path=str(tmp_path),
    )

    updated_pyproject_file = pyproject_file.read_text(encoding="utf8")

    assert updated_pyproject_file == expected_updated_pyproject_file

    # Check the non-version restricted packages are skipped with a message
    for package_name in ["A", "A.B-C_D", "aa", "name"] + [
        f"name{i}" for i in range(6, 12)
    ]:
        assert (
            f"{package_name!r} is not version restricted and will be skipped."
            in caplog.text
        )

    # Check a warning is not emitted for the non-version inter-relative dependency.
    assert (
        "'test[testing]' is not version restricted and will be skipped."
        not in caplog.text
    )

    # Check the URL pinned packages are skipped with a message
    for package_name in ["name4", "name5"]:
        assert f"{package_name!r} is pinned to a URL and will be skipped" in caplog.text

    # Check the already up-to-date packages are skipped with a message
    for package_name in ["invoke", "mike", "pytest"]:
        assert f"Package {package_name!r} is already up-to-date" in caplog.text


@pytest.mark.parametrize(
    ("ignore_rules", "expected_result"),
    [
        (
            ["dependency-name=*...update-types=version-update:semver-major"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[test,docs] ~=0.11.4",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<6",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <2",
            },
        ),
        (
            ["dependency-name=invoke...versions=>=2"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<7",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
        (
            [
                "dependency-name=mike...versions=<1",
                "dependency-name=mike...versions=<=1.0.0",
            ],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<7",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
        (
            ["dependency-name=pylint...versions=~=2.14"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<7",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
        (
            ["dependency-name=pytest"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.1",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<7",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
        (
            ["dependency-name=pytest-cov...update-types=version-update:semver-minor"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.0,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<7",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
        (
            ["dependency-name=Sphinx...versions=>=4.5.0"],
            {
                "invoke": "invoke ~=1.7",
                "tomlkit": "tomlkit[docs,test] >=0.11.4,<2",
                "mike": "mike >=1.1,<3",
                "pytest": "pytest ~=7.2",
                "pytest-cov": "pytest-cov ~=3.1,!=3.1.0",
                "pre-commit": "pre-commit~=2.20",
                "pylint": "pylint ~=2.13,!=2.14",
                "Sphinx": "Sphinx >=4.5.0,<6",
                "test": "test[docs,testing]",
                "urllib3": "urllib3 <3",
            },
        ),
    ],
    ids=[
        "* semver-major",
        "invoke >=2",
        "mike <1 <=1.0.0",
        "pylint ~=2.14",
        "pytest",
        "pytest-cov semver-minor",
        "Sphinx >=4.5.0",
    ],
)
def test_ignore_rules_logic(
    tmp_path: Path, ignore_rules: list[str], expected_result: dict[str, str]
) -> None:
    """Check the workflow of multiple interconnecting ignore rules are respected."""
    import re

    import tomlkit
    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data="""
[project]
name = "test"
requires-python = "~=3.7"

dependencies = [
    "invoke ~=1.7",
    "tomlkit[test,docs] ~=0.11.4",
    "urllib3 <2",
]

[project.optional-dependencies]
docs = [
    "mike >=1.1,<3",
    "Sphinx >=4.5.0,<6",
]
testing = [
    "pytest ~=7.1",
    "pytest-cov ~=3.0,!=3.1.0",
]
dev = [
    "pre-commit~=2.20",
    "pylint ~=2.13,!=2.14",
    "test[docs,testing]",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            re.compile(r".*invoke$"): "invoke (1.7.1)",
            re.compile(r".*tomlkit$"): "tomlkit (1.0.0)",
            re.compile(r".*mike$"): "mike (1.1.1)",
            re.compile(r".*pytest$"): "pytest (7.2.0)",
            re.compile(r".*pytest-cov$"): "pytest-cov (3.1.1)",
            re.compile(r".*pre-commit$"): "pre-commit (2.20.0)",
            re.compile(r".*pylint$"): "pylint (2.14.0)",
            re.compile(r".*Sphinx$"): "Sphinx (6.1.3)",
            re.compile(r".*urllib3$"): "urllib3 (2.0.3)",
        },
    )

    update_deps(
        context,
        root_repo_path=str(tmp_path),
        ignore=ignore_rules,
        ignore_separator="...",
    )

    pyproject = tomlkit.loads(pyproject_file.read_bytes())

    dependencies: list[str] = pyproject.get("project", {}).get("dependencies", [])
    for optional_deps in (
        pyproject.get("project", {}).get("optional-dependencies", {}).values()
    ):
        dependencies.extend(optional_deps)

    for line in dependencies:
        for dependency, dependency_requirement in expected_result.items():
            # Assert the dependency in the updated pyproject.toml file equals the
            # expected value.
            # We have to use a regular expression to match the dependency name as some
            # dependency names are sub-strings of each other (like 'pytest' is a
            # sub-string of 'pytest-cov').
            if re.match(rf"{re.escape(dependency)}\s*(~|>|\[|<).*", line):
                assert line == dependency_requirement
                break
        else:
            pytest.fail(f"Unknown package in line: {line}")


def test_python_version_marker(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Check the python version marker is respected."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data="""
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "oteapi-core ~=0.1.0; python_version <= '3.7'",
    "oteapi-core ~=0.2.0; python_version > '3.7'",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            re.compile(r".*3.7 oteapi-core$"): "oteapi-core (0.1.9)",
            re.compile(r".*3.8 oteapi-core$"): "oteapi-core (1.0.1)",
        }
    )

    expected_updated_pyproject_file = """
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "oteapi-core ~=0.1.9; python_version <= '3.7'",
    "oteapi-core >=0.2.0,<2; python_version > '3.7'",
]
"""

    update_deps(
        context,
        root_repo_path=str(tmp_path),
    )

    updated_pyproject_file = pyproject_file.read_text(encoding="utf8")

    assert updated_pyproject_file == expected_updated_pyproject_file

    assert "Min/max Python version from marker: 3.7" in caplog.text
    assert "Min/max Python version from marker: 3.8" in caplog.text


def test_no_warn_when_project_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Check no warning is emitted if a dependency is also the project name.

    This is only relevant when no specifiers are given.
    """
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data="""
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "oteapi-core ~=0.2.0",
]

[project.optional-dependencies]
docs = [
    "mkdocs >=1.1,<2",
]
dev = [
    "ci-cd[docs]",
    "pytest",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            re.compile(r".*oteapi-core$"): "oteapi-core (2.0.0)",
            re.compile(r".*mkdocs$"): "mkdocs (1.2.3)",
            re.compile(r".*pytest$"): "pytest (7.4.3)",
        }
    )

    expected_updated_pyproject_file = """
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "oteapi-core >=0.2.0,<3",
]

[project.optional-dependencies]
docs = [
    "mkdocs >=1.1,<2",
]
dev = [
    "ci-cd[docs]",
    "pytest",
]
"""

    update_deps(
        context,
        root_repo_path=str(tmp_path),
    )

    updated_pyproject_file = pyproject_file.read_text(encoding="utf8")

    assert updated_pyproject_file == expected_updated_pyproject_file

    assert (
        "Dependency 'pytest' is not version restricted and will be skipped."
        in caplog.text
    )
    assert (
        "Dependency 'ci-cd' is not version restricted and will be skipped."
        not in caplog.text
    )


@pytest.mark.parametrize("verbose_flag", [True, False])
def test_verbose(
    verbose_flag: bool,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Check the verbose flag is respected.

    Any logged messaged should be written to stdout IF the verbose flag is set.
    Check that any expected log messages are found both in the logs and in stdout.

    If the verbose flag is not set, the messages should ONLY appear in the logs.
    """
    from invoke import MockContext

    from ci_cd.tasks import update_deps

    with pytest.raises(
        SystemExit,
        match=(
            r".*Error: Could not find the Python package repository's "
            r"'pyproject.toml' file.*"
        ),
    ):
        update_deps(MockContext(), root_repo_path=str(tmp_path), verbose=verbose_flag)

    captured_output = capsys.readouterr().out

    # Expected log messages - note the strings are sub-strings of the full log messages
    assert (
        "Verbose logging enabled." in caplog.text
        if verbose_flag
        else "Verbose logging enabled." not in caplog.text
    )
    assert "Parsed ignore rules:" in caplog.text

    # Assert the above messages are the only messages in the logs
    assert len(caplog.messages) == 2 if verbose_flag else 1

    # Go through the log messages and ensure they either are or are not in stdout
    for log_message in caplog.messages:
        assert (
            log_message in captured_output
            if verbose_flag
            else log_message not in captured_output
        )


def test_wrongly_formatted_ignore_entries() -> None:
    """Check an error is raised if the ignore rules are incorrectly formatted."""
    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    with pytest.raises(
        SystemExit,
        match=r".*Error: Could not parse ignore options.*",
    ):
        # Should be "dependency-name", not "dependency"
        update_deps(MockContext(), ignore=["dependency=pytest"])


def test_non_parseable_pyproject_toml(tmp_path: Path) -> None:
    """Check an error is raised if the pyproject.toml file cannot be parsed."""
    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text("invalid toml file", encoding="utf8")

    with pytest.raises(
        SystemExit,
        match=r".*Error: Could not parse the 'pyproject.toml' file",
    ):
        update_deps(MockContext(), root_repo_path=str(tmp_path))


@pytest.mark.parametrize(
    "requires_python",
    ["", 'requires-python = "invalid"', 'requires-python = "3.7"'],
    ids=["missing", "invalid", "missing operator"],
)
def test_no_requires_python_in_pyproject_toml(
    tmp_path: Path, requires_python: str
) -> None:
    """Check an error is raised if the pyproject.toml file does not have a (valid)
    requires-python key."""
    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data=f"""
[project]
name = "ci-cd"
{requires_python}
""",
        encoding="utf8",
    )

    with pytest.raises(
        SystemExit,
        match=r".*Error: Cannot determine minimum Python version",
    ):
        update_deps(MockContext(), root_repo_path=str(tmp_path))


def test_missing_project_package_name(tmp_path: Path) -> None:
    """Check an error is raised if the pyproject.toml file does not have a (valid)
    name key."""
    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data="""
[project]
requires-python = "~=3.7"
""",
        encoding="utf8",
    )

    with pytest.raises(
        SystemExit,
        match=r".*Error: Could not find the Python project's name.*",
    ):
        update_deps(MockContext(), root_repo_path=str(tmp_path))


@pytest.mark.parametrize(
    ("dependency", "optional_dependency", "fail_fast"),
    [
        ("(pytest)", "", False),
        ("", "(pytest)", False),
        ("(pytest)", "(pytest-cov)", False),
        ("(pytest)", "(pytest-cov)", True),
    ],
    ids=["dependency", "optional-dependency", "both", "both, but fail_fast"],
)
def test_invalid_requirement(
    tmp_path: Path,
    dependency: str,
    optional_dependency: str,
    fail_fast: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """Check an error is raised if a dependency requirement is invalid."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps
    from ci_cd.utils.console_printing import Color, Emoji, error_msg

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data=f"""
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [{repr(dependency) if dependency else ""}]

[project.optional-dependencies]
dev = [{repr(optional_dependency) if optional_dependency else ""}]
""",
        encoding="utf8",
    )

    log_msg = "Could not parse requirement '{bad_dependency}' from pyproject.toml: "

    if fail_fast:
        # We test failing fast
        # The first dependency to be checked will be the ones from `dependencies`,
        # hence we'd expect the error to be raised for that one.
        raise_msg = (
            f"^{re.escape(Emoji.CROSS_MARK.value)} "
            f"{re.escape(error_msg(log_msg.format(bad_dependency=dependency))[:-len(Color.RESET.value)])}.*"
        )
    else:
        raise_msg = r".*Errors occurred! See printed statements above\.$"

    with pytest.raises(SystemExit, match=raise_msg):
        update_deps(MockContext(), root_repo_path=str(tmp_path), fail_fast=fail_fast)

    captured_stderr = capsys.readouterr().err

    active_dependencies = [_ for _ in [dependency, optional_dependency] if _]

    for bad_dependency in active_dependencies:
        formatted_log_msg = log_msg.format(bad_dependency=bad_dependency)
        formatted_terminal_msg = re.escape(
            error_msg(formatted_log_msg)[: -len(Color.RESET.value)]
        )

        formatted_log_msg = re.escape(formatted_log_msg)

        if fail_fast:
            # Here we test failing fast, so _only_ the first dependency should be
            # checked before the error is raised.
            if bad_dependency == dependency:
                # The error message should not be findable in stderr (or stdout) - it is
                # already checked in the raise statement above.
                # It SHOULD however be present in the logs.
                assert (
                    re.search(formatted_log_msg, caplog.text) is not None
                ), formatted_log_msg
                assert (
                    re.search(formatted_terminal_msg, captured_stderr) is None
                ), formatted_terminal_msg
            else:
                assert (
                    re.search(formatted_log_msg, caplog.text) is None
                ), formatted_log_msg
                assert (
                    re.search(formatted_terminal_msg, captured_stderr) is None
                ), formatted_terminal_msg
        else:
            assert (
                re.search(formatted_log_msg, caplog.text) is not None
            ), formatted_log_msg
            assert (
                re.search(formatted_terminal_msg, captured_stderr) is not None
            ), captured_stderr


@pytest.mark.parametrize("fail_fast", [True, False])
def test_non_parseable_pip_index_versions(
    tmp_path: Path,
    fail_fast: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """Check an error is raised if the pip index versions cannot be parsed."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps
    from ci_cd.utils.console_printing import Emoji, error_msg

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        data="""
[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "pytest ~=7.0",
]
""",
        encoding="utf8",
    )

    context = MockContext(
        run={
            re.compile(r"^pip index versions.*"): "invalid output",
        }
    )

    log_msg = (
        "Could not parse package and version from 'pip index versions' output for "
        "line:\n  invalid output"
    )
    terminal_msg = re.compile(re.escape(error_msg(log_msg)))

    if fail_fast:
        # We test failing fast
        # The error message will be part of the exception, and will not be in stdout or
        # stderr. It SHOULD however be present in the logs.
        raise_msg = (
            f"^{re.escape(Emoji.CROSS_MARK.value)} {re.escape(error_msg(log_msg))}$"
        )
    else:
        raise_msg = (
            rf"^{re.escape(Emoji.CROSS_MARK.value)} Errors occurred! See printed "
            r"statements above\.$"
        )

    with pytest.raises(SystemExit, match=raise_msg):
        update_deps(context, root_repo_path=str(tmp_path), fail_fast=fail_fast)

    assert re.search(log_msg, caplog.text) is not None, log_msg

    if fail_fast:
        assert terminal_msg.search(capsys.readouterr().err) is None, terminal_msg
    else:
        assert terminal_msg.search(capsys.readouterr().err) is not None, terminal_msg


def test_no_dependency_updates_available(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture
) -> None:
    """Check no changes are incurred if no dependency updates are available."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file_data = """[project]
name = "ci-cd"
requires-python = "~=3.6"

dependencies = [
    "pytest ~=7.0",
]
"""
    pyproject_file.write_text(data=pyproject_file_data, encoding="utf8")

    context = MockContext(
        run={
            re.compile(r".*pytest.*"): "pytest (7.0.10)",
        }
    )

    msg = re.compile(r"No dependency updates available")

    update_deps(context, root_repo_path=str(tmp_path))

    assert "'pytest' is already up-to-date." in caplog.text

    assert msg.search(capsys.readouterr().out) is not None, msg

    assert pyproject_file.read_text(encoding="utf8") == pyproject_file_data


@pytest.mark.parametrize("pre_commit", [True, False])
def test_pre_commit(tmp_path: Path, pre_commit: bool) -> None:
    """Check pre-commit toggle."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps

    git_repo = tmp_path / "sub_folder"
    git_repo.mkdir()
    pyproject_file_git_repo = git_repo / "pyproject.toml"
    pyproject_file_data_git_repo = """[project]
name = "ci-cd"
requires-python = "~=3.8"

dependencies = ["pre-commit ~=2.21"]
"""
    pyproject_file_git_repo.write_text(
        data=pyproject_file_data_git_repo, encoding="utf8"
    )

    pyproject_file_tmp_path = tmp_path / "pyproject.toml"
    pyproject_file_data_tmp_path = """[project]
name = "ci-cd"
requires-python = "~=3.8"

dependencies = ["pytest ~=7.0"]
"""
    pyproject_file_tmp_path.write_text(
        data=pyproject_file_data_tmp_path, encoding="utf8"
    )

    context = MockContext(
        run={
            re.compile(r"^git rev-parse --show-toplevel$"): f"{git_repo.resolve()}\n",
            re.compile(r".*pre-commit$"): "pre-commit (3.5.0)",
            re.compile(r".*pytest$"): "pytest (7.4.3)",
        }
    )

    update_deps(
        context,
        root_repo_path="." if pre_commit else str(tmp_path),
        pre_commit=pre_commit,
    )

    if pre_commit:
        # The git folder pyproject.toml should be updated
        assert (
            pyproject_file_git_repo.read_text(encoding="utf8")
            == """[project]
name = "ci-cd"
requires-python = "~=3.8"

dependencies = ["pre-commit >=2.21.0,<4"]
"""
        )

        # The tmp_path pyproject.toml should have no changes
        assert pyproject_file_tmp_path.read_text(encoding="utf8") == (
            pyproject_file_data_tmp_path
        )

    else:
        # The git folder pyproject.toml should have no changes
        assert (
            pyproject_file_git_repo.read_text(encoding="utf8")
            == pyproject_file_data_git_repo
        )

        # The tmp_path pyproject.toml should have have changed
        assert (
            pyproject_file_tmp_path.read_text(encoding="utf8")
            == """[project]
name = "ci-cd"
requires-python = "~=3.8"

dependencies = ["pytest ~=7.4"]
"""
        )


@pytest.mark.parametrize("fail_fast", [True, False])
def test_unresolvable_specifier_set(
    tmp_path: Path,
    fail_fast: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """Ensure an error is raised if the specifier set is unresolvable.

    The specifier operator '===' is not supported by the current implementation.
    """
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps
    from ci_cd.utils.console_printing import Emoji, error_msg

    pyproject_file_data = """[project]
name = "ci-cd"
requires-python = ">=3.8"

dependencies = ["pytest===7.0"]
"""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(data=pyproject_file_data, encoding="utf8")

    context = MockContext(
        run={
            re.compile(r".*pytest$"): "pytest (7.0.0)",
        }
    )

    core_msg = (
        "Could not determine how to update to the latest version using the version "
        "range specifier set: ===7.0. Package: pytest. Latest version: 7.0.0"
    )
    log_msg = (
        f"{core_msg}. Exception: Cannot resolve how to update specifier set to include "
        "latest version."
    )
    terminal_msg = re.compile(re.escape(error_msg(core_msg)))

    if fail_fast:
        # We test failing fast
        # The error message will be part of the exception, and will not be in stdout or
        # stderr. It SHOULD however be present in the logs.
        raise_msg = (
            f"^{re.escape(Emoji.CROSS_MARK.value)} {re.escape(error_msg(core_msg))}$"
        )
    else:
        raise_msg = (
            rf"^{re.escape(Emoji.CROSS_MARK.value)} Errors occurred! See printed "
            r"statements above\.$"
        )

    with pytest.raises(SystemExit, match=raise_msg):
        update_deps(context, root_repo_path=str(tmp_path), fail_fast=fail_fast)

    assert pyproject_file.read_text(encoding="utf8") == pyproject_file_data

    assert (
        re.search(log_msg, caplog.text) is not None
    ), f"{log_msg!r} not found in {caplog.text}"

    if fail_fast:
        assert terminal_msg.search(capsys.readouterr().err) is None, terminal_msg
    else:
        assert terminal_msg.search(capsys.readouterr().err) is not None, terminal_msg


@pytest.mark.parametrize("skip_unnormalized_python_package_names", [True, False])
@pytest.mark.parametrize("fail_fast", [True, False])
def test_skip_unnormalized_python_package_names(
    tmp_path: Path,
    skip_unnormalized_python_package_names: bool,
    fail_fast: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    """Ensure unnormalized Python package names are skipped."""
    import re

    from invoke import MockContext

    from ci_cd.tasks.update_deps import update_deps
    from ci_cd.utils.console_printing import Emoji, error_msg, info_msg

    pyproject_file_data = """[project]
name = "{{ cookiecutter.project_slug }}"
requires-python = ">=3.8"

dependencies = []

[project.optional-dependencies]
dev = ["pytest~=7.1"]
all = ["{{ cookiecutter.project_slug }}[dev]"]
"""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(data=pyproject_file_data, encoding="utf8")

    context = MockContext(
        run={
            re.compile(r".*pytest$"): "pytest (7.4.3)",
        }
    )

    exception_message = (
        "Expected package name at the start of dependency "
        "specifier\n    {{ cookiecutter.project_slug }}[dev]\n    ^"
    )

    core_error_msg = (
        "Could not parse requirement '{{ cookiecutter.project_slug }}[dev]' from "
        f"pyproject.toml: {exception_message}"
    )
    core_info_msg = (
        "Skipping requirement '{{ cookiecutter.project_slug }}[dev]', as unnormalized "
        "Python package naming is allowed by user. Note, the requirements could "
        f"not be parsed: {exception_message}"
    )

    terminal_error_msg = re.compile(re.escape(error_msg(core_error_msg)))
    terminal_info_msg = re.compile(re.escape(info_msg(core_info_msg)))

    if fail_fast:
        # We test failing fast
        # The error message will be part of the exception, and will not be in stdout or
        # stderr. It SHOULD however be present in the logs.
        raise_msg = (
            f"^{re.escape(Emoji.CROSS_MARK.value)} "
            f"{re.escape(error_msg(core_error_msg))}$"
        )
    else:
        raise_msg = (
            rf"^{re.escape(Emoji.CROSS_MARK.value)} Errors occurred! See printed "
            r"statements above\.$"
        )

    # Due to an atomistic approach, if an error occurs, the pyproject.toml file will
    # not be updated.
    successful_expected_pyproject_file_data = """[project]
name = "{{ cookiecutter.project_slug }}"
requires-python = ">=3.8"

dependencies = []

[project.optional-dependencies]
dev = ["pytest~=7.4"]
all = ["{{ cookiecutter.project_slug }}[dev]"]
"""
    erroneous_expected_pyproject_file_data = pyproject_file_data

    if skip_unnormalized_python_package_names:
        # This should end in success
        update_deps(
            context,
            root_repo_path=str(tmp_path),
            skip_unnormalized_python_package_names=skip_unnormalized_python_package_names,
            fail_fast=fail_fast,
        )

        stdouterr = capsys.readouterr()

        assert (
            re.search(re.escape(core_info_msg), caplog.text) is not None
        ), f"{core_info_msg!r} not found in {caplog.text}"
        assert (
            terminal_info_msg.search(stdouterr.out) is not None
        ), f"{terminal_info_msg!r} not found in {stdouterr.out}"

        assert (
            re.search(re.escape(core_error_msg), caplog.text) is None
        ), f"{core_error_msg!r} unexpectedly found in {caplog.text}"
        assert (
            terminal_error_msg.search(stdouterr.err) is None
        ), f"{terminal_error_msg!r} unexpectedly found in {stdouterr.err}"

        assert (
            pyproject_file.read_text(encoding="utf8")
            == successful_expected_pyproject_file_data
        )

    else:
        # This should end in failure
        with pytest.raises(SystemExit, match=raise_msg):
            update_deps(
                context,
                root_repo_path=str(tmp_path),
                skip_unnormalized_python_package_names=(
                    skip_unnormalized_python_package_names
                ),
                fail_fast=fail_fast,
            )

        stdouterr = capsys.readouterr()

        assert (
            re.search(re.escape(core_error_msg), caplog.text) is not None
        ), f"{core_error_msg!r} not found in {caplog.text}"

        assert (
            re.search(re.escape(core_info_msg), caplog.text) is None
        ), f"{core_info_msg!r} unexpectedly found in {caplog.text}"
        assert (
            terminal_info_msg.search(stdouterr.out) is None
        ), f"{terminal_info_msg!r} unexpectedly found in {stdouterr.out}"

        if fail_fast:
            assert (
                terminal_error_msg.search(stdouterr.err) is None
            ), f"{terminal_error_msg!r} unexpectedly found in {stdouterr.err}"
        else:
            assert (
                terminal_error_msg.search(stdouterr.err) is not None
            ), f"{terminal_error_msg!r} not found in {stdouterr.err}"

        assert (
            pyproject_file.read_text(encoding="utf8")
            == erroneous_expected_pyproject_file_data
        )
