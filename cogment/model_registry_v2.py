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

# This should not be a user decision, but we don't want to change the gRPC API at this time.
# Arbitrary size hopefully small enough not to hit the gRPC size limit.
# Unfortunately it is impossible to know without requesting the data, so we play it safe.
_RETRIEVAL_COUNT = 10


class ModelIterationInfo:
    def __init__(self, proto_version_info):
        self.model_name = proto_version_info.model_id
        self.iteration = proto_version_info.version_number
        self.timestamp = proto_version_info.creation_timestamp
        self.hash = proto_version_info.data_hash
        self.size = proto_version_info.data_size
        self.stored = proto_version_info.archived
        self.properties = proto_version_info.user_data  # Ideally 'dict(proto_version_info.user_data)' but slower

    def __str__(self):
        result = f"ModelIterationInfo: model_name = {self.model_name}, iteration = {self.iteration}"
        result += f", timestamp = {self.timestamp}, hash = {self.hash}, size = {self.size}"
        result += f", stored = {self.stored}, properties = {self.properties}"
        return result


class ModelInfo:
    def __init__(self, proto_model_info):
        self.name = proto_model_info.model_id
        self.properties = proto_model_info.user_data  # Ideally 'dict(proto_model_info.user_data)' but slower

    def __str__(self):
        result = f"ModelInfo: name = {self.name}, properties = {self.properties}"
        return result


class ModelRegistry:
    def __init__(self, stub):
        self._model_registry_stub = stub

    def __str__(self):
        return "ModelRegistry"

    async def store_model(self,
            name: str, model: bytes, iteration_properties: Dict[str, str] = None) -> ModelIterationInfo:
        return await self._send_model(name, model, iteration_properties, True)

    async def publish_model(self,
            name: str, model: bytes, iteration_properties: Dict[str, str] = None) -> ModelIterationInfo:
        return await self._send_model(name, model, iteration_properties, False)

    async def _send_model(self, name, model, iteration_properties, store) -> ModelIterationInfo:
        if model is None and iteration_properties is not None:
            raise CogmentError(f"Cannot send iteration properties with no model iteration")
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
                version_info.archived = store
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
                raise CogmentError(f"Failure to generate model data for sending [{exc}]")

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
            # Either the model does not exist, the iteration does not exist, or there was a real error.
            # The Model Registry should be fixed to differentiate
            logger.debug(f"Failed to retrieve iteration [{iteration}] for model [{name}]: [{exc}]")
            model = None

        if model is None:
            model_info = await self._get_model_info(name)
            if model_info is None:
                raise CogmentError(f"Unknown model [{name}]")
            else:
                return None  # Model exists, but not the iteration (probably)

        return model

    async def remove_model(self, name: str) -> None:
        req = model_registry_api.DeleteModelRequest(model_id=name)
        _ = await self._model_registry_stub.DeleteModel(req)

    async def list_models(self) -> List[ModelInfo]:
        req = model_registry_api.RetrieveModelsRequest(models_count=_RETRIEVAL_COUNT)
        models = []
        try:
            while True:
                reply = await self._model_registry_stub.RetrieveModels(req)
                for model_info in reply.model_infos:
                    models.append(ModelInfo(model_info))

                # There is a bug in model registry and we can't rely on "next_model_handle" to know the end;
                # this forces us to make one extra request if the number is a multiple of the count!
                if len(reply.model_infos) < _RETRIEVAL_COUNT:
                    break
                req.model_handle = reply.next_model_handle

        except Exception as exc:
            raise CogmentError(f"Failed to retrieve model list [{exc}]")

        return models

    async def list_iterations(self, model_name: str) -> List[ModelIterationInfo]:
        req = model_registry_api.RetrieveVersionInfosRequest(model_id=model_name, versions_count=_RETRIEVAL_COUNT)
        iterations = []
        try:
            while True:
                reply = await self._model_registry_stub.RetrieveVersionInfos(req)
                for iteration_info in reply.version_infos:
                    iterations.append(ModelIterationInfo(iteration_info))

                # There is a bug in model registry and we can't rely on "next_version_handle" to know the end;
                # this forces us to make one extra request if the number is a multiple of the count!
                if len(reply.version_infos) < _RETRIEVAL_COUNT:
                    break
                req.version_handle = reply.next_version_handle

        except Exception as exc:
            raise CogmentError(f"Failed to retrieve model [{model_name}] iteration list: [{exc}]")

        return iterations

    async def get_iteration_info(self, name: str, iteration: int) -> ModelIterationInfo:
        req = model_registry_api.RetrieveVersionInfosRequest(model_id=name, version_numbers=[iteration])
        try:
            reply = await self._model_registry_stub.RetrieveVersionInfos(req)
        except Exception as exc:
            # Either the model does not exist, the iteration does not exist, or there was a real error.
            # The Model Registry should be fixed to differentiate.
            logger.debug(f"Failed to retrieve iteration [{iteration}] info for model [{name}]: [{exc}]")
            reply = None

        if reply is None:
            model_info = await self._get_model_info(name)
            if model_info is None:
                raise CogmentError(f"Unknown model [{name}]")
            else:
                return None  # Model exists, but not the iteration (probably)

        if len(reply.version_infos) == 0:
            return None
        if len(reply.version_infos) > 1:
            logger.warning(f"Model Registry unexpectedly returned multiple iterations [{len(reply.version_infos)}]")

        return ModelIterationInfo(reply.version_infos[0])

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
            # We assume any error is due to the model not existing!
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

        return result
