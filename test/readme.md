# General Notes for Cogment Python SDK test Directory


## Application Usage Examples & Pseudo-Orchestrator Instances

The following table outlines the usage examples, pseudo orchestrator instances, and other file relationships used when running the usage examples.  The agent, environment, pre-hook and datalog usage examples call the appropriate Cogment 1.0 Python SDK services.

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

<sub><sup>Notes - <br> \* Data will be written to a ".csv" file
                    <br>\*\* Data will be written to a postgreSQL database
                	<br>\+ Environment variables for db, host & csv filenames (run first: source env_var)
                    <br>\+\+ Contains python dependencies for postgres example (run first: pip install -r requirements.txt)
                </sup></sub>

