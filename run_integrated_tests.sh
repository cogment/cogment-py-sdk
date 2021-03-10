set -e

echo "Linting..."
poetry run task lint

echo "Making test docker image..."
docker build -t local/cogment-py-sdk-integration-test --build-arg COGMENT_ORCHESTRATOR_IMAGE="local/orchestrator" -f integration_test.dockerfile .
#docker build -t local/cogment-py-sdk-integration-test --build-arg COGMENT_ORCHESTRATOR_IMAGE="cogment/orchestrator:latest" -f integration_test.dockerfile .
#docker build -t local/cogment-py-sdk-integration-test --build-arg COGMENT_ORCHESTRATOR_IMAGE="registry.gitlab.com/ai-r/cogment-orchestrator:latest" -f integration_test.dockerfile .

echo "Running test..."
docker run --rm  --volume $(pwd):/output local/cogment-py-sdk-integration-test
         


