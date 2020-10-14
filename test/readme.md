# General Notes for Cogment Python SDK test Directory


## Application Usage Examples & Pseudo-Orchestrator Instances

The files included here in this test directory provide basic usage and test examples for different aspects of the python Cogment 1.0 SDK.  The following table outlines the usage examples, pseudo orchestrator instances, and other file relationships used when running the usage examples.  The client, agent, environment, pre-hook and datalog are essentially user Usage Example files and call the appropriate Cogment 1.0 Python SDK services while the Pseudo Orchestrator files act as the orchestrator.

| Usage Example | Usage Example File | Pseudo Orchestrator File | Other Files |
| ------------ |--------- | --------- | ---- |
| Agent Reward/Feedback | agent_feedback.py | pseudo_orch_agent_feedback.py | |
| Agent Messages | agent_messages.py | pseudo_orch_messages.py | |
| Environment | env.py | pseudo_orch_env.py | |
| Environment Reward/Feedback | env_feedback.py | pseudo_orch_env_feedback.py | |
| Environment Messages | env_messages.py | pseudo_orch_env_messages.py | |
| Configurator Prehook | supervisor.py | pseudo_orch_prehook.py | |
| Datalog |  datalog.py | pseudo_orch_datalog.py | |
| Datalog to CSV* | datalog_to_csv.py | pseudo_orch_datalog.py | env_var+ |
| Datalog to Postgresql** | datalog_to_postgres.py | pseudo_orch_datalog.py | env_var+, requirements.txt++ |
| Client Simple | client_simple.py | pseudo_orch_client_simple.py | |
| Client Reward/Feedback | client_feedback.py | pseudo_orch_client_feedback.py | |
| Client Messages | client_messages.py | pseudo_orch_client_messages.py | |


<sup>Notes - <br> In all cases, the Usage Example File should be run first, with the exception of the Client usage examples where the Pseudo Orchestrator File should be run first.
	<br> \* Data will be written to a ".csv" file
                    <br>\*\* Data will be written to a postgreSQL database
                	<br>\+ Environment variables for db, host & csv filenames (run first: source env_var)
                    <br>\+\+ Contains python dependencies for postgres example (run first: pip install -r requirements.txt)
                </sup>

