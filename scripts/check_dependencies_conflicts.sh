#!/usr/bin/env bash

TARGET_DEPENDENCIES_LIST=(
  # Tensorflow
  "tensorflow"               # latest version
  "tensorflow >=2.10, <2.11" # minor versions released in 2020 to 2022
  "tensorflow >=2.9, <2.10"
  "tensorflow >=2.8, <2.9"
  "tensorflow >=2.7, <2.8"
  "tensorflow >=2.6, <2.7"
  # "tensorflow >=2.5, <2.6"
  # "tensorflow >=2.4, <2.5"
  "tensorflow >=2.3, <2.4"
  "tensorflow >=2.2, <2.3"
  "tensorflow >=2.1, <2.2"
  # Pytorch
  "torch"               # latest version
  "torch >=1.12, <1.13" # minor versions released in 2020 to 2022
  "torch >=1.11, <1.12"
  "torch >=1.10, <1.11"
  "torch >=1.9, <1.10"
  "torch >=1.8, <1.9"
  "torch >=1.7, <1.8"
  "torch >=1.6, <1.7"
  "torch >=1.5, <1.6"
  "torch >=1.4, <1.5"
  # Jax
  "jax" # latest version
  # Pandas
  "pandas"
  "pandas >=1.4, <1.5"
  "pandas >=1.3, <1.4"
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

SYSTEM_CONFLICT_DEPENDENCIES_LIST=() # Dependencies not compatible with the env's python version (not due to cogment)
CONFLICT_DEPENDENCIES_LIST=()

# Ensures pip has latest version on all venv
pip install upgrade_ensurepip
python -m upgrade_ensurepip

printf "Dependency compatibility with %s" "$(python -V)"
for dependency in "${TARGET_DEPENDENCIES_LIST[@]}"; do
  if ! (rm -rf "${VENV_DEPENDENCY_CHECK}" && python -m venv "${VENV_DEPENDENCY_CHECK}"); then
    printf "\n%s: Unable to reinitialize the virtual environment." "${dependency}"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${VENV_DEPENDENCY_CHECK}/bin/activate"
  if ! OUT=$(pip install --dry-run --no-deps "${dependency}" --no-cache-dir 2>&1); then
    SYSTEM_CONFLICT_DEPENDENCIES_LIST+=("$dependency")
    printf "\n%s: not supported" "${dependency}"
  else
    printf "\n%s" "${dependency}"
  fi
  deactivate
done

pip cache purge
printf "\nDone with individual dependencies"
printf "\nList of dependencies to skip: %s" "${SYSTEM_CONFLICT_DEPENDENCIES_LIST[*]}"

printf "\nDependency compatibility with cogment and %s" "$(python -V)"
for dependency in "${TARGET_DEPENDENCIES_LIST[@]}"; do
  if ! [[ " ${SYSTEM_CONFLICT_DEPENDENCIES_LIST[*]} " =~ ${dependency} ]]; then
    if ! (rm -rf "${VENV_DEPENDENCY_CHECK}" && python -m venv "${VENV_DEPENDENCY_CHECK}"); then
      printf "\n%s: Unable to reinitialize the virtual environment." "${dependency}"
      exit 1
    fi
    # shellcheck source=/dev/null
    source "${VENV_DEPENDENCY_CHECK}/bin/activate"
    if ! OUT=$(pip install -e ".[generate]" "${dependency}" --no-cache-dir 2>&1 && pip check); then
      CONFLICT_DEPENDENCIES_LIST+=("## ${dependency} ${OUT}")
      printf "\n%s: **conflict**" "${dependency}"
    else
      printf "\n%s" "${dependency}"
    fi
    deactivate
  fi
done

printf "\n"
printf "List of dependencies with cogment issues: %s" "${CONFLICT_DEPENDENCIES_LIST[*]}"
