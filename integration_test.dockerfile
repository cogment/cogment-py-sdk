# Some of the ENV (and ARG) defintions are also used inside the test
ARG COGMENT_ORCHESTRATOR_IMAGE=cogment/orchestrator:latest
ARG COGMENT_CLI_IMAGE=cogment/cli:latest

FROM $COGMENT_ORCHESTRATOR_IMAGE as orchestrator
FROM $COGMENT_CLI_IMAGE as cogment
FROM ubuntu:20.04
ARG PYTHON_VERSION=3.7.10

RUN apt-get update && apt-get install -y curl build-essential git protobuf-compiler bzip2 libreadline-dev libssl-dev libffi-dev

## Pyenv setup and install the desired pythong version
ENV PYENV_ROOT $HOME/.pyenv
ENV PATH $PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH
RUN git clone https://github.com/pyenv/pyenv.git $PYENV_ROOT
RUN pyenv install $PYTHON_VERSION
RUN pyenv global $PYTHON_VERSION

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

# Retrieve the cli!
COPY --from=cogment /usr/local/bin/cogment /usr/local/bin/
ENV COGMENT_CLI /usr/local/bin/cogment

# Retrieve the orchestrator!
COPY --from=orchestrator /usr/local/bin/orchestrator /usr/local/bin/orchestrator
ENV COGMENT_ORCHESTRATOR /usr/local/bin/orchestrator

WORKDIR /cogment-py-sdk
COPY pyproject.toml poetry.lock ./
# Install dependencies
RUN poetry install --no-root
COPY . ./
# Install the cogment-py-sdk package
RUN poetry install

# Run the test with the local orchestrator
ENTRYPOINT ["poetry", "run", "task", "test", "--launch-orchestrator"]

