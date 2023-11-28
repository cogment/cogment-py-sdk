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

import asyncio
from enum import Enum
import grpc
import grpc.aio  # type: ignore

import cogment.api.common_pb2 as common_api
import cogment.api.orchestrator_pb2 as orchestrator_api
from cogment.errors import CogmentError
from cogment.session import ActorInfo
from cogment.utils import logger
from cogment.grpc_metadata import GrpcMetadata


class TrialState(Enum):
    """Enum class for the different states of a trial."""

    UNKNOWN = common_api.TrialState.UNKNOWN  # type: ignore[attr-defined]
    INITIALIZING = common_api.TrialState.INITIALIZING  # type: ignore[attr-defined]
    PENDING = common_api.TrialState.PENDING  # type: ignore[attr-defined]
    RUNNING = common_api.TrialState.RUNNING  # type: ignore[attr-defined]
    TERMINATING = common_api.TrialState.TERMINATING  # type: ignore[attr-defined]
    ENDED = common_api.TrialState.ENDED  # type: ignore[attr-defined]


class TrialInfo:
    """Class representing the details of a trial."""

    def __init__(self, trial_id, api_state, raw_info):
        if raw_info is None:
            self.trial_id = trial_id
            self.state = TrialState(api_state)
            self.properties = None
            self.env_name = None
            self.tick_id = None
            self.duration = None
        else:
            self.trial_id = raw_info.trial_id
            self.state = TrialState(raw_info.state)
            self.properties = raw_info.properties
            self.env_name = raw_info.env_name
            self.tick_id = raw_info.tick_id
            self.duration = raw_info.trial_duration

    def __str__(self):
        result = f"TrialInfo: trial_id = {self.trial_id}, properties = {self.properties}, env_name = {self.env_name}"
        result += f", state = {self.state}, tick_id = {self.tick_id}, duration = {self.duration}"
        return result


class Controller:
    """Class representing a Cogment controller associated with an Orchestrator."""

    def __init__(self, stub, user_id, metadata: GrpcMetadata = GrpcMetadata()):
        self._lifecycle_stub = stub
        self._user_id = user_id
        self._metadata = metadata.copy()

    def __str__(self):
        result = f"Controller: user id = {self._user_id}"
        return result

    def __await__(self):
        """
        Make controller instances awaitable
        This, frankly dirty hack, allows using `await context.get_controller(endpoint)` with any kind of endpoint
        """

        async def _self():
            return self

        return asyncio.create_task(_self()).__await__()

    def has_specs(self):
        return True  # This class does not rely on the spec

    async def get_actors(self, trial_id):
        req = orchestrator_api.TrialInfoRequest()
        req.get_actor_list = True
        metadata = self._metadata.copy()
        metadata.add("trial-id", trial_id)
        rep = await self._lifecycle_stub.GetTrialInfo(
            request=req,
            metadata=metadata.to_grpc_metadata(),
        )
        if len(rep.trial) == 0:
            raise CogmentError(f"Unknown trial [{trial_id}]")
        elif len(rep.trial) > 1:
            raise CogmentError(f"Unexpected response from orchestrator [{rep}] for [{trial_id}]")

        result = [ActorInfo(actor.name, actor.actor_class) for actor in rep.trial[0].actors_in_trial]
        return result

    async def start_trial(self, trial_config=None, trial_id_requested=None, trial_params=None):
        req = orchestrator_api.TrialStartRequest()
        req.user_id = self._user_id

        if trial_config is not None:
            if trial_params is not None:
                raise CogmentError(f"Cannot provide both a start config and start parameters")
            if type(trial_config) is not bytes:
                req.config.content = trial_config.SerializeToString()
            else:
                req.config.content = trial_config
        elif trial_params is not None:
            req.params.CopyFrom(trial_params._raw_params)
            if trial_params._raw_params.HasField("trial_config"):
                logger.warning(f"Trial config from trial parameters will be ignored")

        if trial_id_requested is not None:
            req.trial_id_requested = trial_id_requested

        logger.debug(f"Requesting start of a trial with [{req}] ...")
        rep = await self._lifecycle_stub.StartTrial(req, metadata=self._metadata.to_grpc_metadata())

        if rep.trial_id:
            logger.debug(f"Trial [{rep.trial_id}] started")
        else:
            logger.warning(f"Requested trial id [{trial_id_requested}] could not be used")

        return rep.trial_id

    async def terminate_trial(self, trial_ids, hard=False):
        req = orchestrator_api.TerminateTrialRequest()
        req.hard_termination = hard

        metadata = self._metadata.copy()
        if type(trial_ids) == str:
            logger.deprecated("Using Controller.terminate_trial() with a string trial ID is deprecated.  Use a list.")
            metadata.add("trial-id", trial_ids)
        else:
            for id in trial_ids:
                metadata.add("trial-id", id)

        logger.debug(f"Requesting end of trial [{trial_ids}] (hard termination: [{hard}])")
        await self._lifecycle_stub.TerminateTrial(request=req, metadata=metadata.to_grpc_metadata())

    async def get_remote_versions(self):
        req = common_api.VersionRequest()
        info = await self._lifecycle_stub.Version(request=req, metadata=self._metadata.to_grpc_metadata())
        result = {}
        for ver in info.versions:
            result[ver.name] = ver.version
        return result

    async def get_trial_info(self, trial_ids):
        req = orchestrator_api.TrialInfoRequest()
        metadata = self._metadata.copy()
        if trial_ids is None:
            logger.deprecated("Using Controller.get_trial_info() with a null trial ID is deprecated.  Use a list.")
        elif type(trial_ids) == str:
            logger.deprecated("Using Controller.get_trial_info() with a string trial ID is deprecated.  Use a list.")
            metadata.add("trial-id", trial_ids)
        else:
            for id in trial_ids:
                metadata.add("trial-id", id)
        reply = await self._lifecycle_stub.GetTrialInfo(request=req, metadata=metadata.to_grpc_metadata())

        result = []
        for info in reply.trial:
            info_ex = TrialInfo(None, None, info)
            result.append(info_ex)

        return result

    async def watch_trials(self, trial_state_filters=[], full_info: bool = False):
        request = orchestrator_api.TrialListRequest(full_info=full_info)
        for filter in trial_state_filters:
            if type(filter) != TrialState:
                raise CogmentError(f"Unknown filter type [{type(filter)}]: must of type 'cogment.TrialState'")
            request.filter.append(filter.value)

        reply_itor = self._lifecycle_stub.WatchTrials(request=request)
        if not reply_itor:
            raise CogmentError(f"'watch_trials' failed to connect")

        try:
            async for reply in reply_itor:
                if reply.HasField("info"):
                    info_ex = TrialInfo(None, None, reply.info)
                else:
                    info_ex = TrialInfo(reply.trial_id, reply.state, None)

                keep_looping = yield info_ex
                if keep_looping is not None and not bool(keep_looping):
                    break

        except grpc.aio.AioRpcError as exc:
            logger.debug(f"gRPC failed status details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logger.error(f"Watch_trials Orchestrator communication lost: [{exc.details()}]")
            else:
                logger.exception("watch_trials -- Unexpected aio failure")
                raise

        except GeneratorExit:
            raise

        except asyncio.CancelledError as exc:
            logger.debug(f"watch_trial coroutine cancelled while waiting for trial info: [{exc}]")

        except Exception:
            logger.exception("watch_trials")
            raise
