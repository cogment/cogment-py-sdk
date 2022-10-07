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

import asyncio
import time
import math
from typing import Any, Callable, Dict

from collections import OrderedDict
import cogment.api.model_registry_pb2 as model_registry_api
from prometheus_client import Summary

from cogment.errors import CogmentError
from cogment.utils import logger


MODEL_REGISTRY_STORE_VERSION_TIME = Summary(
    "model_registry_publish_version_seconds",
    "Time spent serializing and sending the model to the registry",
    ["model_id"],
)
MODEL_REGISTRY_RETRIEVE_VERSION_TIME = Summary(
    "model_registry_retrieve_version_seconds",
    "Time spent retrieving and deserializing the agent model version from the registry",
    ["model_id", "cached"],
)

GRPC_BYTE_SIZE_LIMIT = 4 * 1024 * 1024


class _LRU(OrderedDict):
    "Limit size, evicting the least recently looked-up key when full"

    def __init__(self, maxsize=128):
        self.maxsize = maxsize
        super().__init__()

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            self.pop(0)


class ModelInfo:
    def __init__(self, model_id: str, model_user_data: Dict[str, str]):
        self.id = model_id
        self.user_data = model_user_data


class VersionInfo:
    def __init__(self, proto_version_info):
        self.version_number = proto_version_info.version_number
        self.creation_timestamp = proto_version_info.creation_timestamp
        self.archived = proto_version_info.archived
        self.data_hash = proto_version_info.data_hash
        self.data_size = proto_version_info.data_size


class Model(ModelInfo):
    def __init__(self, model_id: str, serialized_model: bytes, **kwargs):
        super().__init__(model_id, {})
        self.version_user_data: Dict[str, str] = {}
        self.deserialized_model = None
        self.serialized_model = serialized_model
        self.stored_version_info = None

        # Provide an easy way for users to set parameter attributes on construction
        for name, value in kwargs.items():
            if name[0] == "_" or name not in dir(self):
                raise CogmentError(f"Unknown attribute [{name}]")
            setattr(self, name, value)


class ModelRegistry:
    def __init__(self, stub):
        self._model_registry_stub = stub
        self._info_cache: Dict[str, ModelInfo] = _LRU()
        self._data_cache: Dict[str, bytes] = _LRU()

    async def store_initial_version(self, model: Model) -> VersionInfo:
        """
        Create a new model in the model registry and store the initial version

        Parameters:
            model (Model): The model
        Returns:
            version_info (VersionInfo):
            The information of the stored initial version
        """
        model_user_data_str = {}
        for key, value in model.user_data.items():
            model_user_data_str[key] = str(value)

        registry_model_info = model_registry_api.ModelInfo(model_id=model.id, user_data=model_user_data_str)
        cached_model_info = ModelInfo(model.id, model.user_data)

        req = model_registry_api.CreateOrUpdateModelRequest(model_info=registry_model_info)
        await self._model_registry_stub.CreateOrUpdateModel(req)

        self._info_cache[model.id] = cached_model_info

        version_info = await self.store_version(model)

        return version_info

    async def retrieve_model_info(self, model_id: str) -> ModelInfo:
        """
        Retrieve the given's model information

        Parameters:
            model_id (string): The model id
        Returns
            model_info (ModelInfo): The information of the model
        """
        if model_id not in self._info_cache:
            req = model_registry_api.RetrieveModelsRequest(model_ids=[model_id])
            try:
                rep = await self._model_registry_stub.RetrieveModels(req)
            except Exception:
                logger.error(f"Error retrieving model version with id [{model_id}]")
                return None

            registry_model_info = rep.model_infos[0]
            cached_model_info = ModelInfo(registry_model_info.model_id, registry_model_info.user_data)

            self._info_cache[model_id] = cached_model_info

        return self._info_cache[model_id]

    async def store_version(self, model: Model, archived=False) -> VersionInfo:
        """
        Store a new version of the model

        Parameters:
            model (Model): The model
            archive (bool - default is False):
            If true, the model version will be archived (i.e. stored in permanent storage)
        Returns
            version_info (VersionInfo): The information of the stored version
        """

        def generate_chunks():
            try:
                version_data = model.serialized_model
                version_info = model_registry_api.ModelVersionInfo(
                    model_id=model.id, archived=archived, data_size=len(version_data))
                for key, value in model.version_user_data.items():
                    version_info.user_data[key] = str(value)

                chunk_header = model_registry_api.CreateVersionRequestChunk.Header(version_info=version_info)
                yield model_registry_api.CreateVersionRequestChunk(header=chunk_header)

                chunksize = math.trunc(GRPC_BYTE_SIZE_LIMIT / 2)

                chunked_version_data = [
                    version_data[index:index + chunksize] for index in range(0, len(version_data), chunksize)
                ]
                for data_chunk in chunked_version_data:
                    chunk_body = model_registry_api.CreateVersionRequestChunk.Body(data_chunk=data_chunk)
                    yield model_registry_api.CreateVersionRequestChunk(body=chunk_body)

            except Exception as error:
                raise CogmentError(f"Failure while generating model version chunk [{error}]")

        if model.serialized_model is None:
            raise CogmentError("Cannot store a model without a serialized_model attribute")

        with MODEL_REGISTRY_STORE_VERSION_TIME.labels(model_id=model.id).time():
            rep = await self._model_registry_stub.CreateVersion(generate_chunks())

        if model.deserialized_model:
            self._data_cache[rep.version_info.data_hash] = model.deserialized_model

        return VersionInfo(rep.version_info)

    async def retrieve_version(
        self, model_id: str, version_number=-1, deserialize_func: Callable[[bytes], Any] = None,
    ) -> Model:
        """
        Retrieve a version of the model

        Parameters:
            model_id (string): Unique id of the model
            version_number (int - default is -1): The version number (-1 for the latest)
            deserialize_func (Callable[[bytes, Any]]): Function that returns an instance of the original model type
        Returns
            model (Model): The stored model
        """
        start_time = time.time()

        # First retrieve the model info and model version info
        async def retrieve_version_info(model_id, version_number):
            req = model_registry_api.RetrieveVersionInfosRequest(model_id=model_id, version_numbers=[version_number])
            try:
                rep = await self._model_registry_stub.RetrieveVersionInfos(req)
            except Exception:
                logger.error(
                    f"Failed to retrieve model version with id [{model_id}] and version number [{version_number}]"
                )
                return None

            version_info_pb = rep.version_infos[0]
            return version_info_pb

        [model_info, version_info] = await asyncio.gather(
            self.retrieve_model_info(model_id), retrieve_version_info(model_id, version_number)
        )

        if model_info is None or version_info is None:
            return None

        cached = version_info.data_hash in self._data_cache

        if cached:
            model = Model(
                model_id=model_id,
                serialized_model=None,
                stored_version_info=VersionInfo(version_info),
                user_data=model_info.user_data,
                version_user_data=version_info.user_data,
                deserialized_model=self._data_cache[version_info.data_hash]
            )

        else:
            req = model_registry_api.RetrieveVersionDataRequest(
                model_id=model_id, version_number=version_info.version_number)
            data = b""
            async for chunk in self._model_registry_stub.RetrieveVersionData(req):
                data += chunk.data_chunk

            model = Model(
                model_id=model_id,
                serialized_model=data,
                stored_version_info=VersionInfo(version_info),
                version_user_data=version_info.user_data,
                user_data=model_info.user_data,
            )

            if deserialize_func:
                deserialized_model = deserialize_func(data)
                model.deserialized_model = deserialized_model
                self._data_cache[version_info.data_hash] = deserialized_model

        MODEL_REGISTRY_RETRIEVE_VERSION_TIME.labels(model_id=model_id, cached=cached).observe(time.time() - start_time)

        return model
