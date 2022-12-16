# Copyright 2021 AI Redefined Inc. <dev+cogment@ai-r.com>
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

from typing import Dict, List

import cogment.api.model_registry_pb2 as model_registry_api

from cogment.errors import CogmentError
from cogment.utils import logger


GRPC_BYTE_SIZE_LIMIT = 4 * 1024 * 1024  # 4 MB


class ModelIterationInfo:
    def __init__(self, proto_version_info):
        self.model_name = proto_version_info.model_id
        self.iteration = proto_version_info.version_number
        self.timestamp = proto_version_info.creation_timestamp
        self.hash = proto_version_info.data_hash
        self.size = proto_version_info.data_size
        self.properties = dict(proto_version_info.user_data)

    def __str__(self):
        result = f"ModelIterationInfo: model_name = {self.model_name}, iteration = {self.iteration}"
        result += f", timestamp = {self.timestamp}, hash = {self.hash}, size = {self.size}"
        result += f", properties = {self.properties}"
        return result


class ModelInfo:
    def __init__(self, proto_model_info):
        self.name = None
        self.nb_iterations = None
        self.properties = dict(proto_model_info.user_data)

    def __str__(self):
        result = f"ModelInfo: nb_iterations = {self.nb_iterations}, properties = {self.properties}"
        return result


class ModelRegistry:
    def __init__(self, stub):
        self._model_registry_stub = stub

    def __str__(self):
        return "ModelRegistry"

    async def store_model(self,
            name: str, model: bytes, iteration_properties: Dict[str, str] = None) -> ModelIterationInfo:
        if model is None and iteration_properties is not None:
            raise CogmentError(f"Cannot store iteration properties with no model iteration")
        if model is not None and len(model) == 0:
            raise CogmentError("Model is empty")

        model_info = await self._get_model_info(name)
        new_model = (model_info is None)

        if new_model:
            req = model_registry_api.CreateOrUpdateModelRequest()
            req.model_info.model_id = name
            _ = await self._model_registry_stub.CreateOrUpdateModel(req)

        if model is None:
            return None

        def generate_chunks():
            try:
                version_info = model_registry_api.ModelVersionInfo()
                version_info.model_id = name
                version_info.archived = True
                version_info.data_size = len(model)
                if iteration_properties is not None:
                    version_info.user_data.update(iteration_properties)
                header = model_registry_api.CreateVersionRequestChunk.Header(version_info=version_info)
                header_chunk = model_registry_api.CreateVersionRequestChunk(header=header)
                yield header_chunk

                max_size = GRPC_BYTE_SIZE_LIMIT // 2
                for index in range(0, len(model), max_size):
                    body = model_registry_api.CreateVersionRequestChunk.Body()
                    body.data_chunk = model[index : index + max_size]
                    body_chunk = model_registry_api.CreateVersionRequestChunk(body=body)
                    yield body_chunk

            except Exception as exc:
                raise CogmentError(f"Failure to generate model data for storage [{exc}]")

        reply = await self._model_registry_stub.CreateVersion(generate_chunks())

        return ModelIterationInfo(reply.version_info)

    async def retrieve_model(self, name: str, iteration: int = -1) -> bytes:
        req = model_registry_api.RetrieveVersionDataRequest()
        req.model_id = name
        req.version_number = iteration

        model = bytes()
        try:
            async for chunk in self._model_registry_stub.RetrieveVersionData(req):
                model += chunk.data_chunk
        except Exception as exc:
            if iteration == -1:
                # Probably the model does not exist or does not have an iteration
                logger.debug(f"Failed to retrieve model [{name}]: [{exc}]")
                return None
            else:
                raise CogmentError(f"Could not retrieve model name [{name}] and/or iteration [{iteration}]: [{exc}]")

        # This should be the one to use, but the Model Registry causes error instead of returning a 0 length model!
        # We still keep this for completeness' sake.
        if len(model) == 0:
            if iteration == -1:
                # The model does not have an iteration
                return None
            else:
                raise CogmentError(f"Unknown model name [{name}] and/or iteration [{iteration}]")

        return model

    async def remove_model(self, name: str) -> None:
        req = model_registry_api.DeleteModelRequest(model_id=name)
        _ = await self._model_registry_stub.DeleteModel(req)

    async def list_models(self) -> List[str]:
        req = model_registry_api.RetrieveModelsRequest()
        # TODO: use `req.models_count` to be able to retrieve a very large number of models
        try:
            reply = await self._model_registry_stub.RetrieveModels(req)
        except Exception as exc:
            raise CogmentError(f"Failed to retrieve model list [{exc}]")

        return [model_info.model_id for model_info in reply.model_infos]

    async def _get_iteration_info(self, name, iteration):
        req = model_registry_api.RetrieveVersionInfosRequest(model_id=name, version_numbers=[iteration])
        try:
            reply = await self._model_registry_stub.RetrieveVersionInfos(req)
        except Exception as exc:
            # Model Registry gRPC API has not way to ask if a model exists.
            # So we assume any error is due to the model not existing!
            # TODO: Update gRPC API accordingly.
            logger.debug(f"Failed to retrieve last iteration info for model [{name}]: [{exc}]")
            return None

        if len(reply.version_infos) == 0:
            return None
        if len(reply.version_infos) > 1:
            logger.warning(f"Model Registry unexpectedly returned multiple iterations [{len(reply.version_infos)}]")

        return reply.version_infos[0]

    # 'iteration' = -1 to get last iteration. List of all iterations: [0, last_iteration]
    async def get_iteration_info(self, name: str, iteration: int) -> ModelIterationInfo:
        info = await self._get_iteration_info(name, iteration)
        if info is None:
            return None

        return ModelIterationInfo(info)

    async def update_model_info(self, name: str, properties: Dict[str, str]) -> None:
        req = model_registry_api.CreateOrUpdateModelRequest()
        req.model_info.model_id = name
        req.model_info.user_data.update(properties)
        try:
            _ = await self._model_registry_stub.CreateOrUpdateModel(req)
        except Exception as exc:
            raise CogmentError(f"Failed to store model [{name}] properties: [{exc}]")

    async def _get_model_info(self, name):
        req = model_registry_api.RetrieveModelsRequest(model_ids=[name])
        try:
            reply = await self._model_registry_stub.RetrieveModels(req)
        except Exception as exc:
            # Model Registry gRPC API has not way to ask if a model exists.
            # So we assume any error is due to the model not existing!
            # TODO: Update gRPC API accordingly.
            logger.debug(f"Failed to retrieve model [{name}] info: [{exc}]")
            return None

        if len(reply.model_infos) == 0:
            logger.debug(f"No model [{name}]")
            return None
        if len(reply.model_infos) > 1:
            logger.warning(f"Model Registry unexpectedly returned multiple model infos [{len(reply.model_infos)}]")

        return reply.model_infos[0]

    async def get_model_info(self, name: str) -> ModelInfo:
        model_info = await self._get_model_info(name)
        if model_info is None:
            return None
        result = ModelInfo(model_info)
        result.name = name

        iteration_info = await self._get_iteration_info(name, -1)
        if iteration_info is not None:
            result.nb_iterations = iteration_info.version_number + 1
        else:
            result.nb_iterations = 0

        return result
