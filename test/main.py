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

AS_SERVER = True

async def my_agent(actor, trial):
    # print("AAAAAAAAAAAA",actor,trial.id_)
    print(f"starting agent {actor.name} for trial id {trial.id_}")
    observation = await actor.start()
    print(f"{actor.name} has observed {observation}")
    count = 4

    while not trial.over:
        observation = await actor.do_action(data_pb2.Action(value=count))
        print(f"{actor.name} has observed {observation}")
        count += 1

    print(f"{actor.name}'s trial is over...")

async def main():
    if AS_SERVER:
        print("This is first")
        server = cogment.Server(cog_project=cog_settings, port=9001)
        server.register_actor(
            impl=my_agent, impl_name="blearg", actor_class="player")
        
        await server.run()
    else:  # As client
        connection = cogment.Connection(
            cog_project=cog_settings, endpoint="localhost:9000")

        # Create a new trial
        trial = connection.start_trial(
            data_pb2.TrialConfig(), user_id="This_is_a_test")

        # Join that trial as an actor
        await connection.join_trial(trial_id=trial.id_, actor_id=1, impl=my_agent)

asyncio.run(main())
