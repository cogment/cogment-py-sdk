import cogment
import cog_settings

import data_pb2
import asyncio

AS_SERVER = True

# N.B. Doesn't work yet.
async def my_environment(env, trial):
    obs_1 =  data_pb2.Observation()
    obs_2 =  data_pb2.Observation()
    
    observations = [
        ("player.*", obs_1)
        ("bob", obs_2)
    ]

    for i in range(10)
        actions = await env.update(observations)

        if actions.player[0].shoot:


async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_environement(
        impl=my_environment, impl_name="release")

    server.register_environement(
        impl=my_environment, impl_name="debug")

    await server.run()
   

asyncio.run(main())
