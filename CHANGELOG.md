# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## Unreleased

## v2.10.1 - 2024-01-06

### Fixed

- Updates `grpcio` to work with python 3.10 on macOS.

## v2.10.0 - 2023-11-28

### Added

- Ability to define metadata in the `Context` constructor, they will be passed to all grpc calls.
- Support for SSL grpc endpoints without a private key.

### Fixed

- `context.get_controller([...])`, `context.get_datastore([...])`, `context.get_model_registry_v2([...])` can always be awaited.

## v2.9.0 - 2023-11-14

### Added

- 'Status' RPC support for all services

### Fixed

- Missing directory service type in API

## v2.8.3 - 2023-08-22

### Fixed

- Upgraded to support PyYaml up to 6.0.1 as [v5 was broken](https://github.com/yaml/pyyaml/issues/724) by the release of cython 3.

## v2.8.2 - 2023-07-10

### Fixed

- Return None when no data is availble in datastore content

## v2.8.1 - 2023-06-06

### Fixed

- Use the most recent directory entry when there are duplicates
- Self IP address discovery functionality is now working on macOS

## v2.8.0 - 2023-04-21

### Added

- Option to request full info (not just id and state) from 'watch_trials'
- Ability to use the SDK without spec (cog_settings)
- Automatic port selection for 'Context.serve_all_registered()'
- Ability to specify an explicit host to register a service to the directory
- Ability to specify trial properties for 'Datastore.all_trials()' and 'Datastore.get_trials()'
- Ability to specify trial ids for 'Datastore.all_trials()'

### Changed

- Enable warning and error logging even if user did not define a logging handler
- Warn user when no logging handler is defined (i.e. proper logging is disabled)
- Better self IP address discovery functionality

## v2.7.1 - 2023-03-06

### Fixed

- Deadlock in 'wait_for_newer' method of LatestModel

## v2.7.0 - 2023-02-28

### Changed

- Facility to track latest models automatically in the Model Registry

### Added

- 'properties' attribute to TrialParameters and TrialInfo

## v2.6.0 - 2023-02-03

### Changed

- Prometheus service is disabled by default

### Added

- Model Registry method `iteration_updates` to stream/push new model iterations
- Parameter `wait_for_trials` (for Datastore method `all_trials`) to wait for new trials

## v2.5.0 - 2023-01-26

### Fixed

- In Datastore reward could be returned as 'None' instead of 0.0

### Added

- Simplified interface for Model Registry (context.get_model_registry_v2)

## v2.4.1 - 2022-12-02

- Support and dependency check for python 3.10

## v2.4.0 - 2022-11-18

### Added

- 'COGMENT_LOG_LEVEL' environment variable
- Model Registry client

### Fixed

- Port parameter needs to be an int
- Context datastore request with default endpoint

## v2.3.0 - 2022-09-20

### Fixed

- Reward tick ID was hard coded to -1

### Changed

- Deprecation warning are only logged once

### Added

- 'Version' grpc method for pre-trial hooks
- Out-of-sync flag in datalog samples
- Parameter 'nb_buffered_ticks'
- Support for actor disconnection and response timeout parameters
- Global Directory integration
- Support for self registration to the Directory
- Use environment variable for Directory access details

## v2.2.2 - 2022-06-20

### Fixed

- Generate to handle multiple imports properly
- Output deprecated warning for use of 'snapshot' in received observation

## v2.2.1 - 2022-05-27

### Fixed

- Fix install of the package from a wheel

### Changed

- Replace poetry centric build process with modern setuptools

## v2.2.0 - 2022-05-07

### Added

- Introduce `cogment.generate.generate`, a function making the code generation previously available through `python -m cogment.generate` accessible as a function.

### Changed

- Integration tests are now able to install the Cogment CLI on their own.
- Integration tests no longer uses a Docker image.

### Fixed

- Fix integration test junit report output.

## v2.1.1 - 2022-04-11

### Fixed

- Fixed a typo in the TrialParameter "environemnt_name" to "environment_name"

## v2.1.0 - 2022-03-25

### Changed

- Update of gRPC version to >=1.42 & <1.45
- Deprecate `cogment.LogParams`
- Deprecate current way to use `PrehookSession`
- Deprecate Session 'event_loop', renamed to 'all_events'
- Deprecate DatalogSession 'get_all_samples' renamed 'all_samples'
- Standardize string ouput of classes

### Added

- `cogment.TrialParameters` and `cogment.ActorParameters`
- Add ability to provide parameters on trial start call
- Datastore SDK

### Fixed

- Fix the failure of the cogment package caused by the partial removal of gRPC 1.45 from pypi

## v2.0.2 - 2022-01-03

## v2.0.1 - 2022-01-03

## v2.0.0 - 2022-01-03

## v2.0.0-rc3 - 2021-12-16

### Changed

- cogment.generate now requires semantic arguments

## v2.0.0-rc2 - 2021-12-10

### Changed

- Cleanup user output
- Require grpc protocol url for endpoints

## v2.0.0-rc1 - 2021-12-01

### Changed

- Major internal changes to match API 2.0
- Minor use changes to match API 2.0 and improve usability

## v1.3.1 - 2021-11-18

### Changed

- Restrict the SDK to python >= 3.7 and <3.10 to maintain compatiblity with tensorflow ^2.7.0.
- Update the cogment api to v1.0.0 to v1.2.1

### Fixed

- Added expanation for strict 1.38 requirement on grpcio-tools.
- Enable pre-trial hooks to set a trial's environment's implementation in `prehook_session.environment_implementation`.

## v1.3.0 - 2021-09-23

### Added

- Add `python -m cogment.generate` to compile the protobuf files and generate `cog_settings.py` for a cogment project.
  This is designed as a replacement for the `cogment generate` command for python cogment components.

### Changed

- Update grpc version used to 1.38.1
- Better management of exception in user implementation coroutine

## v1.2.0 - 2021-06-23

### Changed

- The default Prometheus registry is now used by default, it was previously a custom built registry.
  Furthermore, any prometheus registry can be passed to the constructor for `cogment.Context`.
  If `None` is passed prometheus metrics are disabled entirely.
- Passing `None` as the `prometheus_port` in the constructor for `cogment.Context` disables the launch of the Prometheus server.

## v1.1.1 - 2021-06-17

### Changed

- Update copyright notice to use the legal name of AI Redefined Inc.

### Fixed

- Exit datalog loop on receiving the trial `ended` state
- Simulatenous trials with client actors
- Fix index in RecvAction to match the actor list

## v1.1.0 - 2021-06-04

### Changed

- Internal update to change `assert` into more useful statements
- Internal update to add `__str__` to user accessible classes
- Improve log output
- Improve/add error reporting

### Added

- Add function `get_remote_versions` to controller retrieving the remote versions including api and orchestrator versions.

## v1.0.0 - 2021-05-10

- Initial public release.

### Changed

- Using _caret_ requirements for the dependencies of the library to avoid conflicts (cf. https://python-poetry.org/docs/dependency-specification/#caret-requirements)

### Fixed

- Environment can now receive messages

## v1.0.0-beta3 - 2021-04-26

### Fixed

- **Breaking Change** Fix `Controller.get_actors()`, now properly retrieves the actor in a given trial, the function is now `async`.
- Fix unecessary exception thrown in `watch_trial` when async is cancelled

### Added

- Add `Controller.get_trial_info()` to retrieve the information of a given trial.

## v1.0.0-beta2 - 2021-04-15

### Changed

- Add a bit of code to make sure we are running in an asyncio task
- `EventType.FINAL` events do not contain data anymore
- Fix when replies are `None`
- Add `raw_trial_params` in the datalog session

### Fixed

- actor implementations metrics are now reported under `impl_name`

## v1.0.0-beta1 - 2021-04-07

- Initial beta release, no more breaking changes should be introduced.

## v1.0.0-alpha12 - 2021-04-01

### Changed

- Rename ActorClass `id` to `name`

### Fixed

- Remove unused `feedback_space` parameters from `ActorClass`.

## v1.0.0-alpha11 - 2021-03-30

- Technical release, updating dependencies to fixed versions.

## v1.0.0-alpha10 - 2021-03-30

### Added

- Log exporter is now available: trials param, observations, rewards, messages of every trials are sent to the log exporter service.

### Changed

- The value returned from a `RecvReward.all_source` is now a class `RecvRewardSource` instead of a tuple
- Removed parameter `user_id` from `start_trial` (it was not necessary)

## v1.0.0-alpha9 - 2021-03-10

### Added

- **Breaking** Introduce `Controller`, built for a given orchestrator endpoint it can be used to start and terminate trials. Previous ways of accessing the same such are discontinued.
- Introduce the ability to listen for trial events (startup, ending, ...) using `Controller.watch_trials`.

## v1.0.0-alpha8 - 2021-02-26

### Changed

- Session event loops now return classes

## v1.0.0-alpha7 - 2021-02-19

## v1.0.0-alpha6 - 2021-02-17

### Changed

- Removal of "feedback" in rewards.
- Changes to allow for TLS communication.

## v1.0.0-alpha5 - 2021-01-28

### Added

- Manage errors and exceptions at end of trial
- Debug logging at critical points
- Add access to the complete actor configuration from prehook implementations

### Fixed

- Fix the instanciation of prehooks
- Fix the environment "Final" flag not being set in some cases

## v1.0.0-alpha4 - 2021-01-26

### Added

- Catching exceptions that normally occur at the end of trials

### Fixed

- Fix a crash occuring at the end of a trial in service actor implementations involving a `KeyError`.
- tick_id was not being updated

## v1.0.0-alpha3 - 2021-01-11

### Changed

- Create better errors around handling of implementation names

### Added

- Support messsages
- Avoid silent crashes by catching and logging exceptions thrown in async task and user code
- Cancel tasks properly when they raise exceptions
- Debug logging in strategic places

### Fixed

- Send actions list to environment (as documented)
- Store actor class name (string) for user facing session value and hide internal data
- Client servicer code
- Fix prometheus server

## v1.0.0-alpha2 - 2020-12-09

### Fixed

- Add missing cogment protobuf api files to the generated package.

## v1.0.0-alpha1 - 2020-12-07

- Initial alpha release, expect some breaking changes.
