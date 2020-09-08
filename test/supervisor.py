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

from types import SimpleNamespace as ns

PLAYER_URL = 'grpc://player:9000'

async def my_prehook(trial_params):

    actor_settings = {
        "player": ns(
            actor_class='player',
            endpoint=PLAYER_URL,
            config=None
        )
    }


    trial_config = trial_params.trial_config

    actors = []

    for i in range(trial_config.env_config.num_agents):
        actors.append(actor_settings["player"])

    trial_params.actors = actors

    trial_params.environment.config = trial_config.env_config

    return trial_params



async def main():

    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_prehook(impl=my_prehook)

    await server.run()
   

asyncio.run(main())
