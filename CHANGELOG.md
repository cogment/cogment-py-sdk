# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## Unreleased

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
