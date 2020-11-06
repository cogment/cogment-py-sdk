# cogment python SDK

## Introduction

The Cogment framework is a high-efficiency, open source framework designed to enable the training of models in environments where humans and agents interact with the environment and each other continuously. It’s capable of distributed, multi-agent, multi-model training.

This is the python API for making use of the cogment framework when working with the Python programming language.

For further Cogment information, check out the documentation at <https://docs.cogment.ai>

## Developers

### Testing and building locally

Make sure you have the following installed:
  - [Python](https://www.python.org) (any version >3.8 should work),
  - [Poetry](https://python-poetry.org).

Install the dependencies, including downloading and building the cogment protobuf API, by navigating to the python SDK directory and run the following

```
poetry install
```

Run the linter using

```
poetry run task lint
```

Build the source package (this step will only be succesfull if `poetry install` succeeded)

```
poetry build -f sdist
```

### Used Cogment protobuf API

The version of the used cogment protobuf API is defined in the `.cogment-api.yaml` file at the root of the repository. The following can be defined:

- `cogment_api_version: "latest"`, is the default, it retrieves the _latest_ build of the cogment-api `develop`,
- `cogment_api_version: "vMAJOR.MINOR.PATCH[-PRERELEASE]"`, retrieves an official release of cogment-api.
- `cogment_api_path: "../path/to/cogment-api"`, retrieves a local version of cogment-api found at the given path ; if set, this overrides `cogment_api_version`.

> ⚠️ when building a docker image, `cogment_api_path` needs to exists in the docker file system. In practice it means it should be a subdirectory of the current directory.

### Building a Docker image

Navigate to the python SDK directory and run the following in order to create an image that can be used by a cogment project:

```
docker build -t image_name .
```
