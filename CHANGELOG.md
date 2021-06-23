# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## Unreleased

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
