# Copyright 2020 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
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
import logging
import traceback
import grpc
import grpc.experimental.aio

import cogment.api.orchestrator_pb2 as orchestrator_api
import cogment.api.orchestrator_pb2_grpc as grpc_api
from cogment.trial import Trial
from cogment.control import _ServedControlSession


class ControlServicer:
    def __init__(self, cog_settings, endpoint):
        self.cog_settings = cog_settings
        if endpoint.private_key is None:
            channel = grpc.experimental.aio.insecure_channel(endpoint.url)
        else:
            if endpoint.root_certificates:
                root = bytes(endpoint.root_certificates, "utf-8")
            else:
                root = None
            if endpoint.private_key:
                key = bytes(endpoint.private_key, "utf-8")
            else:
                key = None
            if endpoint.certificate_chain:
                certs = bytes(endpoint.certificate_chain, "utf-8")
            else:
                certs = None
            creds = grpc.ssl_channel_credentials(root, key, certs)
            channel = grpc.experimental.aio.secure_channel(endpoint.url, creds)

        self.lifecycle_stub = grpc_api.TrialLifecycleStub(channel)

    async def run(self, user_id, impl, trial_config):
        req = orchestrator_api.TrialStartRequest()
        req.user_id = user_id
        if trial_config is not None:
            req.config.content = trial_config.SerializeToString()

        rep = await self.lifecycle_stub.StartTrial(req)
        trial = Trial(rep.trial_id, rep.actors_in_trial, self.cog_settings)

        try:
            await impl(_ServedControlSession(trial, self.lifecycle_stub))
            logging.debug(f"Control implementation returned")

        except asyncio.CancelledError:
            logging.debug("Control implementation coroutine cancelled")

        except Exception:
            logging.error(f"An exception occured in user control implementation:\n{traceback.format_exc()}")
            raise
