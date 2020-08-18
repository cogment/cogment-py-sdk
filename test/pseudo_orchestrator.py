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

import grpc
from cogment.api.agent_pb2 import AgentStartRequest, AgentDataRequest, AgentActionReply, AgentRewardRequest, Reward
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
    async with grpc.experimental.aio.insecure_channel("localhost:9001") as channel:
        stub = cogment.api.agent_pb2_grpc.AgentEndpointStub(channel)

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[
                    TrialActor(actor_class="player", name="Joe"),
                    TrialActor(actor_class="player", name="Jack"),
                ],
            ),
            metadata=(("trial-id", "abc"), ("actor-id", "0")),
        )

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[
                    TrialActor(actor_class="player", name="Joe"),
                    TrialActor(actor_class="player", name="Jack"),
                ],
            ),
            metadata=(("trial-id", "abc"), ("actor-id", "1")),
        )

        await stub.Start(
            AgentStartRequest(
                impl_name="blearg",
                actors_in_trial=[TrialActor(actor_class="player", name="Joe")],
            ),
            metadata=(("trial-id", "def"), ("actor-id", "0")),
        )

        def0_decide_conn = stub.Decide(metadata=(("trial-id", "def"), ("actor-id", "0")))
        abc0_decide_conn = stub.Decide(metadata=(("trial-id", "abc"), ("actor-id", "0")))
        abc1_decide_conn = stub.Decide(metadata=(("trial-id", "abc"), ("actor-id", "1")))

        for count in range(2):  # the hard way
            await abc0_decide_conn.write(make_req(count))
            tmp0 = await abc0_decide_conn.read()
            act0 = data_pb2.Action()
            act0.ParseFromString(tmp0.action.content)
            print(f"Recieved from actor 0 - {act0}")
            # print('Feedback from actor 0',tmp0.feedbacks)

            await abc1_decide_conn.write(make_req(count))
            tmp1 = await abc1_decide_conn.read()
            act1 = data_pb2.Action()
            act1.ParseFromString(tmp1.action.content)
            print(f"Recieved from actor 1 - {act1}")
            # print('Feedback from actor 1',tmp1.feedbacks)

            feedback_list0 = []
            feedback_list1 = []
            values0 = []
            values1 = []

            for feedback in tmp0.feedbacks:
              if feedback.actor_id == 0:
                feedback_list0.append(feedback)
                values0.append(feedback.value)
              else:
                feedback_list1.append(feedback)
                values1.append(feedback.value)
            for feedback in tmp1.feedbacks:
              if feedback.actor_id == 0:
                feedback_list0.append(feedback)
                values0.append(feedback.value)
              else:
                feedback_list1.append(feedback)
                values1.append(feedback.value)

            print("FFFF0000", feedback_list0) #, 'VVV000', new_value0)
            print("FFFF1111", feedback_list1) #, 'VVV000', new_value1)

            if feedback_list0:
                new_value0 = sum(values0)/float(len(values0))

                reward0 = Reward(value = new_value0,
                    confidence = 1.0)
                reward0.feedbacks.extend(feedback_list0)

                await stub.Reward(
                  AgentRewardRequest(
                    trial_id = "abc",
                    actor_id = 0,
                    tick_id = -1,
                    reward = reward0), 
                  metadata=(("trial-id", "abc"), ("actor-id", "0"))
                )

            if feedback_list1:

                new_value1 = sum(values1)/float(len(values1))

                reward1 = Reward(value = new_value1,
                    confidence = 1.0)
                reward1.feedbacks.extend(feedback_list0)

                await stub.Reward(
                  AgentRewardRequest(
                    trial_id = "abc",
                    actor_id = 1,
                    tick_id = -1,
                    reward = reward1), 
                  metadata=(("trial-id", "abc"), ("actor-id", "1"))
                )


        await abc1_decide_conn.write(make_req(2, True))
        mytest = await abc1_decide_conn.read()
        await abc0_decide_conn.write(make_req(2, True))
        mytest = await abc0_decide_conn.read()

asyncio.run(main())
