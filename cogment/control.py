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

import cogment.api.orchestrator_pb2 as orchestrator_api
from cogment.session import ActorInfo

import grpc
import grpc.experimental.aio
from types import SimpleNamespace
from enum import Enum
import logging
import traceback


class TrialState(Enum):
    UNKNOWN = orchestrator_api.TrialState.UNKNOWN
    INITIALIZING = orchestrator_api.TrialState.INITIALIZING
    PENDING = orchestrator_api.TrialState.PENDING
    RUNNING = orchestrator_api.TrialState.RUNNING
    TERMINATING = orchestrator_api.TrialState.TERMINATING
    ENDED = orchestrator_api.TrialState.ENDED


class TrialInfo:
    def __init__(self, trial_id):
        self.trial_id = trial_id
        self.state = TrialState.UNKNOWN

    def __str__(self):
        result = f"TrialInfo: trial_id = {self.trial_id}, state = {self.state}"
        return result


# Future functionality (as a non-participant):
#   - Accept/refuse actor connections
#   - Diconnect actors
#   - Request tick updates?
#   - Request any observation?
#   - Send messages?
#   - Request to receive every message?
class Controller:
    def __init__(self, stub, user_id):
        self._lifecycle_stub = stub
        self._user_id = user_id
        self._actors = {}

    def get_actors(self, trial_id):
        # Keeping actor lists leaks memory ...
        # TODO: Replace this function with an explicit request for actors of a trial_id (in the API)
        actor_list = self._actors.get(trial_id, [])
        result = [ActorInfo(actor.name, actor.actor_class) for actor in actor_list]

        return result

    async def start_trial(self, trial_config=None):
        req = orchestrator_api.TrialStartRequest()
        req.user_id = self._user_id
        if trial_config is not None:
            req.config.content = trial_config.SerializeToString()

        logging.debug(f"Requesting start of a trial with [{req}] ...")
        rep = await self._lifecycle_stub.StartTrial(req)
        logging.debug(f"Trial [{rep.trial_id}] started")
        self._actors[rep.trial_id] = rep.actors_in_trial

        return rep.trial_id

    async def terminate_trial(self, trial_id):
        req = orchestrator_api.TerminateTrialRequest()
        metadata = [("trial-id", trial_id)]
        logging.debug(f"Requesting end of trial [{trial_id}] ...")
        await self._lifecycle_stub.TerminateTrial(request=req, metadata=metadata)
        logging.debug(f"End of trial request accepted for {trial_id}")

        if trial_id in self._actors:
            del self._actors[trial_id]

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

        except grpc.experimental.aio._call.AioRpcError as exc:
            logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logging.error(f"Orchestrator communication lost: [{exc.details()}]")
            else:
                logging.error(f"{traceback.format_exc()}")
                raise

        except GeneratorExit:
            raise

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise
