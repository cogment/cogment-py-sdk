import cogment
import cog_settings

import data_pb2
import asyncio

AS_SERVER = True

async def my_agent(actor, trial):

    def on_trial_over():
        print(f"Trial has ended!")

    actor.on_trial_over = on_trial_over

    def on_reward_joe(r):
        print("Joe bring on the rewards! \n",r)
    def on_reward_jack(r):
        print("Jack bring on the rewards! \n",r)
    def on_message_joe(sender, msg):
        # print("Joe received the messages! \n",m)
        print(f"Joe received message {msg.name} from agent {sender}!")
    def on_message_jack(sender, msg):
        # print("Jack received the messages! \n",m)
        print(f"Jack received message {msg.name} from agent {sender}")
    if actor.name == 'Joe':
        actor.on_reward = on_reward_joe
        actor.on_message = on_message_joe
    else:
        actor.on_reward = on_reward_jack
        actor.on_message = on_message_jack
    print(f"starting agent {actor.name} for trial id {trial.id_}")
    observation = await actor.start()
    print(f"{actor.name} has observed {observation}")
    count = 4

    while not trial.over:
        print("**********************************************")
        msg_test = data_pb2.MessageTest(name="Doctor Who " + str(count))
        msg_test1 = data_pb2.MessageTest(name="Horton Who " + str(count))
        trial.send_message(to=['*'],user_data=msg_test)

        if actor.name == 'Joe':
            # trial.env.send_message(msg_test)
            trial.send_message(to=['*'],user_data=msg_test)
            # trial.actors[1].send_message(user_data=msg_test)
            # trial.actors[0].send_message(user_data=msg_test)
            # trial.actors[1].add_feedback(value=3,confidence=1)
            # trial.actors[0].add_feedback(value=3,confidence=1)
            # trial.add_feedback(to=[0,'Jack'],value=3,confidence=1)
            pass
        else:
            # trial.send_message(to=['*'],user_data=msg_test)
            # trial.env.send_message(msg_test)
            # trial.send_message(to=[0,'Jack'],user_data=msg_test)
            # trial.actors[1].send_message(user_data=msg_test)
            # trial.actors[0].send_message(user_data=msg_test)
            # trial.actors[1].add_feedback(value=3,confidence=1)
            # trial.actors[0].add_feedback(value=4,confidence=1)
            # trial.add_feedback(to="*",value=2,confidence=1)
            # trial.add_feedback(to=["*.Joe","*.Jack"],value=2,confidence=1)
            pass

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
