# cogment-py-sdk

[![Latest final release](https://img.shields.io/pypi/v/cogment?style=flat-square)](https://pypi.org/project/cogment/) [![Apache 2 License](https://img.shields.io/badge/license-Apache%202-green?style=flat-square)](./LICENSE) [![Changelog](https://img.shields.io/badge/-Changelog%20-blueviolet?style=flat-square)](./CHANGELOG.md)

[Cogment](https://cogment.ai) is an innovative open source AI platform designed to leverage the advent of AI to benefit humankind through human-AI collaboration developed by [AI Redefined](https://ai-r.com). Cogment enables AI researchers and engineers to build, train and operate AI agents in simulated or real environments shared with humans. For the full user documentation visit <https://docs.cogment.ai>

This module, `cogment-py-sdk`, is the Python SDK for making use of Cogment when working with Python. It's full documentation can be consulted at <https://docs.cogment.ai/cogment/cogment-api-reference/python/>.

## Developers

### Local setup

Make sure you have the following installed:

-   [Python](https://www.python.org) (any version >=3.7 should work),
-   [Poetry](https://python-poetry.org).

Install the dependencies, including downloading and building the cogment protobuf API, by navigating to the python SDK directory and run the following

```
poetry install
```

### Define used Cogment protobuf API

The version of the used cogment protobuf API is defined in the `.cogment-api.yaml` file at the root of the repository. The following can be defined:

-   `cogment_api_version: "latest"`, is the default, it retrieves the _latest_ build of the cogment-api `develop`,
-   `cogment_api_version: "vMAJOR.MINOR.PATCH[-PRERELEASE]"`, retrieves an official release of cogment-api.
-   `cogment_api_path: "../path/to/cogment-api"`, retrieves a local version of cogment-api found at the given path ; if set, this overrides `cogment_api_version`.

> ⚠️ when building a docker image, `cogment_api_path` needs to exists in the docker file system. In practice it means it should be a subdirectory of the current directory.

### Tests

To run them the first step is to configure the way to launch the orchestrator and the cli in a `.env` file.

You can copy `.env.template` for an example of what's expected.

#### Module tests

These tests only rely on the sdk, no connection to an orchestrator is done.

To execute the module tests, simply run

```
poetry run task test
```

#### Integration tests

These tests launch and use an orchestrator they are slower but more in depth.

##### Run in a docker image

This is the easiest way to run the tests.

```
./scripts/run_integration_test.sh
```

By default it will use the latest public version of `cogment/cli` and `cogment/orchestrator` released on [DockerHub](https://hub.docker.com/u/cogment). To use specific versions define `COGMENT_CLI_IMAGE` and/or `COGMENT_ORCHESTRATOR_IMAGE`.

```
COGMENT_CLI_IMAGE=<COGMENT_CLI_IMAGE_NAME_AND_TAG> COGMENT_CLI_IMAGE=<COGMENT_ORCHESTRATOR_IMAGE_NAME_AND_TAG> ./scripts/run_integration_test.sh
```

##### Run locally

```
poetry run task test --launch-orchestrator
```

You'll need to define:
- Either `COGMENT_CLI_IMAGE` (as above) or `COGMENT_CLI` as the path to a locally built Cogment cli executable.
- Either `COGMENT_ORCHESTRATOR_IMAGE` (as above) or `COGMENT_ORCHESTRATOR` as the path to a locally built Cogment orchestrator executable.

### Lint

Run the linter using

```
poetry run task lint
```

### Build the source package

Build the source package (this step will only be succesfull if `poetry install` succeeded)

```
poetry build -f sdist
```

### Release process

People having mainteners rights of the repository can follow these steps to release a version **MAJOR.MINOR.PATCH**. The versioning scheme follows [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

1. Run `./scripts/create_release_branch.sh MAJOR.MINOR.PATCH` to create the release branch and update the version of the package,
2. On the release branch, check and update the changelog if needed,
3. Update `./.cogment-api.yaml` to use the public release of the API,
4. Update `./.gitlab-ci.yml`, `integration_test`, `COGMENT_ORCHESTRATOR_IMAGE` and `COGMENT_CLI_IMAGE` to match the latest public releases of the orchestrator and cli
5. Make sure everything's fine on CI,
6. Run `./scripts/tag_release.sh MAJOR.MINOR.PATCH` to create the specific version section in the changelog, merge the release branch in `main`, create the release tag and update the `develop` branch with those.

The rest, publishing the package to PyPI and updating the mirror repositories, is handled directly by the CI.
