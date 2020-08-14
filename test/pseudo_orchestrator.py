import grpc
from cogment.api.agent_pb2 import AgentStartRequest, AgentDataRequest, AgentActionReply
import cogment.api.agent_pb2_grpc
from cogment.api.common_pb2 import TrialActor
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue


def make_req(val, final=False):
    obs = data_pb2.Observation(value=val)
    req = AgentDataRequest()
    req.observation.data.snapshot = True
    req.observation.data.content = obs.SerializeToString()
    req.observation.tick_id = 12

    req.final = final
    return req

async def main():
    async with grpc.experimental.aio.insecure_channel('localhost:9001') as channel:
        stub = cogment.api.agent_pb2_grpc.AgentEndpointStub(channel)

        await stub.Start(
          AgentStartRequest(
              impl_name="blearg",
              actors_in_trial=[
                TrialActor(actor_class="player", name="Joe"),
                TrialActor(actor_class="player", name="Jack")
              ]),
          metadata=(("trial-id", "abc"), ("actor-id", "0"))
        )

        await stub.Start(
          AgentStartRequest(
              impl_name="blearg",
              actors_in_trial=[
                TrialActor(actor_class="player", name="Joe"),
                TrialActor(actor_class="player", name="Jack")
              ]), 
          metadata=(("trial-id", "abc"), ("actor-id", "1"))
        )

        await stub.Start(
          AgentStartRequest( 
              impl_name="blearg",
              actors_in_trial=[
                TrialActor(actor_class="player", name="Joe")           
              ]), 
          metadata=(("trial-id", "def"), ("actor-id", "0"))
        )

        decide_conn = stub.Decide(metadata=(("trial-id", "def"), ("actor-id", "0")))
    
        for count in range(4):
            await decide_conn.write(make_req(count))
            tmp = await decide_conn.read()
            act = data_pb2.Action()
            act.ParseFromString(tmp.action.content)
            print(f"Recieved from actor - {act}")

        await decide_conn.write(make_req(2, True))
        mytest = await decide_conn.read()

asyncio.run(main())
