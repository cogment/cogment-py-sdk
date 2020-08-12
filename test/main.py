import cogment
import cog_settings

import data_pb2

async def my_agent(actor, trial):
    print(f"starting agent {actor.name} for trial id {trial.id_}")

    print(f"{actor.name} is waiting for initial observation...")
    observation = await actor.start()

    while not trial.over:
        print(f" {actor.name} has observed {observation}")
        observation = await actor.do_action(data_pb2.Action(value=3))

    print(f"{actor.name}'s trial is over...")

if __name__=="__main__":
    server = cogment.Server(cog_project=cog_settings)
    
    server.register_actor(impl=my_agent, impl_name="blearg", actor_class="player")
    
    server.run()
