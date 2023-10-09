"""`update_deps` task.

Update dependencies in a `pyproject.toml` file.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
from invoke import task
from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from tomlkit.exceptions import TOMLKitError

from ci_cd.exceptions import InputError, UnableToResolve
from ci_cd.utils import (
    Emoji,
    create_ignore_rules,
    error_msg,
    find_minimum_py_version,
    get_min_max_py_version,
    ignore_version,
    info_msg,
    parse_ignore_entries,
    parse_ignore_rules,
    regenerate_requirement,
    update_file,
    update_specifier_set,
    warning_msg,
)

if TYPE_CHECKING:  # pragma: no cover
    from invoke import Context, Result

    from ci_cd.utils.versions import IgnoreUpdateTypes, IgnoreVersions


LOGGER = logging.getLogger(__file__)
LOGGER.setLevel(logging.DEBUG)


def _format_and_update_dependency(
    requirement: Requirement, raw_dependency_line: str, pyproject_path: Path
) -> None:
    """Regenerate dependency without changing anything but the formatting.

    NOTE: If any white space is present after the name (incl. possible extras) it is
    reduced to a single space.
    """
    match = re.search(rf"{requirement.name}(?:\[.*\])?\s+", raw_dependency_line)
    updated_dependency = regenerate_requirement(
        requirement,
        post_name_space=bool(match),
    )
    LOGGER.debug("Regenerated dependency: %r", updated_dependency)
    if updated_dependency != raw_dependency_line:
        # Update pyproject.toml since the dependency formatting has changed
        LOGGER.debug("Updating pyproject.toml for %r", requirement.name)
        update_file(
            pyproject_path,
            (re.escape(raw_dependency_line), updated_dependency.replace('"', "'")),
        )


@task(
    help={
        "fail-fast": (
            "Fail immediately if an error occurs. Otherwise, print and ignore all "
            "non-critical errors."
        ),
        "root-repo-path": (
            "A resolvable path to the root directory of the repository folder."
        ),
        "pre-commit": "Whether or not this task is run as a pre-commit hook.",
        "ignore": (
            "Ignore-rules based on the `ignore` config option of Dependabot. It "
            "should be of the format: key=value...key=value, i.e., an ellipsis "
            "(`...`) separator and then equal-sign-separated key/value-pairs. "
            "Alternatively, the `--ignore-separator` can be set to something else to "
            "overwrite the ellipsis. The only supported keys are: `dependency-name`, "
            "`versions`, and `update-types`. Can be supplied multiple times per "
            "`dependency-name`."
        ),
        "ignore-separator": (
            "Value to use instead of ellipsis (`...`) as a separator in `--ignore` "
            "key/value-pairs."
        ),
    },
    iterable=["ignore"],
)
def update_deps(  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
    context,
    root_repo_path=".",
    fail_fast=False,
    pre_commit=False,
    ignore=None,
    ignore_separator="...",
):
    """Update dependencies in specified Python package's `pyproject.toml`."""
    if TYPE_CHECKING:  # pragma: no cover
        context: "Context" = context  # type: ignore[no-redef]
        root_repo_path: str = root_repo_path  # type: ignore[no-redef]
        fail_fast: bool = fail_fast  # type: ignore[no-redef]
        pre_commit: bool = pre_commit  # type: ignore[no-redef]
        ignore_separator: str = ignore_separator  # type: ignore[no-redef]

    if not ignore:
        ignore: list[str] = []  # type: ignore[no-redef]

    try:
        ignore_rules = parse_ignore_entries(ignore, ignore_separator)
    except InputError as exc:
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Error: Could not parse ignore options.\n"
            f"Exception: {exc}"
        )
    LOGGER.debug("Parsed ignore rules: %s", ignore_rules)

    if pre_commit and root_repo_path == ".":
        # Use git to determine repo root
        result: "Result" = context.run("git rev-parse --show-toplevel", hide=True)
        root_repo_path = result.stdout.strip("\n")

    pyproject_path = Path(root_repo_path).resolve() / "pyproject.toml"
    if not pyproject_path.exists():
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Error: Could not find the Python package "
            f"repository's 'pyproject.toml' file at: {pyproject_path}"
        )

    # Parse pyproject.toml
    try:
        pyproject = tomlkit.parse(pyproject_path.read_bytes())
    except TOMLKitError as exc:
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Error: Could not parse 'pyproject.toml' file "
            f"at: {pyproject_path}\nException: {exc}"
        )

    # Retrieve the minimum required Python version
    try:
        py_version = get_min_max_py_version(
            pyproject.get("project", {}).get("requires-python", "")
        )
    except UnableToResolve as exc:
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Error: Cannot determine minimum Python version."
            f"\nException: {exc}"
        )
    LOGGER.debug("Minimum required Python version: %s", py_version)

    # Retrieve the Python project's package name
    project_name = pyproject.get("project", {}).get("name", "")
    if not project_name:
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Error: Could not find the Python project's name"
            " in 'pyproject.toml'."
        )

    # Build the list of dependencies listed in pyproject.toml
    dependencies: list[str] = pyproject.get("project", {}).get("dependencies", [])
    for optional_deps in (
        pyproject.get("project", {}).get("optional-dependencies", {}).values()
    ):
        dependencies.extend(optional_deps)

    # Placeholder and default variables
    already_handled_packages = set()
    updated_packages = {}
    error = False

    for dependency in dependencies:
        try:
            parsed_requirement = Requirement(dependency)
        except InvalidRequirement as exc:
            msg = (
                f"Could not parse requirement {dependency!r} from pyproject.toml: "
                f"{exc}"
            )
            LOGGER.error(msg)
            if fail_fast:
                sys.exit(f"{Emoji.CROSS_MARK.value} {error_msg(msg)}")
            print(error_msg(msg), flush=True)
            error = True
            continue
        LOGGER.debug("Parsed requirement: %r", parsed_requirement)

        # Skip package if already handled
        if parsed_requirement in already_handled_packages:
            continue

        # Skip URL versioned dependencies
        # BUT do regenerate the dependency in order to have a consistent formatting
        if parsed_requirement.url:
            msg = (
                f"Dependency {parsed_requirement.name!r} is pinned to a URL and "
                "will be skipped."
            )
            LOGGER.info(msg)
            print(info_msg(msg), flush=True)

            _format_and_update_dependency(
                parsed_requirement, dependency, pyproject_path
            )
            already_handled_packages.add(parsed_requirement)
            continue

        # Skip and warn if package is not version-restricted
        # BUT do regenerate the dependency in order to have a consistent formatting
        if not parsed_requirement.specifier:
            # Only warn if package name does not match project name
            if parsed_requirement.name != project_name:
                msg = (
                    f"Dependency {parsed_requirement.name!r} is not version "
                    "restricted and will be skipped. Consider adding version "
                    "restrictions."
                )
                LOGGER.warning(msg)
                print(warning_msg(msg), flush=True)

            _format_and_update_dependency(
                parsed_requirement, dependency, pyproject_path
            )
            already_handled_packages.add(parsed_requirement)
            continue

        # Examine markers for a custom set of Python version specifiers
        marker_py_version = ""
        if parsed_requirement.marker:
            environment_keys = default_environment().keys()
            empty_environment = {key: "" for key in environment_keys}
            python_version_centric_environment = empty_environment
            python_version_centric_environment.update({"python_version": py_version})

            if not parsed_requirement.marker.evaluate(
                environment=python_version_centric_environment
            ):
                # Current (minimum) Python version does NOT satisfy the marker
                marker_py_version = find_minimum_py_version(
                    parsed_requirement.marker, py_version
                )

            marker_py_version = get_min_max_py_version(parsed_requirement.marker)
            LOGGER.debug("Min/max Python version from marker: %s", marker_py_version)

        # Check version from PyPI's online package index
        out: "Result" = context.run(
            "pip index versions "
            f"--python-version {marker_py_version or py_version} "
            f"{parsed_requirement.name}",
            hide=True,
        )
        package_latest_version_line = out.stdout.split(sep="\n", maxsplit=1)[0]
        match = re.match(
            r"(?P<package>[a-zA-Z0-9-_]+) \((?P<version>[0-9]+(?:\.[0-9]+){0,2})\)",
            package_latest_version_line,
        )
        if match is None:
            msg = (
                "Could not parse package and version from 'pip index versions' output "
                f"for line:\n  {package_latest_version_line}"
            )
            LOGGER.error(msg)
            if fail_fast:
                sys.exit(f"{Emoji.CROSS_MARK.value} {error_msg(msg)}")
            print(error_msg(msg), flush=True)
            already_handled_packages.add(parsed_requirement)
            error = True
            continue

        pip_index_package_name: str = match.group("package")
        latest_version: str = match.group("version")

        # Sanity check
        # Ensure that the package name parsed from pyproject.toml matches the name
        # returned from 'pip index versions'
        if parsed_requirement.name != pip_index_package_name:
            msg = (
                "Package name parsed from pyproject.toml "
                f"({parsed_requirement.name!r}) does not match the name returned from "
                f"'pip index versions': {pip_index_package_name!r}"
            )
            LOGGER.error(msg)
            if fail_fast:
                sys.exit(f"{Emoji.CROSS_MARK.value} {error_msg(msg)}")
            print(error_msg(msg), flush=True)
            already_handled_packages.add(parsed_requirement)
            error = True
            continue

        # Check whether pyproject.toml already uses the latest version
        # This is expected if the latest version equals a specifier with any of the
        # operators: ==, >=, or ~=.
        split_latest_version = latest_version.split(".")
        _continue = False
        for specifier in parsed_requirement.specifier:
            if specifier.operator in ["==", ">=", "~="]:
                split_specifier_version = specifier.version.split(".")
                equal_length_latest_version = split_latest_version[
                    : len(split_specifier_version)
                ]
                if equal_length_latest_version == split_specifier_version:
                    LOGGER.debug(
                        "Package %r is already up-to-date. Specifiers: %s. "
                        "Latest version: %s",
                        parsed_requirement.name,
                        parsed_requirement.specifier,
                        latest_version,
                    )
                    already_handled_packages.add(parsed_requirement)
                    _continue = True
        if _continue:
            continue

        # Create ignore rules based on specifier set
        requirement_ignore_rules = create_ignore_rules(parsed_requirement.specifier)
        if requirement_ignore_rules["versions"]:
            if parsed_requirement.name in ignore_rules:
                # Only "versions" key exists in requirement_ignore_rules
                if "versions" in ignore_rules[parsed_requirement.name]:
                    ignore_rules[parsed_requirement.name]["versions"].extend(
                        requirement_ignore_rules["versions"]
                    )
                else:
                    ignore_rules[parsed_requirement.name].update(
                        requirement_ignore_rules
                    )
            else:
                ignore_rules[parsed_requirement.name] = requirement_ignore_rules
            LOGGER.debug(
                "Created ignore rules (from specifier set): %s",
                requirement_ignore_rules,
            )

        # Apply ignore rules
        if parsed_requirement.name in ignore_rules or "*" in ignore_rules:
            versions: "IgnoreVersions" = []
            update_types: "IgnoreUpdateTypes" = {}

            if "*" in ignore_rules:
                versions, update_types = parse_ignore_rules(ignore_rules["*"])

            if parsed_requirement.name in ignore_rules:
                parsed_rules = parse_ignore_rules(ignore_rules[parsed_requirement.name])

                versions.extend(parsed_rules[0])
                update_types.update(parsed_rules[1])

            LOGGER.debug(
                "Ignore rules:\nversions: %s\nupdate_types: %s", versions, update_types
            )

            # Get "current" version from specifier set, i.e., the lowest allowed version
            # If a minimum version is not explicitly specified, use '0.0.0'
            for specifier in parsed_requirement.specifier:
                if specifier.operator in ["==", ">=", "~="]:
                    current_version = specifier.version.split(".")
                    break
            else:
                current_version = "0.0.0".split(".")

            if ignore_version(
                current=current_version,
                latest=split_latest_version,
                version_rules=versions,
                semver_rules=update_types,
            ):
                already_handled_packages.add(parsed_requirement)
                continue

        # Update specifier set to include the latest version.
        try:
            updated_specifier_set = update_specifier_set(
                latest_version=latest_version,
                current_specifier_set=parsed_requirement.specifier,
            )
        except UnableToResolve as exc:
            msg = (
                "Could not determine how to update to the latest version using the "
                f"version range specifier set: {parsed_requirement.specifier}. "
                f"Package: {parsed_requirement.name}. Latest version: {latest_version}"
            )
            LOGGER.error("%s. Exception: %s", msg, exc)
            if fail_fast:
                sys.exit(f"{Emoji.CROSS_MARK.value} {error_msg(msg)}")
            print(error_msg(msg), flush=True)
            already_handled_packages.add(parsed_requirement)
            error = True
            continue

        if not error:
            # Regenerate the full requirement string with the updated specifiers
            # Note: If any white space is present after the name (possibly incl.
            # extras) is reduced to a single space.
            match = re.search(rf"{parsed_requirement.name}(?:\[.*\])?\s+", dependency)
            updated_dependency = regenerate_requirement(
                parsed_requirement,
                specifier=updated_specifier_set,
                post_name_space=bool(match),
            )
            LOGGER.debug("Updated dependency: %r", updated_dependency)

            # Update pyproject.toml
            update_file(
                pyproject_path,
                (re.escape(dependency), updated_dependency.replace('"', "'")),
            )
            already_handled_packages.add(parsed_requirement)
            updated_packages[parsed_requirement.name] = ",".join(
                str(_)
                for _ in sorted(
                    updated_specifier_set,
                    key=lambda spec: spec.operator,
                    reverse=True,
                )
            ) + (f" ; {parsed_requirement.marker}" if parsed_requirement.marker else "")

    if error:
        sys.exit(
            f"{Emoji.CROSS_MARK.value} Errors occurred! See printed statements above."
        )

    if updated_packages:
        print(
            f"{Emoji.PARTY_POPPER.value} Successfully updated the following "
            "dependencies:\n"
            + "\n".join(
                f"  {package} ({version})"
                for package, version in updated_packages.items()
            )
            + "\n"
        )
    else:
        print(f"{Emoji.CHECK_MARK.value} No dependency updates available.")
