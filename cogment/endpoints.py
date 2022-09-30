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

from cogment.utils import logger

import os
from typing import List, Tuple

# Schemes
GRPC_SCHEME = "grpc"
COGMENT_SCHEME = "cogment"

# Hosts
DISCOVERY_HOST = "discover"
CLIENT_ACTOR_HOST = "client"

# Paths
SERVICE_PATH = "service"
ACTOR_PATH = "actor"
ENVIRONMENT_PATH = "environment"
DATALOG_PATH = "datalog"
PRE_HOOK_PATH = "prehook"
LIFECYCLE_PATH = "lifecycle"
ACTOR_SERVICE_PATH = "actservice"
DATASTORE_PATH = "datastore"
MODEL_REGISTRY_PATH = "modelregistry"

# Reserved query property names
ACTOR_CLASS_PROPERTY_NAME = "__actor_class"
IMPLEMENTATION_PROPERTY_NAME = "__implementation"
SERVICE_ID_PROPERTY_NAME = "__id"
AUTHENTICATION_TOKEN_PROPERTY_NAME = "__authentication-token"

# Special URLs
BASIC_CONTEXT_DISCOVERY_URL = "cogment://discover"
CLIENT_ACTOR_URL = "cogment://client"


class Endpoint:
    """Class representing a remote Cogment endpoint where to connect."""

    def __init__(self, url: str = BASIC_CONTEXT_DISCOVERY_URL):
        self.url: str = url
        self.private_key: str = None
        self.root_certificates: str = None
        self.certificate_chain: str = None

    def __str__(self):
        result = f"Endpoint: url = {self.url}, private_key = {self.private_key}"
        result += f", root_certificates = {self.root_certificates}, certificate_chain = {self.certificate_chain}"
        return result

    def using_ssl(self):
        return (self.private_key is not None)

    def set_from_files(self, private_key_file=None, root_certificates_file=None, certificate_chain_file=None):
        try:
            if private_key_file:
                with open(private_key_file) as fl:
                    self.private_key = fl.read()
                if not self.private_key:
                    self.private_key = None

            if root_certificates_file:
                with open(root_certificates_file) as fl:
                    self.root_certificates = fl.read()
                if not self.root_certificates:
                    self.root_certificates = None

            if certificate_chain_file:
                with open(certificate_chain_file) as fl:
                    self.certificate_chain = fl.read()
                if not self.certificate_chain:
                    self.certificate_chain = None

        except Exception:
            logger.error(f"Failed loading file from CWD: {os.getcwd()}")
            raise


class ServedEndpoint:
    """Class representing a local Cogment endpoint where others can connect."""

    def __init__(self, port: int):
        if type(port) == str:
            logger.deprecated(f"'ServedEndpoint' port should be an integer, not a string")  # type: ignore
            self.port = int(port)
        else:
            self.port = port
        self.private_key_certificate_chain_pairs: List[Tuple[str, str]] = None
        self.root_certificates: str = None

    def using_ssl(self):
        return (self.private_key_certificate_chain_pairs is not None)

    # def set_from_files(private_key_certificate_chain_pairs_file=None, root_certificates_file=None):
    # TODO: This function would need to parse the PEM encoded `private_key_certificate_chain_pairs_file`
    #       to create the list of tuples required (see simpler version in `Endpoint` class above).

    def __str__(self):
        result = f"ServedEndpoint: port = {self.port}"
        result += f", private_key_certificate_chain_pairs = {self.private_key_certificate_chain_pairs}"
        result += f", root_certificates = {self.root_certificates}"
        return result
