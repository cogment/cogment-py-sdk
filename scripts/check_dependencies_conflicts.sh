#!/usr/bin/env bash

TARGET_DEPENDENCIES_LIST=(
  # Tensorflow
  "tensorflow" # latest version
  #"tensorflow >=2.5, <2.6" # minor versions released in 2020 and 2021
  #"tensorflow >=2.4, <2.5"
  "tensorflow >=2.3, <2.4"
  "tensorflow >=2.2, <2.3"
  "tensorflow >=2.1, <2.3"
  # Pytorch
  "torch"              # latest version
  "torch >=1.9, <1.10" # minor versions released in 2020 and 2021
  "torch >=1.8, <1.9"
  "torch >=1.7, <1.8"
  "torch >=1.6, <1.7"
  "torch >=1.5, <1.6"
  "torch >=1.4, <1.5"
  # Jax
  "jax" # latest version
  # Pandas
  "pandas >=1.2, <1.3"
  "pandas >=1.1, <1.2"
  "pandas >=1.0, <1.1"
  # Jupyter
  "jupyter" # latest version
  # Scikit learn
  "scikit-learn" # latest version
)

cd "$(dirname "${BASH_SOURCE[0]}")/.." || (
  printf "Could not change the working directory to the repository root.\n"
  exit 1
)

VENV_DEPENDENCY_CHECK='.venv.dep_check'

CONFLICT_DEPENDENCIES_LIST=()

for DEPENDENCY in "${TARGET_DEPENDENCIES_LIST[@]}"; do
  if ! (rm -rf "${VENV_DEPENDENCY_CHECK}" && python -m venv "${VENV_DEPENDENCY_CHECK}"); then
    printf "Unable to reinitialize the virtual environment.\n"
    exit 1
  fi

  # shellcheck source=/dev/null
  source "${VENV_DEPENDENCY_CHECK}/bin/activate"
  if ! OUT=$(pip install -e ".[generate]" "${DEPENDENCY}" 2>&1 && pip check); then
    CONFLICT_DEPENDENCIES_LIST+=("## ${DEPENDENCY} ${OUT}")
    printf "x"
  else
    printf "."
  fi
  deactivate
done

printf "\n"

if [ ${#CONFLICT_DEPENDENCIES_LIST[@]} -eq 0 ]; then
  printf "No conflicts found within target %s dependencies\n" ${#TARGET_DEPENDENCIES_LIST[@]}
  exit 0
else
  for DEPENDENCY in "${CONFLICT_DEPENDENCIES_LIST[@]}"; do
    printf "***\n%s\n\n" "${DEPENDENCY}"
  done
  printf "***\n%s conflicts found within %s target dependencies\n" ${#CONFLICT_DEPENDENCIES_LIST[@]} ${#TARGET_DEPENDENCIES_LIST[@]}
  exit 1
fi
