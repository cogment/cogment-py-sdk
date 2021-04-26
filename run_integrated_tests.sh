set -e

echo "Linting..."
poetry run task lint

CLI="cogment/cli:latest"
#CLI="registry.gitlab.com/ai-r/cogment-cli:latest"

ORCHESTRATOR="cogment/orchestrator:latest"
#ORCHESTRATOR="local/orchestrator:latest"
#ORCHESTRATOR="registry.gitlab.com/ai-r/cogment-orchestrator:latest"


echo "Making test docker image..."
docker build -t local/cogment-py-sdk-integration-test --build-arg COGMENT_IMAGE="$CLI" --build-arg COGMENT_ORCHESTRATOR_IMAGE="$ORCHESTRATOR" -f integration_test.dockerfile .

echo "Running test..."
docker run --rm  --volume $(pwd):/output local/cogment-py-sdk-integration-test



