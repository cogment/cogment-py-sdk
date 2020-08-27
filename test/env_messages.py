import cogment
import cog_settings

import data_pb2
import asyncio

AS_SERVER = True

async def my_environment(env, trial):

    def on_message(sender, msg):
        print(f"Joe received message {msg.name} from agent {sender}!")

    env.on_message = on_message

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

        msg_test = data_pb2.MessageTest(name="Doctor Who " + str(count))
        msg_test1 = data_pb2.MessageTest(name="Horton the Who " + str(count))

        trial.send_message(to=['*'],user_data=msg_test)
        # trial.actors[1].send_message(user_data=msg_test)
        # trial.actors[0].send_message(user_data=msg_test)
        # trial.env.send_message(user_data=msg_test)
        # trial.env.send_message(user_data=msg_test1)

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
