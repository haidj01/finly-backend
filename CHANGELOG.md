# Changelog

## [0.3.1](https://github.com/haidj01/finly-backend/compare/v0.3.0...v0.3.1) (2026-04-29)


### Bug Fixes

* improve trending API reliability and performance ([2020402](https://github.com/haidj01/finly-backend/commit/2020402c99a49acadf1886910fb78751618fa0d5))
* translate Claude API error status codes to 502 ([ca0f570](https://github.com/haidj01/finly-backend/commit/ca0f5701ad6a192a9dc35ace619b9c7ebdd7cca7))
* trending API reliability and performance improvements ([c2e22ef](https://github.com/haidj01/finly-backend/commit/c2e22efc0287cf52c91f561dbc88915711613422))

## [0.3.0](https://github.com/haidj01/finly-backend/compare/v0.2.0...v0.3.0) (2026-04-23)


### Features

* add stock detail API endpoints and strategy proxy routes ([ae3db2e](https://github.com/haidj01/finly-backend/commit/ae3db2e9593fc142a53859411d1b22f9b4013197))
* stock detail API endpoints and strategy proxy routes ([0291ca9](https://github.com/haidj01/finly-backend/commit/0291ca9f6cfeec1990d2de9fb39181d0ba88e10e))


### Bug Fixes

* add AGENT_URL to docker-compose template in userdata.sh ([8fd5070](https://github.com/haidj01/finly-backend/commit/8fd5070e721614e765789f386420cbe3cf4a5e52))
* change /version to /api/version for CloudFront routing ([d8f7cef](https://github.com/haidj01/finly-backend/commit/d8f7cef0707d50fad00abb5c85e99e144ae27f0b))
* proxy agent version through backend /version endpoint ([670af41](https://github.com/haidj01/finly-backend/commit/670af4107e1f79650994741ae91c4447621f539d))

## [0.2.0](https://github.com/haidj01/finly-backend/compare/v0.1.0...v0.2.0) (2026-04-23)


### Features

* add auth route, trending improvements, and EC2 terraform infra ([12c5e65](https://github.com/haidj01/finly-backend/commit/12c5e65d7562e1e916ea9a39d2910a417a0a9c08))
* add auth route, trending improvements, and EC2 Terraform infra ([e25fe10](https://github.com/haidj01/finly-backend/commit/e25fe1062ddb16f549cf74f82a4a63e96c33d4f7))
* add release-please versioning and /version endpoint ([d1fbd9a](https://github.com/haidj01/finly-backend/commit/d1fbd9adb0067f0749c5250e922706377e4924b7))
* expose /version endpoint for deployment version display ([d4d8c54](https://github.com/haidj01/finly-backend/commit/d4d8c54fcc1e20b8a49f85b7fe076a949e6aa89d))


### Bug Fixes

* resolve pylint CI failures ([45a4f4a](https://github.com/haidj01/finly-backend/commit/45a4f4abb83b3f6f932752421907cacf9616f920))
* resolve remaining pylint warnings ([330254b](https://github.com/haidj01/finly-backend/commit/330254b4578f35caf83de5398145427e4d214422))
