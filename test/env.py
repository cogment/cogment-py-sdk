import cogment
import cog_settings

import data_pb2
import asyncio


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


    for i in range(5):
        obs_1 =  data_pb2.Observation(value=i+55)
        obs_2 =  data_pb2.Observation(value=i+66)
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
