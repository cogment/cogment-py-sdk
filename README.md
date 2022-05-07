# cogment-py-sdk

[![Latest final release](https://img.shields.io/pypi/v/cogment?style=flat-square)](https://pypi.org/project/cogment/) [![Apache 2 License](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](./LICENSE) [![Changelog](https://img.shields.io/badge/-Changelog%20-blueviolet?style=flat-square)](./CHANGELOG.md)

[Cogment](https://cogment.ai) is an innovative open source AI platform designed to leverage the advent of AI to benefit humankind through human-AI collaboration developed by [AI Redefined](https://ai-r.com). Cogment enables AI researchers and engineers to build, train and operate AI agents in simulated or real environments shared with humans. For the full user documentation visit <https://docs.cogment.ai>

This module, `cogment-py-sdk`, is the Python SDK for making use of Cogment when working with Python. It's full documentation can be consulted at <https://docs.cogment.ai/cogment/cogment-api-reference/python/>.

## Developers

### Local setup

Make sure you have the following installed:

- [Python](https://www.python.org) (any version >=3.7 should work),
- [Poetry](https://python-poetry.org).

Install the dependencies, including downloading and building the cogment protobuf API, by navigating to the python SDK directory and run the following

```
poetry install
```

### Define used Cogment protobuf API

The version of the used cogment protobuf API is defined in the `.cogment-api.yaml` file at the root of the repository. The following can be defined:

- `cogment_version: "latest"`, is the default, it retrieves the api from the _latest_ Cogment release (excluding pre-releases),
- `cogment_version: "vMAJOR.MINOR.PATCH[-PRERELEASE]"`, retrieves the api from any Cogment release.
- `cogment_api_path: "../RELATIVE/PATH/TO/LOCAL/COGMENT/INSTALL/include/cogment/api"`, retrieves a local version of the api found at the given path (e.g. `common.proto` should be at `${cogment_api_path}/common.proto`); if set, this overrides `cogment_version`.

### Tests

#### Integration tests

These tests launch and use Cogment, by default they'll use they'll download and use the latest released version of Cogment.

```console
poetry run task test --launch-orchestrator
```

The following environment can be defined to change this behavior, either directly in the terminal or in a `.env` file located at the root of the repository:

```bash
COGMENT_PATH="/path/to/cogment" # local path to cogment binary
COGMENT_VERSION="v2.2.0" # cogment version to download
```

### Lint

Run the linter using

```console
poetry run task lint
```

### Check conflicting dependencies with "popular" Python packages

```console
./scripts/check_dependencies_conflicts.sh
```

This script will check for conflicts required by the cogment-py-sdk and the popular Python packages in the AI/ML/Data ecosystem.

### Build the source package

Build the source package (this step will only be succesfull if `poetry install` succeeded)

```console
poetry build -f sdist
```

### Release process

People having mainteners rights of the repository can follow these steps to release a version **MAJOR.MINOR.PATCH**. The versioning scheme follows [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

1. Run `./scripts/create_release_branch.sh MAJOR.MINOR.PATCH` to create the release branch and update the version of the package,
2. On the release branch, check and update the changelog if needed,
3. Make sure `./.cogment-api.yaml` specifies fixed version to ensure rebuildability,
4. Make sure everything's fine on CI,
5. Run `./scripts/tag_release.sh MAJOR.MINOR.PATCH` to create the specific version section in the changelog, merge the release branch in `main`, create the release tag and update the `develop` branch with those.

The rest, publishing the package to PyPI and updating the mirror repositories, is handled directly by the CI.
