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
from cogment.api.environment_pb2 import EnvOnMessageRequest, EnvStartRequest, EnvStartReply, EnvEndRequest, EnvEndReply, EnvUpdateRequest, EnvUpdateReply, ActionSet
import cogment.api.environment_pb2_grpc
from cogment.api.common_pb2 import TrialActor
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue
import importlib
import cog_settings

def send_actions_req(value_list):

    action_set = ActionSet()

    action = data_pb2.Action()
    action.value = value_list[0]
    action.SerializeToString()
    action_set.actions.append(action.SerializeToString())
    action.value = value_list[1]
    action.SerializeToString()
    action_set.actions.append(action.SerializeToString())

    req = EnvUpdateRequest(action_set=action_set)

    return req


async def main():
    async with grpc.experimental.aio.insecure_channel('localhost:9001') as channel:
        stub = cogment.api.environment_pb2_grpc.EnvironmentEndpointStub(channel)

        # send start
        start_conn = stub.Start(
            EnvStartRequest(
                impl_name="release",
                actors_in_trial=[
                  TrialActor(actor_class="player", name="Joe"),
                  TrialActor(actor_class="player", name="Jack")
                ]),
            metadata=(("trial-id", "abc"),)
        )

        # read observation from start
        tmp = await start_conn.read()
        for actor_index, observation_data in enumerate(tmp.observation_set.observations):
            obs = data_pb2.Observation()
            obs.ParseFromString(observation_data.content)
            print(f"Observation for actor {actor_index}: {obs}")

        update_conn = stub.Update(metadata=(("trial-id", "abc"),))

        for count in range(5):

            # update_conn = stub.Update(metadata=(("trial-id", "abc"),))
            await update_conn.write(send_actions_req([88+count,99+count]))

            tmp = await update_conn.read()
            for actor_index, observation_data in enumerate(tmp.observation_set.observations):
                obs = data_pb2.Observation()
                obs.ParseFromString(observation_data.content)
                print(f"Observation for actor {actor_index}: {obs}")

            env_message_list = []
            for message in tmp.messages:
                class_type = message.payload.type_url.split('.')
                user_data = getattr(importlib.import_module(
                    cog_settings.protolib), class_type[-1])()
                message.payload.Unpack(user_data)

                if message.receiver_id == -1:
                    # print(f"Message sent to Env is {message.payload.value}")
                    print(f"Message sent from Env to Env is {user_data}")
                    env_message_list.append(message)
                else:
                    # print(f"Message sent to Actor {message.receiver_id} is {message.payload.value}")
                    print(f"Message sent from Env to Actor {message.receiver_id} is {user_data}")


            if env_message_list:
                eom = EnvOnMessageRequest(
                    trial_id = "abc",
                    actor_id = 0)
                eom.messages.extend(env_message_list)

                await stub.OnMessage(eom,
                  metadata=(("trial-id", "abc"),)
                )


        end_conn = stub.End(
            EnvEndRequest(),
            metadata=(("trial-id", "abc"),)
        )

asyncio.run(main())
