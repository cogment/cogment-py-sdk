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
    
        server.register_actor(impl=my_agent, impl_name="blearg", actor_class="player")
    
        await server.run()
    else: # As client
        connection = cogment.Connection(cog_project=cog_settings, endpoint="localhost:9000")

        # Create a new trial
        trial = connection.start_trial(data_pb2.TrialConfig(), user_id="This_is_a_test")

        # Join that trial as an actor
        await connection.join_trial(trial_id=trial.id_, actor_id=1, impl=my_agent)

asyncio.run(main())