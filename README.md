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

The version of the used cogment protobuf API is defined in the `.cogment-api.yml` file at the root of the repository.

### Building a Docker image

Navigate to the python SDK directory and run the following in order to create an image that can be used by a cogment project:

```
docker build -t image_name .
```
