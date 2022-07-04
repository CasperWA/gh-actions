---
title: CD - Release
---
<!-- markdownlint-disable-next-line MD025 -->
# CD - Release (`cd_release.yml`)

There are 2 jobs in this workflow, which run in sequence.

First, an update & publish job, which updates the version in the package's root `__init__.py` file through an [Invoke](https://pyinvoke.org) task.
The newly created tag (created due to the caller workflow running `on.release.types.published`) will be updated accordingly, as will the publish branch (defaults to `main`).

Secondly, a job to update the documentation is run, however, this can be deactivated.
The job expects the documentation to be setup with the [mike](https://github.com/jimporter/mike)+[MkDocs](https://www.mkdocs.org)+[GitHub Pages](https://pages.github.com/) framework.

## Expectations

This workflow should _only_ be used for releasing a single modern Python package.

The repository contains the following:

- (**required**) A Python package root `__init__.py` file with `__version__` defined.
- (**required**) The workflow is run for a tag that starts with `v` followed by a full semantic version.
  This will automatically be the case for a GitHub release, which creates a new tag that starts with `v`.
  See [SemVer.org](https://semver.org) for more information about semantic versioning.

## Inputs

| **Name** | **Descriptions** | **Required** | **Default** | **Type** |
|:--- |:--- |:---:|:---:|:---:|
| `package_dir` | Path to the Python package directory relative to the repository directory.</br></br>Example: `'src/my_package'`. | **_Yes_** | | _string_ |
| `git_username` | A git username (used to set the 'user.name' config option). | **_Yes_** | | _string_ |
| `git_email` | A git user's email address (used to set the 'user.email' config option). | **_Yes_** | | _string_ |
| `release_branch` | The branch name to release/publish from. | No | main | _string_ |
| `install_extras` | Any extras to install from the local repository through 'pip'. Must be encapsulated in square parentheses (`[]`) and be separated by commas (`,`) without any spaces.</br></br>Example: `'[dev,release]'`. | No | _Empty string_ | _string_ |
| `python_version` | The Python version to use for the workflow. | No | 3.9 | _string_ |
| `update_docs` | Whether or not to also run the 'docs' workflow job. | No | `false` | _boolean_ |
| `doc_extras` | Any extras to install from the local repository through 'pip'. Must be encapsulated in square parentheses (`[]`) and be separated by commas (`,`) without any spaces.</br></br>Note, if this is empty, 'install_extras' will be used as a fallback.</br></br>Example: `'[docs]'`. | No | _Empty string_ | _string_ |
| `build_cmd` | The package build command, e.g., `'flit build'` or `'python -m build'` (default). | No | `python -m build` | _string_ |
| `tag_message_file` | Relative path to a release tag message file from the root of the repository.</br></br>Example: `'.github/utils/release_tag_msg.txt'`. | No | _Empty string_ | _string_ |
| `test` | Whether to use the TestPyPI repository index instead of PyPI. | No | `false` | _boolean_ |

## Secrets

| **Name** | **Descriptions** | **Required** |
|:--- |:--- |:---:|
| `PyPI_token` | A PyPI token for publishing the built package to PyPI. | **_Yes_** |
| `PAT` | A personal access token (PAT) with rights to update the `release_branch`. This will fallback on `GITHUB_TOKEN`. | No |

## Usage example

The following is an example of how a workflow may look that calls _CD - Release_.
It is meant to be complete as is.

```yaml
name: CD - Publish

on:
  release:
    types:
    - published

jobs:
  publish:
    name: Publish package and documentation
    uses: CasperWA/gh-actions/.github/workflows/cd_release.yml@main
    if: github.repository == 'CasperWA/my-python-package' && startsWith(github.ref, 'refs/tags/v')
    with:
      git_username: "Casper Welzel Andersen"
      git_email: "CasperWA@github.com"
      release_branch: stable
      install_extras: "[dev,build]"
      doc_extras: "[docs]"
      update_docs: true
      build_cmd: "flit build"
      tag_message_file: ".github/utils/release_tag_msg.txt"
    secrets:
      PyPI_token: ${{ secrets.PYPI_TOKEN }}
      PAT: ${{ secrets.PAT }}
```