import grpc
import grpc.experimental.aio

from cogment.api.orchestrator_pb2_grpc import TrialLifecycleStub, ActorEndpointStub
from cogment.api.orchestrator_pb2 import (
    TrialStartRequest, TerminateTrialRequest, TrialJoinRequest, TrialJoinReply, TrialActionRequest,
    TrialFeedbackRequest, TrialMessageRequest)
from cogment.trial import Trial, TrialLifecycle

from cogment.delta_encoding import DecodeObservationData
from cogment.actor import _ClientActorSession
from cogment.api.common_pb2 import TrialActor

import asyncio


async def read_observations(client_session, actor_stub):
    while True:

        action_conn = actor_stub.ActionStream()

        request = await action_conn.read()

        obs = DecodeObservationData(
            client_session.actor_class,
            request.observation.data,
            client_session.latest_observation
        )

        client_session._new_observation(obs, request.trial_is_over)


async def write_actions(client_session, actor_stub, actor_id):
    while True:

        action_conn = actor_stub.ActionStream()

        act = await client_session._action_queue.get()
        action_req = TrialActionRequest()
        action_req.action.content = act.SerializeToString()
        await action_conn.write(action_req)

        feedback_req = TrialFeedbackRequest()
        feedback_req.feedbacks.extend(
            client_session.trial._gather_all_feedback())
        await actor_stub.GiveFeedback(feedback_req)

        message_req = TrialMessageRequest()
        message_req.messages.extend(
            client_session.trial._gather_all_messages(actor_id))
        await actor_stub.SendChanMessage(message_req)


class Connection:

    def __init__(self, cog_project, endpoint):
        self.cog_project = cog_project

        channel = grpc.experimental.aio.insecure_channel(endpoint)

        self.__lifecycle_stub = TrialLifecycleStub(channel)
        self.__actor_stub = ActorEndpointStub(channel)

    async def start_trial(self, trial_config, user_id):
        req = TrialStartRequest()
        req.config.content = trial_config.SerializeToString()
        req.user_id = user_id

        rep = await self.__lifecycle_stub.StartTrial(req)

        # added trial_config to following and in trial.py TrialLifecycle
        return TrialLifecycle(rep.trial_id, trial_config, rep.actors_in_trial, self)

    async def terminate(self, trial_id):
        req = TerminateTrialRequest()

        await self.__lifecycle_stub.TerminateTrial(req, metadata=(("trial-id", trial_id),))

    async def join_trial(self, trial_id=None, actor_id=-1, actor_class=None, impl=None):

        req = TrialJoinRequest(
            trial_id=trial_id,
            actor_id=actor_id,
            actor_class=actor_class)

        reply = await self.__actor_stub.JoinTrial(req)

        trial = Trial(id_=reply.trial_id,
                      cog_project=self.cog_project,
                      trial_config=None)

        trial._add_actors(reply.actors_in_trial)
        trial._add_env()

        self_info = reply.actors_in_trial[reply.actor_id]
        actor_class = self.cog_project.actor_classes[self_info.actor_class]

        client_session = _ClientActorSession(
            # should it be reply.impl_name, if yes add to .proto
            impl, actor_class, trial, self_info.name, "impl_name"
        )

        loop = asyncio.get_running_loop()

        reader_task = loop.create_task(
            read_observations(client_session, self.__actor_stub))
        writer_task = loop.create_task(
            write_actions(client_session, self.__actor_stub, reply.actor_id))

        await impl(client_session, trial)

        reader_task.cancel()
        writer_task.cancel()
