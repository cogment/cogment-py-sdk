# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## Unreleased

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
