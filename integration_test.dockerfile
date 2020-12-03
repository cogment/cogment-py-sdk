ARG COGMENT_ORCHESTRATOR_IMAGE=cogment/orchestrator:latest
FROM $COGMENT_ORCHESTRATOR_IMAGE as orchestrator
FROM ubuntu:20.04

RUN apt-get update && apt-get install -y curl build-essential python3 python3-distutils python3-pip

# Retrieve the orchestrator!
COPY --from=orchestrator /usr/local/bin/orchestrator /usr/local/bin/
ENV COGMENT_ORCHESTRATOR /usr/local/bin/orchestrator

## Poetry setup
ENV POETRY_VERSION=1.1.3 \
  # make poetry install to this location
  POETRY_HOME="/opt/poetry" \
  # make poetry not use virtual envs
  POETRY_VIRTUALENVS_CREATE=false \
  # do not ask any interactive question
  POETRY_NO_INTERACTION=1

# prepend poetry to path
ENV PATH="$POETRY_HOME/bin:$PATH"
# Download and install poetry
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3 -

WORKDIR /cogment-py-sdk
COPY pyproject.toml poetry.lock ./
# Install dependencies
RUN poetry install --no-root
COPY . ./
# Install the cogment-py-sdk package
RUN poetry install
# Run the test with the local orchestrator
ENTRYPOINT ["poetry", "run", "task", "test", "--launch-orchestrator"]
