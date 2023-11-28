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

from typing import Callable, Dict, List, Tuple, Any
import asyncio
import time
import inspect
import threading

import grpc.aio  # type: ignore

import cogment.api.model_registry_pb2 as model_registry_api

from cogment.errors import CogmentError
from cogment.utils import logger
from cogment.grpc_metadata import GrpcMetadata


GRPC_BYTE_SIZE_LIMIT = 4 * 1024 * 1024  # 4MB

# This should not be a user decision, but we don't want to change the gRPC API at this time.
# Arbitrary size hopefully small enough not to hit the gRPC size limit.
# Unfortunately it is impossible to know without requesting the data, so we play it safe.
_RETRIEVAL_COUNT = 10

# Asyncio based: Not thread safe.
# These could be made thread local, but that would introduce a different set of use-case problems.
_tracked_models = {}  # type: Dict[str, _TrackedModel]
_tracked_models_removal_task = None
_tracked_models_thread_id = None


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


class LatestModel:
    def __init__(self, tracked_model):
        self._model = tracked_model
        self._model.increment_reference()

        # We only provide the name, because the properties can change
        # over time and we don't track them with the iteration info.
        self.name = self._model.model_info.name

    def __del__(self):
        self._model.decrement_reference()

    def is_deserialized(self) -> bool:
        return self._model.deserialized_func is not None

    async def get(self) -> Tuple[Any, ModelIterationInfo]:
        await self.wait_for_available()
        return self.get_no_wait()

    def is_available(self) -> bool:
        return self._model.available.is_set()  # type: ignore

    async def wait_for_available(self) -> None:
        self._model.start_tracking()
        await self._model.available.wait()

    async def wait_for_newer(self, iteration: int) -> None:
        await self.wait_for_available()
        while iteration >= self._model.iteration_info.iteration:
            event = asyncio.Event()
            self._model.set_event_on_new_model(event)
            await event.wait()

    # Undocumented: But we leave it available for special cases or low latency step trials
    def get_no_wait(self) -> Tuple[Any, ModelIterationInfo]:
        return self._model.model, self._model.iteration_info


class _TrackedModel:
    def __init__(self, info, deserialize_func, registry):
        self.model_info = info
        self.registry = registry
        self.deserialize_func = deserialize_func

        self.available = asyncio.Event()
        self.last_ref = time.monotonic()
        self.ref_count = 0

        # The model is a bytes string if 'deserialize_func' is None
        # Otherwise it is the return value of `deserialize_func`
        self.model = None
        self.iteration_info = None

        self._tracking_task = None
        self._new_events = []

    def increment_reference(self):
        self.ref_count += 1
        self.start_tracking()

    def decrement_reference(self):
        self.ref_count -= 1
        if self.ref_count > 0:
            return
        self.last_ref = time.monotonic()
        self.ref_count = 0

    def start_tracking(self):
        if self._tracking_task is None:
            self._tracking_task = asyncio.create_task(self._track_model())
            # self._tracking_task.set_name(f"Cogment-Model [{self.model_info.name}] tracking") # Python 3.8

    def terminate(self):
        if self._tracking_task is not None:
            self._tracking_task.cancel()
            self._tracking_task = None

    def set_event_on_new_model(self, event):
        self._new_events.append(event)

    async def _track_model(self):
        name = self.model_info.name
        registry = self.registry

        # Continuously track/update model
        try:
            async for info in registry.iteration_updates(name):
                registry_model = await registry.retrieve_model(name, info.iteration)
                if registry_model is None:
                    logger.warning(
                        f"Tracked Model [{name}] iteration [{info.iteration}] unavailable:"
                        " it was probably flushed from the model registry cache"
                    )
                    continue
                if self.deserialize_func is not None:
                    self.model = self.deserialize_func(registry_model)
                else:
                    self.model = registry_model
                self.iteration_info = info

                if not self.available.is_set():
                    self.available.set()
                    logger.debug(f"First tracked model [{name}] iteration info [{info}]")

                if len(self._new_events) > 0:
                    running_new_events = self._new_events
                    self._new_events = []
                    for event in running_new_events:
                        event.set()

        except Exception:
            logger.exception(f"Failed to track model [{name}]")

        self._tracking_task = None


async def _tracked_models_removal():
    global _tracked_models_removal_task
    global _tracked_models_thread_id

    _tracked_models_thread_id = threading.get_ident()

    try:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()

            if len(_tracked_models) == 0:
                self_task = _tracked_models_removal_task
                _tracked_models_removal_task = None
                _tracked_models_thread_id = None
                logger.debug("Cancelled task for tracked models removal")
                self_task.cancel()

            for name in list(_tracked_models):
                if _tracked_models[name].ref_count == 0 and (now - _tracked_models[name].last_ref) > 300:
                    _tracked_models[name].terminate()
                    del _tracked_models[name]
                    logger.debug(f"Stopped tracking model [{name}]. [{len(_tracked_models)}] tracked models left.")

    except Exception:
        logger.exception("Tracked models removal task failure")

    _tracked_models_removal_task = None
    _tracked_models_thread_id = None


class ModelRegistry:
    def __init__(self, stub, endpoint_url, metadata: GrpcMetadata = GrpcMetadata()):
        self._model_registry_stub = stub
        self._endpoint_url = endpoint_url
        self._metadata = metadata.copy()

    def __str__(self):
        return "ModelRegistry"

    def __await__(self):
        """
         Make model registry instances awaitable
        This, frankly dirty hack, allows using `await context.get_model_registry_v2(endpoint)` with any kind of endpoint
        """

        async def _self():
            return self

        return asyncio.create_task(_self()).__await__()

    def has_specs(self):
        return True  # This class does not rely on the spec

    async def store_model(
        self, name: str, model: bytes, iteration_properties: Dict[str, str] = None
    ) -> ModelIterationInfo:
        return await self._send_model(name, model, iteration_properties, True)

    async def publish_model(
        self, name: str, model: bytes, iteration_properties: Dict[str, str] = None
    ) -> ModelIterationInfo:
        return await self._send_model(name, model, iteration_properties, False)

    async def _send_model(self, name, model, iteration_properties, store) -> ModelIterationInfo:
        if model is None and iteration_properties is not None:
            raise CogmentError(f"Cannot send iteration properties with no model iteration")
        if model is not None and len(model) == 0:
            raise CogmentError("Model is empty")

        model_info = await self._get_model_info(name)
        new_model = model_info is None

        if new_model:
            req = model_registry_api.CreateOrUpdateModelRequest()
            req.model_info.model_id = name
            _ = await self._model_registry_stub.CreateOrUpdateModel(req, metadata=self._metadata.to_grpc_metadata())

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

        reply = await self._model_registry_stub.CreateVersion(
            generate_chunks(), metadata=self._metadata.to_grpc_metadata()
        )

        return ModelIterationInfo(reply.version_info)

    async def retrieve_model(self, name: str, iteration: int = -1) -> bytes:
        req = model_registry_api.RetrieveVersionDataRequest()
        req.model_id = name
        req.version_number = iteration

        model = bytes()
        try:
            async for chunk in self._model_registry_stub.RetrieveVersionData(
                req, metadata=self._metadata.to_grpc_metadata()
            ):
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
        _ = await self._model_registry_stub.DeleteModel(req, metadata=self._metadata.to_grpc_metadata())

    async def list_models(self) -> List[ModelInfo]:
        req = model_registry_api.RetrieveModelsRequest(models_count=_RETRIEVAL_COUNT)
        models = []
        try:
            while True:
                reply = await self._model_registry_stub.RetrieveModels(req, metadata=self._metadata.to_grpc_metadata())
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
                reply = await self._model_registry_stub.RetrieveVersionInfos(
                    req, metadata=self._metadata.to_grpc_metadata()
                )
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
            reply = await self._model_registry_stub.RetrieveVersionInfos(
                req, metadata=self._metadata.to_grpc_metadata()
            )
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
            _ = await self._model_registry_stub.CreateOrUpdateModel(req, metadata=self._metadata.to_grpc_metadata())
        except Exception as exc:
            raise CogmentError(f"Failed to store model [{name}] properties: [{exc}]")

    async def _get_model_info(self, name):
        req = model_registry_api.RetrieveModelsRequest(model_ids=[name])
        try:
            reply = await self._model_registry_stub.RetrieveModels(req, metadata=self._metadata.to_grpc_metadata())
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

    async def iteration_updates(self, model_name: str):
        req = model_registry_api.VersionUpdateRequest()
        req.model_id = model_name

        reply_itor = self._model_registry_stub.VersionUpdate(req, metadata=self._metadata.to_grpc_metadata())
        if not reply_itor:
            raise CogmentError("Failed to connect to the Model Registry")

        try:
            async for update in reply_itor:
                if update == grpc.aio.EOF:
                    raise CogmentError(f"No response to Model Registry iteration update request for [{model_name}]")
                yield ModelIterationInfo(update.version_info)

        except grpc.aio.AioRpcError as exc:
            logger.debug(f"gRPC failed status details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logger.error(f"Model Registry communication lost [{exc.details()}]")
            else:
                logger.exception("Model Registry communication -- Unexpected aio failure")
                raise

    # Utility function for simple use cases. More complex cases must use 'iteration_update' explicitly.
    # This may fail if called in different threads or with different async loops.
    async def track_latest_model(
        self,
        name: str,
        deserialize_func: Callable[[bytes], Any] = None,
        initial_wait: int = 0,
    ) -> LatestModel:
        global _tracked_models_removal_task

        if name not in _tracked_models:
            _tracked_models[name] = None

            # We want to fail early if 'deserialize_func' is wrong
            if deserialize_func is not None:
                sig = inspect.signature(deserialize_func)
                if len(sig.parameters) != 1:
                    raise CogmentError(f"Deserialize function must take only one parameter [{len(sig.parameters)}]")

            # Check and wait for model to exist
            model_info = await self.get_model_info(name)
            fail_count = 0
            while model_info is None:
                fail_count += 1
                if fail_count > initial_wait:
                    del _tracked_models[name]
                    raise CogmentError(f"Model [{name}] not found in Model Registry")
                logger.debug(f"Model [{name}] not yet in Model Registry")
                await asyncio.sleep(1.0)
                model_info = await self.get_model_info(name)

            _tracked_models[name] = _TrackedModel(model_info, deserialize_func, self)

        else:  # Other task is already requesting the initial model info: wait
            while _tracked_models[name] is None:
                await asyncio.sleep(1.0)
                if name not in _tracked_models:
                    raise CogmentError(f"Model [{name}] may not be found in Model Registry")

        tracked_model = _tracked_models[name]
        if deserialize_func is not None and tracked_model.deserialize_func != deserialize_func:
            raise CogmentError(f"Deserialize function mismatch with already set function")
        if tracked_model.registry._endpoint_url != self._endpoint_url:
            raise CogmentError(
                f"Different model registry to track the same model [{name}]"
                f": [{tracked_model.registry._endpoint_url}] vs [{self._endpoint_url}]"
            )

        if _tracked_models_removal_task is None:
            _tracked_models_removal_task = asyncio.create_task(_tracked_models_removal())
            # _tracked_models_removal_task.set_name("Cogment-Stop tracking unused models") # Python 3.8
        elif _tracked_models_thread_id != threading.get_ident():
            logger.warning("Tracking global models on different threads")

        return LatestModel(tracked_model)
