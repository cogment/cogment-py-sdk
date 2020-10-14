import cogment
import cog_settings

import data_pb2
import asyncio

async def my_client(actor, trial):


    def on_reward(r):
        print("Bring on the rewards! \n",r)

    actor.on_reward = on_reward


    observation = await actor.start()
    print(f"First observation from {actor.name} is {observation}")

    # while not trial.over:
    for count in range(5):
        observation = await actor.do_action(data_pb2.Action(value=12 + count))
        print(f"{actor.name} has observed {observation}")

        # send feedback here
        # trial.add_feedback(to=['*'],value=77+count,confidence=1)
        trial.actors[1].add_feedback(value=72+count,confidence=1)

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
