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

import cogment.api.common_pb2 as common_api
import cogment.api.orchestrator_pb2 as orchestrator_api
from cogment.session import ActorInfo
from cogment.errors import CogmentError

import asyncio
import grpc
import grpc.aio  # type: ignore
from enum import Enum
import logging


class TrialState(Enum):
    UNKNOWN = common_api.TrialState.UNKNOWN
    INITIALIZING = common_api.TrialState.INITIALIZING
    PENDING = common_api.TrialState.PENDING
    RUNNING = common_api.TrialState.RUNNING
    TERMINATING = common_api.TrialState.TERMINATING
    ENDED = common_api.TrialState.ENDED


class TrialInfo:
    def __init__(self, trial_id, api_state):
        self.trial_id = trial_id
        self.state = TrialState(api_state)
        self.env_name = None
        self.tick_id = None
        self.duration = None

    def __str__(self):
        result = f"TrialInfo: trial_id = {self.trial_id}, env_name = {self.env_name}, state = {self.state}"
        result += f", tick_id = {self.tick_id}, duration = {self.duration}"
        return result


class Controller:
    def __init__(self, stub, user_id):
        self._lifecycle_stub = stub
        self._user_id = user_id

    async def get_actors(self, trial_id):
        req = orchestrator_api.TrialInfoRequest()
        req.get_actor_list = True
        metadata = [("trial-id", trial_id)]
        rep = await self._lifecycle_stub.GetTrialInfo(request=req, metadata=metadata)
        if len(rep.trial) != 1:
            raise CogmentError(f"Unexpected response from orchestrator [{rep}] for [{trial_id}]")

        result = [ActorInfo(actor.name, actor.actor_class) for actor in rep.trial[0].actors_in_trial]
        return result

    async def start_trial(self, trial_config=None, trial_id_requested=None):
        req = orchestrator_api.TrialStartRequest()
        req.user_id = self._user_id
        if trial_config is not None:
            req.config.content = trial_config.SerializeToString()
        if trial_id_requested is not None:
            req.trial_id_requested = trial_id_requested

        logging.debug(f"Requesting start of a trial with [{req}] ...")
        rep = await self._lifecycle_stub.StartTrial(req)

        # For compatibility with v1, we can't return an empty string.
        if not rep.trial_id:
            raise CogmentError(f"Requested trial id [{trial_id_requested}] could not be used")

        logging.debug(f"Trial [{rep.trial_id}] started")

        return rep.trial_id

    async def terminate_trial(self, trial_ids, hard=False):
        req = orchestrator_api.TerminateTrialRequest()
        req.hard_termination = hard
        if type(trial_ids) == str:
            logging.warning("Using Controller.TerminateTrial() with a string trial ID is deprecated.  Use a list.")
            metadata = [("trial-id", trial_ids)]
        else:
            metadata = []
            for id in trial_ids:
                metadata.append(("trial-id", id))

        logging.debug(f"Requesting end of trial [{trial_ids}] (hard termination: [{hard}])")
        await self._lifecycle_stub.TerminateTrial(request=req, metadata=metadata)

    async def get_remote_versions(self):
        req = common_api.VersionRequest()
        info = await self._lifecycle_stub.Version(request=req)
        result = {}
        for ver in info.versions:
            result[ver.name] = ver.version
        return result

    async def get_trial_info(self, trial_ids):
        req = orchestrator_api.TrialInfoRequest()
        if trial_ids is None:
            logging.warning("Using Controller.GetTrialInfo() with a null trial ID is deprecated.  Use a list.")
            metadata = []
        elif type(trial_ids) == str:
            logging.warning("Using Controller.GetTrialInfo() with a string trial ID is deprecated.  Use a list.")
            metadata = [("trial-id", trial_ids)]
        else:
            metadata = []
            for id in trial_ids:
                metadata.append(("trial-id", id))
        rep = await self._lifecycle_stub.GetTrialInfo(request=req, metadata=metadata)

        result = []
        for reply in rep.trial:
            info_ex = TrialInfo(reply.trial_id, reply.state)
            info_ex.env_name = reply.env_name
            info_ex.tick_id = reply.tick_id
            info_ex.duration = reply.trial_duration

            result.append(info_ex)

        return result

    async def watch_trials(self, trial_state_filters=[]):
        request = orchestrator_api.TrialListRequest()
        for fil in trial_state_filters:
            request.filter.append(fil.value)

        reply_itor = self._lifecycle_stub.WatchTrials(request=request)
        if not reply_itor:
            raise CogmentError(f"'watch_trials' failed to connect")

        try:
            async for reply in reply_itor:
                info = TrialInfo(reply.trial_id, reply.state)
                keep_looping = yield info
                if keep_looping is not None and not bool(keep_looping):
                    break

        except grpc.aio.AioRpcError as exc:
            logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logging.error(f"Watch_trials Orchestrator communication lost: [{exc.details()}]")
            else:
                logging.exception("watch_trials -- Unexpected aio error")
                raise

        except GeneratorExit:
            raise

        except asyncio.CancelledError as exc:
            logging.debug(f"watch_trial coroutine cancelled while waiting for trial info: [{exc}]")

        except Exception:
            logging.exception("watch_trials")
            raise

    def __str__(self):
        result = f"Controller:"
        return result
