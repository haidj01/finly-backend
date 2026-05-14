# Changelog

## [0.9.0](https://github.com/haidj01/finly-backend/compare/v0.8.0...v0.9.0) (2026-05-14)


### Features

* proxy regime-recommendations endpoint from finly-agent ([f2ff8c5](https://github.com/haidj01/finly-backend/commit/f2ff8c51308a0d75d3373c44a2ea20bbffe0594d))
* proxy regime-recommendations from finly-agent ([08956d5](https://github.com/haidj01/finly-backend/commit/08956d59a4f78cd9a592fe125db2dcd9fd9f0e92))

## [0.8.0](https://github.com/haidj01/finly-backend/compare/v0.7.0...v0.8.0) (2026-05-14)


### Features

* add watchdog status and config proxy routes ([cdcc52f](https://github.com/haidj01/finly-backend/commit/cdcc52ffa813aaa277fff62975dc8bd1f4a60d7e))
* add watchdog status and config proxy routes ([9121e3c](https://github.com/haidj01/finly-backend/commit/9121e3c34c20f0a4a4aae3111ff16a08aaa420a5))

## [0.7.0](https://github.com/haidj01/finly-backend/compare/v0.6.0...v0.7.0) (2026-05-13)


### Features

* add GET/PUT /api/market/trading-mode proxy routes ([0d505a4](https://github.com/haidj01/finly-backend/commit/0d505a499aac1e4f71e2b13ef64a1333593cae5c))
* add GET/PUT /api/market/trading-mode proxy routes ([7ac1e8f](https://github.com/haidj01/finly-backend/commit/7ac1e8f6b7b9ca1529f371755e0f468304c6bf37))

## [0.6.0](https://github.com/haidj01/finly-backend/compare/v0.5.0...v0.6.0) (2026-05-13)


### Features

* load Alpaca live keys from Secrets Manager in userdata.sh ([249872d](https://github.com/haidj01/finly-backend/commit/249872d05f997914e23e3a71e84cabd4140768b4))
* load Alpaca live keys from Secrets Manager in userdata.sh ([abfe43c](https://github.com/haidj01/finly-backend/commit/abfe43c0c7d1f7c3d04cbe82a310356d7dbc1cd1))

## [0.5.0](https://github.com/haidj01/finly-backend/compare/v0.4.0...v0.5.0) (2026-05-13)


### Features

* add market regime proxy endpoint ([0a0fa50](https://github.com/haidj01/finly-backend/commit/0a0fa507302d33edcb588a570b3a126a9b764cea))
* add market regime proxy endpoint ([217574b](https://github.com/haidj01/finly-backend/commit/217574b186bc787828dac1aea4c027a60301335d))
* enrich trending pipeline with Polygon options flow, FMP news, SEC EDGAR insider trades ([80311de](https://github.com/haidj01/finly-backend/commit/80311de9b5e2608c89221b35dc36c34e4cb2e13e))
* enrich trending pipeline with Polygon options, FMP news, SEC EDGAR insider trades ([0b74721](https://github.com/haidj01/finly-backend/commit/0b7472107151a040ed5f587ba142e0d72238945d))

## [0.4.0](https://github.com/haidj01/finly-backend/compare/v0.3.1...v0.4.0) (2026-04-29)


### Features

* **trending:** add fundamentals data (PE, analyst, growth, grade) to stock analysis ([515e711](https://github.com/haidj01/finly-backend/commit/515e711ad6a39fa5c7b0304e10a91d8ff81fe161))
* **trending:** fundamentals data + market-aware cache + penny stock filter ([bb42a98](https://github.com/haidj01/finly-backend/commit/bb42a9810d0eceb7f4f9f363405b928defd3a525))
* 주목종목 가격을 실시간 latestTrade 기준으로 전환 ([c532d8f](https://github.com/haidj01/finly-backend/commit/c532d8f738e0d20dbfb70dee3a5ff2699462aa93))


### Bug Fixes

* **trending:** fix pylint C0411 wrong-import-order (stdlib before third-party) ([09edc93](https://github.com/haidj01/finly-backend/commit/09edc93edf41b39e0ef27b13462930dd164d23b0))

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
