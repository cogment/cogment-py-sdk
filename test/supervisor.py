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
