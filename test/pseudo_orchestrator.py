import grpc
from cogment.api.agent_pb2 import AgentStartRequest, AgentDataRequest
import cogment.api.agent_pb2_grpc
from cogment.api.common_pb2 import TrialActor
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue

def make_req(val, final = False):
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
    
        await decide_conn.write(make_req(0))
        print(await decide_conn.read())
        await decide_conn.write(make_req(1))
        print(await decide_conn.read())
        await decide_conn.write(make_req(2, True))
        print(await decide_conn.read())

asyncio.run(main())


    
    