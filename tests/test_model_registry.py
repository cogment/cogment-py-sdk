# Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cogment

from helpers.find_free_port import find_free_port
from helpers.launch_cogment import launch_model_registry, launch_directory

import pytest
import asyncio
import logging

logger = logging.getLogger("cogment.unit-tests")


@pytest.fixture(scope="function")
def model_registry_test_setup(test_cogment_app_dir, cogment_path):
    # Launch the directory
    directory_port = find_free_port()
    terminate_directory = launch_directory(
        app_directory=test_cogment_app_dir,
        directory_port=directory_port,
        cogment_path=cogment_path,
    )
    directory_endpoint = f"grpc://localhost:{directory_port}"

    model_registry_port = find_free_port()
    # Launch the model registry
    terminate_model_registry = launch_model_registry(
        app_directory=test_cogment_app_dir,
        model_registry_port=model_registry_port,
        cogment_path=cogment_path,
        directory_endpoint=directory_endpoint,
    )
    # Execute the test
    yield {
        "directory_endpoint": cogment.Endpoint(directory_endpoint),
    }

    # Terminate cogment
    terminate_model_registry()
    terminate_directory()


@pytest.mark.use_cogment
@pytest.mark.asyncio
async def test_model_registry(
    model_registry_test_setup, unittest_case, cog_settings, data_pb2
):
    context = cogment.Context(
        cog_settings=cog_settings,
        user_id="test_model_registry",
        prometheus_registry=None,
        directory_endpoint=model_registry_test_setup["directory_endpoint"]
    )

    await asyncio.sleep(5)
    model_registry = await context.get_model_registry()

    model_id = "test"
    model_user_data = {"model_key": "model_value"}
    version_user_data = {"version_key": "version_value"}

    # Use proto message as test 'model' due to ease of serializing/deserializing
    deserialized_model = data_pb2.Observation(observed_value=1)
    serialized_model = deserialized_model.SerializeToString()

    model = cogment.Model(
        model_id=model_id,
        serialized_model=serialized_model,
        user_data=model_user_data,
        version_user_data=version_user_data,
    )

    await asyncio.sleep(1)
    await model_registry.store_initial_version(model)
    retrieved_model = await model_registry.retrieve_version(model_id)

    assert retrieved_model.serialized_model == serialized_model
    assert retrieved_model.user_data == model_user_data
    assert retrieved_model.version_user_data == version_user_data
    assert retrieved_model.stored_version_info.data_size == len(serialized_model)
    assert retrieved_model.stored_version_info.version_number == 1
    assert retrieved_model.id == model_id
    assert retrieved_model.deserialized_model is None

    model.deserialized_model = deserialized_model
    await model_registry.store_version(model)
    retrieved_model = await model_registry.retrieve_version(model_id)

    assert retrieved_model.serialized_model is None
    assert retrieved_model.stored_version_info.version_number == 2
    assert retrieved_model.deserialized_model == deserialized_model

    def deserialize_function(data):
        obs = data_pb2.Observation()
        obs.ParseFromString(data)
        return obs

    model_registry._data_cache.clear()
    model_registry._info_cache.clear()
    retrieved_model = await model_registry.retrieve_version(
        model_id=model_id,
        version_number=-1,
        deserialize_func=deserialize_function
    )

    assert retrieved_model.serialized_model == serialized_model
    assert retrieved_model.stored_version_info.version_number == 2
    assert retrieved_model.deserialized_model == deserialized_model
    assert len(model_registry._data_cache) == 1
    assert len(model_registry._info_cache) == 1
