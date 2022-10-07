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

import grpc
import grpc.aio  # type: ignore
from prometheus_client import start_http_server as start_prometheus_server
from prometheus_client.core import REGISTRY  # type: ignore

import cogment.api.orchestrator_pb2_grpc as orchestrator_grpc_api
import cogment.api.agent_pb2_grpc as agent_grpc_api
import cogment.api.environment_pb2_grpc as env_grpc_api
import cogment.api.hooks_pb2_grpc as hooks_grpc_api
import cogment.api.datalog_pb2_grpc as datalog_grpc_api
import cogment.api.trial_datastore_pb2_grpc as datastore_grpc_api
import cogment.api.model_registry_pb2_grpc as model_registry_api
import cogment.api.directory_pb2_grpc as directory_grpc_api

import cogment.endpoints as ep
from cogment.directory import Directory, ServiceType
from cogment.actor import ActorSession
from cogment.environment import EnvironmentSession
from cogment.prehook import PrehookSession
from cogment.datalog import DatalogSession
from cogment.datastore import Datastore
from cogment.model_registry import ModelRegistry
from cogment.control import Controller
from cogment.agent_service import AgentServicer, get_actor_impl
from cogment.client_service import ClientServicer
from cogment.env_service import EnvironmentServicer
from cogment.hooks_service import PrehookServicer
from cogment.datalog_service import DatalogServicer
from cogment.errors import CogmentError
from cogment.utils import logger
from cogment.version import __version__

import os
from typing import Callable, Awaitable, Dict, List, Any, Tuple
from types import ModuleType
import asyncio
from types import SimpleNamespace
import socket
import urllib.parse as urlpar


DEFAULT_PROMETHEUS_PORT = 8000
_ADDITIONAL_REGISTRATION_ITEMS = {"__registration_source" : "PythonSDK-Implicit", "__version" : __version__}


def _make_client_channel(grpc_endpoint: ep.Endpoint):
    parsed_url = urlpar.urlparse(grpc_endpoint.url)
    if parsed_url.scheme == ep.GRPC_SCHEME:
        url = parsed_url.netloc
    else:
        raise CogmentError(f"Invalid endpoint scheme (must be 'grpc') [{grpc_endpoint.url}]")

    if not grpc_endpoint.using_ssl():
        channel = grpc.aio.insecure_channel(url)
    else:
        if grpc_endpoint.root_certificates:
            root = bytes(grpc_endpoint.root_certificates, "utf-8")
        else:
            root = None
        if grpc_endpoint.private_key:
            key = bytes(grpc_endpoint.private_key, "utf-8")
        else:
            key = None
        if grpc_endpoint.certificate_chain:
            certs = bytes(grpc_endpoint.certificate_chain, "utf-8")
        else:
            certs = None
        creds = grpc.ssl_channel_credentials(root, key, certs)
        channel = grpc.aio.secure_channel(url, creds)

    return channel


def _make_server(served_endpoint: ep.ServedEndpoint):
    server = grpc.aio.server()

    address = f"[::]:{served_endpoint.port}"
    if not served_endpoint.using_ssl():
        server.add_insecure_port(address)
    else:
        if served_endpoint.root_certificates:
            require_client_auth = True
            root = bytes(served_endpoint.root_certificates, "utf-8")
        else:
            require_client_auth = False
            root = None
        certs = []
        for (key, chain) in served_endpoint.private_key_certificate_chain_pairs:
            certs.append((bytes(key, "utf-8"), bytes(chain, "utf-8")))
        if not certs:
            certs = None

        creds = grpc.ssl_server_credentials(certs, root, require_client_auth)
        server.add_secure_port(address, creds)

    return server


class Context:
    """Top level class for the Cogment library from which to obtain all services."""

    def __init__(self, user_id: str, cog_settings: ModuleType, asyncio_loop=None,
                       prometheus_registry=REGISTRY, directory_endpoint: ep.Endpoint = None,
                       directory_auth_token: str = None):
        self._user_id = user_id
        self._actor_impls: Dict[str, SimpleNamespace] = {}
        self._env_impls: Dict[str, SimpleNamespace] = {}
        self._prehook_impl: SimpleNamespace = None
        self._datalog_impl: SimpleNamespace = None
        self._grpc_server = None  # type: Any
        self._prometheus_registry = prometheus_registry
        self._cog_settings = cog_settings

        if asyncio_loop is None:
            # Make sure we are running in a asyncio.Task. Even if technically this init does not need
            # to be in a Task, the whole of the SDK expects to be running in Tasks of the same event loop.
            try:
                self.asyncio_loop = asyncio.get_running_loop()
            except RuntimeError:
                raise CogmentError("The Cogment SDK requires running in a Python `asyncio` Task")
        else:
            self.asyncio_loop = asyncio_loop

        if directory_endpoint is not None:
            endpoint_to_use = directory_endpoint
        else:
            env_endpoint = os.environ.get("COGMENT_DIRECTORY_ENDPOINT")
            if env_endpoint is not None:
                endpoint_to_use = ep.Endpoint(env_endpoint)
            else:
                endpoint_to_use = None

        if directory_auth_token is not None:
            auth_token_to_use = directory_auth_token
        else:
            auth_token_to_use = os.environ.get("COGMENT_DIRECTORY_AUTHENTICATION_TOKEN")

        if endpoint_to_use:
            try:
                channel = _make_client_channel(endpoint_to_use)
            except CogmentError as exc:
                raise CogmentError(f"Directory endpoint: {exc}")

            stub = directory_grpc_api.DirectorySPStub(channel)
            self._directory = Directory(stub, auth_token_to_use)
        else:
            self._directory = None

    def __str__(self):
        result = f"Cogment Context: user id = {self._user_id}"
        return result

    def register_actor(self,
                       impl: Callable[[ActorSession], Awaitable[None]],
                       impl_name: str,
                       actor_classes: List[str] = [], properties: Dict[str, str] = {}):

        if self._grpc_server is not None:
            # We could accept "client" actor registration after the server is started, but it is not worth it
            raise CogmentError("Cannot register an actor after the server is started")
        if impl_name in self._actor_impls:
            raise CogmentError(f"The actor implementation name must be unique: [{impl_name}]")
        if ep.ACTOR_CLASS_PROPERTY_NAME in properties:
            raise CogmentError(f"Actor property [{ep.ACTOR_CLASS_PROPERTY_NAME}] is reserved for internal use")
        if ep.IMPLEMENTATION_PROPERTY_NAME in properties:
            raise CogmentError(f"Actor property [{ep.IMPLEMENTATION_PROPERTY_NAME}] is reserved for internal use")

        directory_properties = {}
        directory_properties.update(properties)
        directory_properties[ep.IMPLEMENTATION_PROPERTY_NAME] = impl_name
        directory_properties.update(_ADDITIONAL_REGISTRATION_ITEMS)

        if len(actor_classes) > 0:
            directory_actor_classes = [ac for ac in actor_classes]
        else:
            logger.deprecated(f"The use of an empty list of actor_classes is deprecated")  # type: ignore
            directory_actor_classes = []
            for ac in self._cog_settings.actor_classes:
                actor_classes.append(ac.name)
            logger.warning(f"Implementation [{impl_name}] will be registered to the directory"
                            f" for all actor classes [{actor_classes}]")

        self._actor_impls[impl_name] = SimpleNamespace(
            impl=impl, actor_classes=directory_actor_classes, properties=directory_properties)

    def register_environment(self,
                             impl: Callable[[EnvironmentSession], Awaitable[None]],
                             impl_name: str = "default", properties: Dict[str, str] = {}):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register an environment after the server is started")
        if impl_name in self._env_impls:
            raise CogmentError(f"The environment implementation name must be unique: [{impl_name}]")
        if ep.IMPLEMENTATION_PROPERTY_NAME in properties:
            raise CogmentError(f"Environment property [{ep.IMPLEMENTATION_PROPERTY_NAME}] is reserved for internal use")

        directory_properties = {}
        directory_properties.update(properties)
        directory_properties[ep.IMPLEMENTATION_PROPERTY_NAME] = impl_name
        directory_properties.update(_ADDITIONAL_REGISTRATION_ITEMS)

        self._env_impls[impl_name] = SimpleNamespace(impl=impl, properties=directory_properties)

    def register_pre_trial_hook(self,
                                impl: Callable[[PrehookSession], Awaitable[None]],
                                properties: Dict[str, str] = {}):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register a pre-trial hook after the server is started")
        if self._prehook_impl is not None:
            raise CogmentError("Only one pre-trial hook service can be registered")

        directory_properties = {}
        directory_properties.update(properties)
        directory_properties.update(_ADDITIONAL_REGISTRATION_ITEMS)
        self._prehook_impl = SimpleNamespace(impl=impl, properties=directory_properties)

    def register_datalog(self,
                         impl: Callable[[DatalogSession], Awaitable[None]],
                         properties: Dict[str, str] = {}):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register a datalog after the server is started")
        if self._datalog_impl is not None:
            raise CogmentError("Only one datalog service can be registered")

        directory_properties = {}
        directory_properties.update(properties)
        directory_properties.update(_ADDITIONAL_REGISTRATION_ITEMS)
        self._datalog_impl = SimpleNamespace(impl=impl, properties=directory_properties)

    async def _directory_deregistration(self, registered: List[Tuple[int, str]]):
        if self._directory is None:
            return

        for item in registered:
            try:
                await self._directory.deregister_service(*item)
            except Exception as exc:
                logger.debug(f"Failed to deregister service id [{item[0]}] from directory: [{exc}]")

        registered.clear()

    async def _directory_registration(self, port, ssl):
        registered: List[Tuple[int, str]] = []

        if self._directory is None:
            logger.debug(f"No directory for implicit service registration")
            return registered

        socket_addr = socket.gethostbyname(socket.gethostname())
        logger.debug(f"Registering services available here [{socket_addr}] to Directory")

        try:
            for actor in self._actor_impls.values():
                properties = actor.properties
                for actor_class in actor.actor_classes:
                    properties[ep.ACTOR_CLASS_PROPERTY_NAME] = actor_class
                    res = await self._directory.register_host(
                        ServiceType.ACTOR, socket_addr, port, ssl, properties)
                    registered.append(res)

            for env in self._env_impls.values():
                res = await self._directory.register_host(
                    ServiceType.ENVIRONMENT, socket_addr, port, ssl, env.properties)
                registered.append(res)

            if self._prehook_impl is not None:
                res = await self._directory.register_host(
                    ServiceType.HOOK, socket_addr, port, ssl, self._prehook_impl.properties)
                registered.append(res)

            if self._datalog_impl is not None:
                res = await self._directory.register_host(
                    ServiceType.DATALOG, socket_addr, port, ssl, self._datalog_impl.properties)
                registered.append(res)

        except Exception:
            await self._directory_deregistration(registered)
            raise

        return registered

    async def serve_all_registered(self, served_endpoint: ep.ServedEndpoint, prometheus_port=DEFAULT_PROMETHEUS_PORT):
        if (len(self._actor_impls) == 0 and len(self._env_impls) == 0 and
                self._prehook_impl is None and self._datalog_impl is None):
            raise CogmentError("Nothing registered to serve!")
        if self._grpc_server is not None:
            raise CogmentError("Cannot serve the same components twice")

        self._grpc_server = _make_server(served_endpoint)

        if self._actor_impls:
            servicer = AgentServicer(self._actor_impls, self._cog_settings, self._prometheus_registry)
            agent_grpc_api.add_ServiceActorSPServicer_to_server(servicer, self._grpc_server)

        if self._env_impls:
            servicer = EnvironmentServicer(self._env_impls, self._cog_settings, self._prometheus_registry)
            env_grpc_api.add_EnvironmentSPServicer_to_server(servicer, self._grpc_server)

        if self._prehook_impl is not None:
            servicer = PrehookServicer(self._prehook_impl.impl, self._cog_settings, self._prometheus_registry)
            hooks_grpc_api.add_TrialHooksSPServicer_to_server(servicer, self._grpc_server)

        if self._datalog_impl is not None:
            servicer = DatalogServicer(self._datalog_impl.impl, self._cog_settings)
            datalog_grpc_api.add_DatalogSPServicer_to_server(servicer, self._grpc_server)

        if self._prometheus_registry is not None and prometheus_port is not None:
            start_prometheus_server(prometheus_port, "", self._prometheus_registry)

        await self._grpc_server.start()
        logger.debug(f"Context gRPC server at port [{served_endpoint.port}] for user [{self._user_id}] started")

        directory_registered = await self._directory_registration(served_endpoint.port, served_endpoint.using_ssl())

        try:
            await self._grpc_server.wait_for_termination()
            logger.debug(f"Context gRPC server at port [{served_endpoint.port}] for user [{self._user_id}] exited")

        finally:
            await self._directory_deregistration(directory_registered)

    def _make_controller(self, endpoint):
        channel = _make_client_channel(endpoint)
        stub = orchestrator_grpc_api.TrialLifecycleSPStub(channel)
        return Controller(stub, self._user_id)

    async def _inquire_and_make_controller(self, endpoint):
        inquired_endpoint = await self._directory.get_inquired_endpoint(endpoint, ServiceType.LIFE_CYCLE)
        return self._make_controller(inquired_endpoint)

    # TODO: The non-async part is only kept for backward compatibility,
    #       remove it in a future (backward incompatible) release.
    def get_controller(self, endpoint=ep.Endpoint()):
        try:
            parsed_url = urlpar.urlparse(endpoint.url)
        except Exception as exc:
            raise CogmentError(f"Endpoint [{endpoint.url}]: {exc}")

        if parsed_url.scheme == ep.GRPC_SCHEME or self._directory is None:
            return self._make_controller(endpoint)  # This returns a controller instance
        else:
            return self._inquire_and_make_controller(endpoint)  # This returns an awaitable object

    def _make_datastore(self, endpoint):
        channel = _make_client_channel(endpoint)
        stub = datastore_grpc_api.TrialDatastoreSPStub(channel)
        return Datastore(stub, self._cog_settings)

    async def _inquire_and_make_datastore(self, endpoint):
        inquired_endpoint = await self._directory.get_inquired_endpoint(endpoint, ServiceType.DATASTORE)
        return self._make_datastore(inquired_endpoint)

    # TODO: The non-async part is only kept for backward compatibility,
    #       remove it in a future (backward incompatible) release.
    def get_datastore(self, endpoint=ep.Endpoint()):
        try:
            parsed_url = urlpar.urlparse(endpoint.url)
        except Exception as exc:
            raise CogmentError(f"Endpoint [{endpoint.url}]: {exc}")

        if parsed_url.scheme == ep.GRPC_SCHEME or self._directory is None:
            return self._make_datastore(endpoint)  # This returns a datastore instance
        else:
            return self._inquire_and_make_datastore(endpoint)  # This returns an awaitable object

    # Undocumented
    # We may want to make it async to standardize with the future
    # versions of 'get_controller' and 'get_datastore'
    def get_directory(self, endpoint: ep.Endpoint, authentication_token: str = None):
        channel = _make_client_channel(endpoint)
        stub = directory_grpc_api.DirectorySPStub(channel)
        return Directory(stub, authentication_token)

    async def get_model_registry(self, endpoint=ep.Endpoint()):
        if self._directory is not None:
            endpoint = await self._directory.get_inquired_endpoint(endpoint, ServiceType.MODEL_REG)

        channel = _make_client_channel(endpoint)
        stub = model_registry_api.ModelRegistrySPStub(channel)
        return ModelRegistry(stub)

    async def join_trial(self, trial_id, endpoint=ep.Endpoint(), impl_name=None, actor_name=None, actor_class=None):
        requested_class = None
        requested_name = None
        if impl_name is not None:
            # For backward compatibility
            logger.deprecated(f"`join_trial` parameter `impl_name` is deprecated")
            if actor_name is None:
                actor_impl = self._actor_impls[impl_name]
                if len(actor_impl.actor_classes) == 0:
                    raise CogmentError(f"Unable to determine possible actor to join trial: "
                                       f"impl_name [{impl_name}] does not have any registered actor class")
                requested_class = actor_impl.actor_classes[0]
            else:
                requested_name = actor_name

        elif actor_name is not None:
            requested_name = actor_name
            if actor_class is not None:
                logger.warning(f"`actor_class` will be ignored because `actor_name` is provided in `join_trial")

        elif actor_class is not None:
            requested_class = actor_class

        else:
            raise CogmentError(f"Actor name or actor class must be specified to join a trial")

        if self._directory is not None:
            inquired_endpoint = await self._directory.get_inquired_endpoint(endpoint, ServiceType.CLIENT_ACTOR)
        else:
            inquired_endpoint = endpoint

        channel = _make_client_channel(inquired_endpoint)
        stub = orchestrator_grpc_api.ClientActorSPStub(channel)
        servicer = ClientServicer(self._cog_settings, stub)

        init_data = await servicer.join_trial(trial_id, requested_name, requested_class)
        if not init_data:
            return

        if requested_name is not None and requested_name != init_data.actor_name:
            raise CogmentError(f"Internal failure: Actor name [{requested_name}] requested, received: {init_data}")
        if requested_class is not None and requested_class != init_data.actor_class:
            raise CogmentError(f"Internal failure: Actor class [{requested_class}] requested, received: {init_data}")

        if impl_name is not None and init_data.impl_name and init_data.impl_name != impl_name:
            logger.warning(f"Requested impl_name [{impl_name}] does not match trial impl_name "
                           f"[{init_data.impl_name}]: Requested impl_name will be used.")
            init_data.impl_name = impl_name

        actor_impl = get_actor_impl(trial_id, self._actor_impls, init_data)

        await servicer.run_session(actor_impl.impl, init_data)
