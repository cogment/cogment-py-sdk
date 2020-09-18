import grpc
from cogment.api.agent_pb2 import AgentEndRequest, AgentStartRequest, AgentDataRequest, AgentActionReply, AgentRewardRequest, AgentOnMessageRequest, Reward, MessageCollection
import cogment.api.agent_pb2_grpc
from cogment.api.common_pb2 import TrialActor
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue


def make_req(val, final=False):
    obs = data_pb2.Observation(value=val)
    req = AgentDataRequest()
    req.observation.data.snapshot = True
    req.observation.data.content = obs.SerializeToString()
    req.observation.tick_id = 12

    req.final = final
    return req

async def main():
    async with grpc.experimental.aio.insecure_channel('localhost:9001') as channel:
        stub = cogment.api.agent_pb2_grpc.AgentEndpointStub(channel)

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[
                    TrialActor(actor_class="player", name="Joe"),
                    TrialActor(actor_class="player", name="Jack")
                ]),
            metadata=(("trial-id", "abc"), ("actor-id", "0"))
        )

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[
                    TrialActor(actor_class="player", name="Joe"),
                    TrialActor(actor_class="player", name="Jack")
                ]),
            metadata=(("trial-id", "abc"), ("actor-id", "1"))
        )

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[
                    TrialActor(actor_class="player", name="Joe")
                ]),
            metadata=(("trial-id", "def"), ("actor-id", "0"))
        )

        def0_decide_conn = stub.Decide(
            metadata=(("trial-id", "def"), ("actor-id", "0")))
        abc0_decide_conn = stub.Decide(
            metadata=(("trial-id", "abc"), ("actor-id", "0")))
        abc1_decide_conn = stub.Decide(
            metadata=(("trial-id", "abc"), ("actor-id", "1")))

        for count in range(2):  # the hard way
            print("***********************************")
            print('Loop count: ', count)
            print("***********************************")
            await abc0_decide_conn.write(make_req(count))
            tmp0 = await abc0_decide_conn.read()
            act0 = data_pb2.Action()
            act0.ParseFromString(tmp0.action.content)
            # print(f"Recieved from actor 0 - {act0}")
            # print('Feedback from actor 0',tmp0.feedbacks)
            # print('Messages from actor 0', tmp0.messages)

            await abc1_decide_conn.write(make_req(count))
            tmp1 = await abc1_decide_conn.read()
            act1 = data_pb2.Action()
            act1.ParseFromString(tmp1.action.content)
            # print(f"Recieved from actor 1 - {act1}")
            # print('Feedback from actor 1',tmp1.feedbacks)
            # print('Messages from actor 1', tmp1.messages)

            message_list0 = []
            message_list1 = []
            env_messages = []

            for message in tmp0.messages:
                if message.receiver_id == -1:
                    env_messages.append(message)
                elif message.receiver_id == 0:
                    message_list0.append(message)
                else:
                    message_list1.append(message)
            for message in tmp1.messages:
                if message.receiver_id == -1:
                    env_messages.append(message)
                elif message.receiver_id == 1:
                    message_list0.append(message)
                else:
                    message_list1.append(message)

            print("For Actor 0", message_list0)
            print("For Actor 1", message_list1)
            print("For Environment", env_messages)

            if message_list0:
                aomr0 = AgentOnMessageRequest(
                    trial_id = "abc",
                    actor_id = 0)
                aomr0.messages.extend(message_list0)

                await stub.OnMessage(aomr0,
                  metadata=(("trial-id", "abc"), ("actor-id", "0"))
                )

            if message_list1:
                aomr1 = AgentOnMessageRequest(
                    trial_id = "abc",
                    actor_id = 1)
                aomr1.messages.extend(message_list1)

                await stub.OnMessage(aomr1,
                  metadata=(("trial-id", "abc"), ("actor-id", "1"))
                )

        await abc1_decide_conn.write(make_req(2, True))
        mytest = await abc1_decide_conn.read()
        await abc0_decide_conn.write(make_req(2, True))
        mytest = await abc0_decide_conn.read()


        await abc0_decide_conn.done_writing()
        await abc1_decide_conn.done_writing()
 
        end_abc0_conn = stub.End(
            AgentEndRequest(),
            metadata=(("trial-id", "abc"),("actor-id", "0"))
        )

        end_abc1_conn = stub.End(
            AgentEndRequest(),
            metadata=(("trial-id", "abc"),("actor-id", "1"))
        )

        end_def0_conn = stub.End(
            AgentEndRequest(),
            metadata=(("trial-id", "def"),("actor-id", "0"))
        )



        await end_abc0_conn
        await end_abc1_conn
        await end_def0_conn


asyncio.run(main())
