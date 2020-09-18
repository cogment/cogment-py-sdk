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

async def my_environment(env, trial):

    def on_trial_over():
        print(f"Trial has ended!")

    env.on_trial_over = on_trial_over

    
    obs_1 =  data_pb2.Observation(value=22)
    obs_2 =  data_pb2.Observation(value=33)
    
    # observations = [
    #     ("player.*", obs_1),
    #     ("bob", obs_2)
    # ]

    observations = [
        # ("player.*", obs_1)
        ("Jack", obs_2),
        ("Joe", obs_1)
    ]

    await env.start(observations)

    for count in range(5):

        trial.actors[0].add_feedback(value=2,confidence=1)
        trial.actors[1].add_feedback(value=3,confidence=1)
        # trial.add_feedback(to=['*'],value=3+count,confidence=1)

        obs_1 =  data_pb2.Observation(value=count+55)
        obs_2 =  data_pb2.Observation(value=count+66)
        observations = [
            # ("player.*", obs_1)
            ("Jack", obs_2),
            ("Joe", obs_1)
        ]

        actions = await env.update(observations)

        # if actions.player[0].shoot:
        print('Here are all the player actions',actions.player)

async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_environment(
        impl=my_environment, impl_name="release", env_class="dummy")

    server.register_environment(
        impl=my_environment, impl_name="debug", env_class="dummy")

    await server.run()
   

asyncio.run(main())
