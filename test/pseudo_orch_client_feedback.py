import grpc
from cogment.api.orchestrator_pb2 import TrialStartReply, TrialJoinReply, TrialActionReply, TrialFeedbackReply, TrialMessageReply
from cogment.api.orchestrator_pb2_grpc import TrialLifecycleServicer, ActorEndpointServicer, add_TrialLifecycleServicer_to_server, add_ActorEndpointServicer_to_server
from cogment.api.common_pb2 import TrialActor, Observation
from cogment.api.agent_pb2 import Reward
import data_pb2
import time
import grpc.experimental.aio
import asyncio
# from queue import Queue


def fill_reply(val, trial_is_over=False, reward = None):
    obs = data_pb2.Observation(value=val)
    req = TrialActionReply()
    req.observation.data.snapshot = True
    req.observation.data.content = obs.SerializeToString()
    req.observation.tick_id = 12

    req.trial_is_over = trial_is_over

    if reward:
        req.reward.CopyFrom(reward)

    return req

class TrialLifecycle(TrialLifecycleServicer):

    def StartTrial(self, request, context):

        start_reply = TrialStartReply(
            trial_id="abc",
            actors_in_trial=[
                TrialActor(actor_class="player", name="Joe"),
                TrialActor(actor_class="player", name="Jack"),
                TrialActor(actor_class="player", name="John"),
            ])

        return start_reply


class ActorEndpoint(ActorEndpointServicer):

    def __init__(self):

        self.count = 0

    async def JoinTrial(self, request, context):

        join_reply = TrialJoinReply(
            actor_class="player",
            actor_id=1,
            trial_id="abcd",
            actors_in_trial=[
                TrialActor(actor_class="player", name="Joe"),
                TrialActor(actor_class="player", name="Jack"),
                TrialActor(actor_class="player", name="John")
            ])

        return join_reply

    async def ActionStream(self, request, context):

        if self.count >= 3:
            await context.write(fill_reply(51 + self.count, True, None))
        else:

            rwd = Reward(value=3.7,
                confidence=1.0
                )


            await context.write(fill_reply(51 + self.count, False, rwd))

        rec_action = await context.read()
        action = data_pb2.Action()
        action.ParseFromString(rec_action.action.content)
        print(f"Recieved action is - {action}")

        self.count += 1

    async def GiveFeedback(self, request, context):
        if request.feedbacks:
            print("Here's the feedback:", request.feedbacks)

        return TrialFeedbackReply()

    async def SendChanMessage(self, request, context):
        if request.messages:
            print("Here's the messages:", request.messages)

        return TrialMessageReply()

async def main():

    server = grpc.experimental.aio.server()

    add_TrialLifecycleServicer_to_server(TrialLifecycle(), server)
    add_ActorEndpointServicer_to_server(ActorEndpoint(), server)

    server.add_insecure_port(f'[::]:9000')
    await server.start()
    await server.wait_for_termination()


asyncio.run(main())
