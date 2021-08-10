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

import asyncio
import grpc
import grpc.aio  # type: ignore
from enum import Enum
import logging
import traceback


class TrialState(Enum):
    UNKNOWN = common_api.TrialState.UNKNOWN
    INITIALIZING = common_api.TrialState.INITIALIZING
    PENDING = common_api.TrialState.PENDING
    RUNNING = common_api.TrialState.RUNNING
    TERMINATING = common_api.TrialState.TERMINATING
    ENDED = common_api.TrialState.ENDED


class TrialInfo:
    def __init__(self, trial_id):
        self.trial_id = trial_id
        self.state = TrialState.UNKNOWN
        self.tick_id = None
        self.duration = None

    def __str__(self):
        result = f"TrialInfo: trial_id = {self.trial_id}, state = {self.state}"
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
            raise RuntimeError(f"Unexpected response from orchestraotr [{len(rep.trial)}]")

        result = [ActorInfo(actor.name, actor.actor_class) for actor in rep.trial[0].actors_in_trial]
        return result

    async def start_trial(self, trial_config=None):
        req = orchestrator_api.TrialStartRequest()
        req.user_id = self._user_id
        if trial_config is not None:
            req.config.content = trial_config.SerializeToString()

        logging.debug(f"Requesting start of a trial with [{req}] ...")
        rep = await self._lifecycle_stub.StartTrial(req)
        logging.debug(f"Trial [{rep.trial_id}] started")

        return rep.trial_id

    async def terminate_trial(self, trial_id):
        req = orchestrator_api.TerminateTrialRequest()
        metadata = [("trial-id", trial_id)]
        logging.debug(f"Requesting end of trial [{trial_id}] ...")
        await self._lifecycle_stub.TerminateTrial(request=req, metadata=metadata)
        logging.debug(f"End of trial request accepted for {trial_id}")

    async def get_remote_versions(self):
        req = common_api.VersionRequest()
        info = await self._lifecycle_stub.Version(request=req)
        result = {}
        for ver in info.versions:
            result[ver.name] = ver.version
        return result

    async def get_trial_info(self, trial_id):
        req = orchestrator_api.TrialInfoRequest()
        if trial_id is not None:
            metadata = [("trial-id", trial_id)]
            rep = await self._lifecycle_stub.GetTrialInfo(request=req, metadata=metadata)
        else:
            rep = await self._lifecycle_stub.GetTrialInfo(request=req)

        result = []
        for reply in rep.trial:
            info_ex = TrialInfo(reply.trial_id)
            info_ex.state = TrialState(reply.state)
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
            raise Exception(f"'watch_trials' failed to connect")

        try:
            async for reply in reply_itor:
                info = TrialInfo(reply.trial_id)
                info.state = TrialState(reply.state)
                keep_looping = yield info
                if keep_looping is not None and not bool(keep_looping):
                    break

        except grpc.aio.AioRpcError as exc:
            logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logging.error(f"Orchestrator communication lost: [{exc.details()}]")
            else:
                logging.error(f"{traceback.format_exc()}")
                raise

        except GeneratorExit:
            raise

        except asyncio.CancelledError as exc:
            logging.debug(f"watch_trial coroutine cancelled while waiting for trial info: [{exc}]")

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    def __str__(self):
        result = f"Controller:"
        return result
