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


def test_arbitrary_metadata(unittest_case):
    metadata = cogment.GrpcMetadata()
    metadata.add("First", "Value")
    metadata.add("second", "second")
    metadata.add("foO-bIn", b"blop")

    unittest_case.assertCountEqual(
        metadata.to_grpc_metadata(),
        [("first", "Value"), ("second", "second"), ("foo-bin", b"blop")],
    )


def test_metadata_copy(unittest_case):
    metadata = cogment.GrpcMetadata()
    metadata.add("First", "Value")

    metadata_copy = metadata.copy()

    unittest_case.assertCountEqual(
        metadata.to_grpc_metadata(),
        metadata_copy.to_grpc_metadata(),
    )

    metadata_copy.add("bLOp", "bloupy")

    unittest_case.assertCountEqual(
        metadata.to_grpc_metadata(),
        [("first", "Value")],
    )

    unittest_case.assertCountEqual(
        metadata_copy.to_grpc_metadata(),
        [("first", "Value"), ("blop", "bloupy")],
    )


def test_bad_binary_metadata(unittest_case):
    metadata = cogment.GrpcMetadata()
    with unittest_case.assertRaises(cogment.CogmentError):
        metadata.add("test", b"blop")


def test_bad_metadata_prefix(unittest_case):
    metadata = cogment.GrpcMetadata()
    with unittest_case.assertRaises(cogment.CogmentError):
        metadata.add("GrpC-test", "blop")


def test_basic_auth(unittest_case):
    metadata = cogment.GrpcMetadata()
    metadata.add("First", "Value")
    metadata.add_http_basic_auth("user", "password")

    unittest_case.assertCountEqual(
        metadata.to_grpc_metadata(),
        [
            ("first", "Value"),
            (
                "authorization",
                "basic dXNlcjpwYXNzd29yZA==",  # `echo -n "user:password" | base64``
            ),
        ],
    )
