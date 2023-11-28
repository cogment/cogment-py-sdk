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

import base64
from copy import deepcopy
from typing import Tuple, List, Sequence, Union

from typing_extensions import Self
from cogment.errors import CogmentError

GrpcMetadataValue = Union[str, bytes]


class GrpcMetadata:
    """
    Metadata sent alongside gRPC calls to Cogment endpoints

    Some specifications from https://grpc.io/docs/guides/metadata/

    """

    def __init__(self) -> None:
        self._metadata: List[Tuple[str, GrpcMetadataValue]] = []

    def copy(self) -> Self:
        """Return a deepcopy of the metadata, useful to extend w/o side effects"""
        return deepcopy(self)

    def add(self, key: str, value: GrpcMetadataValue):
        """Add arbitrary metadata key/value pair"""
        key = key.lower()

        if key.startswith("grpc-"):
            raise CogmentError("'grpc-' metadata prefix is reserved by grpc itself")

        if key.endswith("-bin"):
            if not isinstance(value, bytes):
                raise CogmentError("Key ending with '-bin' should have a bytes value")
            # Unclear what exactly should be done for binary values
            # should they be encoded in base64? the official python example says no
            # cf. https://github.com/grpc/grpc/blob/master/examples/python/metadata/metadata_client.py
            self._metadata.append((key, value))

        else:
            if isinstance(value, bytes):
                raise CogmentError("Binary metadata should have a key ending with '-bin'")

            self._metadata.append((key, value))

    def add_http_basic_auth(self, username: str, password: str) -> None:
        """Add http basic auth 'authorization' metadata item"""
        bin_auth: bytes = f"{username}:{password}".encode("utf-8")
        base64_auth: str = base64.b64encode(bin_auth).decode("utf-8")
        self._metadata.append(("authorization", f"basic {base64_auth}"))

    def to_grpc_metadata(self) -> Sequence[Tuple[str, Union[str, bytes]]]:
        """Return the metadata ready to be sent alongside a gRPC request"""
        return self._metadata
