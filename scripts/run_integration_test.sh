#!/usr/bin/env sh
# Should run in sh as the docker-in-docker CI environment doesn't have bash.

set -e

if [ -z "${COGMENT_ORCHESTRATOR_IMAGE}" ]; then
  COGMENT_ORCHESTRATOR_IMAGE="cogment/orchestrator:latest"
fi

echo "** Pulling ${COGMENT_ORCHESTRATOR_IMAGE}..."
docker pull "${COGMENT_ORCHESTRATOR_IMAGE}" || echo "   Unable to pull ${COGMENT_ORCHESTRATOR_IMAGE}, maybe it is a locally built image."

if [ -n "${CI_JOB_ID}" ]; then
  TEST_IMAGE_TAG="${CI_JOB_ID}"
else
  TEST_IMAGE_TAG="latest"
fi

echo "** Building the docker image..."
docker build \
  -t local/cogment-py-sdk-integration-test:"${TEST_IMAGE_TAG}" \
  --build-arg COGMENT_ORCHESTRATOR_IMAGE="${COGMENT_ORCHESTRATOR_IMAGE}" \
  -f integration_test.dockerfile .

echo "** Running test..."
docker run --rm --volume "$(pwd)":/output local/cogment-py-sdk-integration-test:"${TEST_IMAGE_TAG}"
