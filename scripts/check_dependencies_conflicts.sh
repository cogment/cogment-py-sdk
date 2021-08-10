#!/usr/bin/env bash

TARGET_DEPENDENCIES_LIST=(
  # Tensorflow
  "tensorflow"      # latest version
  "tensorflow~=2.5" # minor versions released in 2020 and 2021
  "tensorflow~=2.4"
  "tensorflow~=2.3"
  "tensorflow~=2.2"
  "tensorflow~=2.1"
  # Pytorch
  "torch"      # latest version
  "torch~=1.9" # minor versions released in 2020 and 2021
  "torch~=1.8"
  "torch~=1.7"
  "torch~=1.6"
  "torch~=1.5"
  "torch~=1.4"
  # Jax
  "jax" # latest version
  # Pandas
  #"pandas" # latest version
  #"pandas~=1.3" # minor versions released in 2020 and 2021
  #"pandas~=1.2" # Commenting out >=1.2 versions because they require python >=3.7.1 (we are compatible with ^3.7) and poetry counts that as a conflict
  "pandas~=1.1"
  "pandas~=1.0"
  # Jupyter
  "jupyter" # latest version
  # Scikit learn
  "scikit-learn" # latest version
)

cd "$(dirname "${BASH_SOURCE[0]}")/.." || (
  printf "Could not change the working directory to the repository root.\n"
  exit 1
)

CONFLICT_DEPENDENCIES_LIST=()

for DEPENDENCY in "${TARGET_DEPENDENCIES_LIST[@]}"; do
  if ! OUT=$(poetry add --dry-run "${DEPENDENCY}"); then
    CONFLICT_DEPENDENCIES_LIST+=("## ${DEPENDENCY} ${OUT}")
    printf "x"
  else
    printf "."
  fi
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
