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

import cogment.api.directory_pb2 as directory_api

from cogment.errors import CogmentError
from cogment.utils import logger
import cogment.endpoints as ep

import copy
import urllib.parse as urlpar
from enum import Enum
from typing import Dict, List, Tuple

AUTHENTICATION_TOKEN_METADATA_NAME = "authentication-token"


class ServiceType(Enum):
    """Enum class for the different services available in directory."""

    LIFE_CYCLE = directory_api.ServiceType.TRIAL_LIFE_CYCLE_SERVICE
    CLIENT_ACTOR = directory_api.ServiceType.CLIENT_ACTOR_CONNECTION_SERVICE
    ACTOR = directory_api.ServiceType.ACTOR_SERVICE
    ENVIRONMENT = directory_api.ServiceType.ENVIRONMENT_SERVICE
    HOOK = directory_api.ServiceType.PRE_HOOK_SERVICE
    DATALOG = directory_api.ServiceType.DATALOG_SERVICE
    DATASTORE = directory_api.ServiceType.DATASTORE_SERVICE
    MODEL_REG = directory_api.ServiceType.MODEL_REGISTRY_SERVICE
    OTHER = directory_api.ServiceType.OTHER_SERVICE


# TODO: Add a cache to service?
# TODO: Make ready for end users?
class Directory:

    def __init__(self, stub, auth_token: str):
        self._stub = stub
        self._auth_token = auth_token

        if self._auth_token:
            self._metadata = [(AUTHENTICATION_TOKEN_METADATA_NAME, self._auth_token)]
        else:
            self._metadata = []

    def __str__(self):
        result = f"Directory: authentication token = {self._auth_token}"
        return result

    async def register_host(self, type: ServiceType, host: str, port: int, ssl=False,
                            properties: Dict[str, str] = None):
        request = directory_api.RegisterRequest()
        if ssl:
            request.endpoint.protocol = directory_api.ServiceEndpoint.Protocol.GRPC_SSL
        else:
            request.endpoint.protocol = directory_api.ServiceEndpoint.Protocol.GRPC
        request.endpoint.host = host
        request.endpoint.port = port
        request.details.type = type.value
        if properties is not None:
            request.details.properties.update(properties)

        def request_itor():
            yield request

        reply_itor = self._stub.Register(request_itor(), metadata=self._metadata)
        if not reply_itor:
            raise CogmentError("Failed to connect to the directory")

        async for reply in reply_itor:
            if reply == grpc.aio.EOF:
                raise CogmentError(f"No response to directory register request [{request}]")

            if reply.status != directory_api.RegisterReply.Status.OK:
                raise CogmentError(f"Failed to register to the directory [{reply.status}] [{reply.error_msg}]")

            logger.debug(f"New directory registration [{type}] [{host}] [{port}] [{ssl}] [{properties}]"
                         f" service id [{reply.service_id}]")
            return (reply.service_id, reply.secret)

        raise CogmentError(f"Empty response to directory register request [{request}]")

    async def deregister_service(self, service_id: int, secret: str):
        request = directory_api.DeregisterRequest()
        request.service_id = service_id
        request.secret = secret

        def request_itor():
            yield request

        reply_itor = self._stub.Deregister(request_itor(), metadata=self._metadata)
        if not reply_itor:
            raise CogmentError("Failed to connect to the directory")

        async for reply in reply_itor:
            if reply == grpc.aio.EOF:
                CogmentError(f"No response to deregister request")

            if reply.status != directory_api.DeregisterReply.Status.OK:
                CogmentError(f"Deregistration failed [{reply.status}] [{reply.error_msg}]")

            logger.debug(f"Deregistered from directory: service id [{service_id}]")

    async def inquire_by_id(self, service_id: int):
        request = directory_api.InquireRequest()
        request.service_id = service_id
        dir_urls = await self._inquire(request)

        return dir_urls

    async def inquire_by_type(self, type: ServiceType, properties: Dict[str, str]):
        request = directory_api.InquireRequest()
        request.details.type = type.value
        for key, val in properties.items():
            request.details.properties[key] = val
        dir_urls = await self._inquire(request)

        return dir_urls

    async def _inquire(self, request) -> List[Tuple[str, bool]]:
        result: List[Tuple[str, bool]] = []

        reply_itor = self._stub.Inquire(request, metadata=self._metadata)
        if not reply_itor:
            raise CogmentError("Failed to connect to the directory")

        async for reply in reply_itor:
            if reply == grpc.aio.EOF:
                logger.debug(f"No response to directory inquire request [{request}]")
                return result

            if reply.data.endpoint.protocol == directory_api.ServiceEndpoint.Protocol.GRPC:
                address = f"{ep.GRPC_SCHEME}://{reply.data.endpoint.host}:{reply.data.endpoint.port}"
                ssl = False
            elif reply.data.endpoint.protocol == directory_api.ServiceEndpoint.Protocol.GRPC_SSL:
                address = f"{ep.GRPC_SCHEME}://{reply.data.endpoint.host}:{reply.data.endpoint.port}"
                ssl = True
            elif reply.data.endpoint.protocol == directory_api.ServiceEndpoint.Protocol.COGMENT:
                host = reply.data.endpoint.host
                if host != ep.CLIENT_ACTOR_HOST:
                    raise CogmentError(f"Invalid cogment endpoint from directory [{host}]")
                address = ep.CLIENT_ACTOR_URL
                ssl = False
            else:
                raise CogmentError(f"Invalid reply from directory inquiry [{reply}]")

            result.append((address, ssl))

        return result

    def _new_endpoint(self, endpoint: ep.Endpoint, dir_urls):
        if len(dir_urls) == 0:
            # TODO: Decide what to do in case inquiry did not find a service in directory
            return endpoint

        url = None
        ssl_endpoint = endpoint.using_ssl()
        for dir_url, dir_ssl in dir_urls:
            if (ssl_endpoint and dir_ssl) or (not ssl_endpoint and not dir_ssl):
                url = dir_url

        if url is not None:
            new_endpoint = copy.copy(endpoint)
            new_endpoint.url = url
        else:
            if not ssl_endpoint:
                raise CogmentError(f"All services found require an SSL connection [{endpoint.url}]")
            new_endpoint = ep.Endpoint(dir_urls[0][0])

        return new_endpoint

    # The URL data takes precedence over the provided parameters
    async def get_inquired_endpoint(self, endpoint: ep.Endpoint, type: ServiceType = None,
                                    properties: Dict[str, str] = None):
        """ Inquire directory for an enpoint with optional context (type and properties)"""

        try:
            parsed_url = urlpar.urlparse(endpoint.url)
        except Exception as exc:
            raise CogmentError(f"Endpoint [{endpoint.url}]: {exc}")

        if parsed_url.scheme == ep.GRPC_SCHEME:
            logger.debug(f"No need to inquire directory, endpoint is already a grpc endpoint")
            return endpoint

        if parsed_url.scheme != ep.COGMENT_SCHEME:
            raise CogmentError(
                f"Invalid endpoint scheme (must be '{ep.GRPC_SCHEME}' or '{ep.COGMENT_SCHEME}') [{endpoint.url}]")
        if parsed_url.hostname != ep.DISCOVERY_HOST:
            raise CogmentError(f"Unknown host for cogment endpoint [{endpoint.url}]")

        path = parsed_url.path.strip("/")
        if len(path) == 0:
            if type is None:
                raise CogmentError(f"No type provided for inquiry from directory")
            dir_type = type
        else:
            if type is not None:
                logger.warning(f"Parameter 'type' [{type}] is ignored due to a path being provided [{endpoint.url}]")

            if path == ep.SERVICE_PATH:
                # properties are ignored
                if parsed_url.query:
                    try:
                        query = urlpar.parse_qsl(parsed_url.query, keep_blank_values=True, strict_parsing=True)
                    except Exception as exc:
                        raise CogmentError(f"Endpoint [{endpoint.url}]: {exc}")
                else:
                    query = []

                properties = {key: val for key, val in query}
                id = properties.get(ep.SERVICE_ID_PROPERTY_NAME)
                if not id:
                    raise CogmentError(f"A service path on a cogment endpoint must have an"
                                       f" '{ep.SERVICE_ID_PROPERTY_NAME}' query [{endpoint.url}]")

                service_id = int(id)
                dir_urls = await self.inquire_by_id(service_id)
                if len(dir_urls) == 0:
                    logger.error(f"No resource in directory with service id [{service_id}] [{endpoint.url}]")

                result = self._new_endpoint(endpoint, dir_urls)
                logger.debug(f"Inquired service endpoint result [{result.url}]")
                return result

            elif path == ep.ACTOR_PATH:
                dir_type = ServiceType.ACTOR
            elif path == ep.ENVIRONMENT_PATH:
                dir_type = ServiceType.ENVIRONMENT
            elif path == ep.DATALOG_PATH:
                dir_type = ServiceType.DATALOG
            elif path == ep.PRE_HOOK_PATH:
                dir_type = ServiceType.HOOK
            elif path == ep.LIFECYCLE_PATH:
                dir_type = ServiceType.LIFE_CYCLE
            elif path == ep.ACTOR_SERVICE_PATH:
                dir_type = ServiceType.CLIENT_ACTOR
            elif path == ep.DATASTORE_PATH:
                dir_type = ServiceType.DATASTORE
            elif path == ep.MODEL_REGISTRY_PATH:
                dir_type = ServiceType.MODEL_REG
            else:
                raise CogmentError(f"Unknown path for cogment endpoint [{endpoint.url}]")

        if parsed_url.query:
            try:
                query = urlpar.parse_qsl(parsed_url.query, keep_blank_values=True, strict_parsing=True)
            except Exception as exc:
                raise CogmentError(f"Endpoint [{endpoint.url}]: {exc}")
        else:
            query = []

        if properties is None:
            properties = {key: val for key, val in query}
        else:
            for key, val in query:
                if key in properties:
                    logger.warning(f"Key [{key}] in parameter 'properties'"
                                   f" will be overwriten with endpoint url query value [{val}]")
                properties[key] = val

        dir_urls = await self.inquire_by_type(dir_type, properties)
        if len(dir_urls) == 0:
            logger.error(f"No service in directory for [{endpoint.url}] with [{dir_type}] and [{properties}]")
        else:
            logger.debug(f"Inquired directory for [{endpoint.url}] with [{dir_type}] and [{properties}]")

        result_endpoint = self._new_endpoint(endpoint, dir_urls)
        logger.debug(f"Inquired endpoint result [{result_endpoint.url}]")

        return result_endpoint
