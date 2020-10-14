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

import cogment
import cog_settings

import data_pb2
import asyncio
import time

async def my_client(actor, trial):

    def on_message(sender, msg):
        print(f"Client received message {msg.name} from actor {sender}!")

    actor.on_message = on_message



    observation = await actor.start()
    print(f"First observation from {actor.name} is {observation}")

    # while not trial.over:
    for count in range(5):
        time.sleep(0.5)
        observation = await actor.do_action(data_pb2.Action(value=12 + count))
        print(f"{actor.name} has observed {observation}")

        # send messages here
        msg_test = data_pb2.MessageTest(name="Doctor Who " + str(count))
        trial.send_message(to=['Jack'],user_data=msg_test)

    print(f"{actor.name}'s trial is over...")


async def main():

    # connection = cogment.Connection(
    #     cog_project=cog_settings, endpoint="orchestrator:9000")
    connection = cogment.Connection(
        cog_project=cog_settings, endpoint="localhost:9000")

    print("Connected!")
    # Create a new trial
    trial = await connection.start_trial(
        data_pb2.TrialConfig(), user_id="This_is_a_test")

    print("Created a trial!")

    # maybe add impl_name to following
    await connection.join_trial(
        trial_id=trial.id_,
        actor_id=2,
        actor_class="player",
        impl=my_client
    )

    print("Joined Trial")

asyncio.run(main())
