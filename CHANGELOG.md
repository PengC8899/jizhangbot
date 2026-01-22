# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-01-22

### Added
- **Redis Caching**: Implemented `CacheService` to cache group configurations, significantly reducing database read pressure.
- **Sentry Integration**: Added Sentry support for real-time error monitoring in production.
- **Connection Pooling**: Configured SQLAlchemy connection pool with `pool_pre_ping` for better stability.

### Changed
- **Database Performance**: Enabled WAL (Write-Ahead Logging) mode for SQLite to improve concurrency support.
- **Dependencies**: Added `redis` and `sentry-sdk` to `requirements.txt`.

## [0.2.0] - 2026-01-22

### Added
- **Web Dashboard**: Added a visual admin dashboard at `/dashboard` for managing trial requests.
- **Trial Authorization**: Implemented `TrialRequest` model and approval flow. Users can now request trials via private chat.
- **Welcome Message**: Added a stylized welcome message for new group members.
- **Enhanced Formatting**: Updated transaction response format to match "HYPay" commercial style (with emojis and detailed breakdown).
- **Flexible Regex**: Improved command regex to handle leading spaces (e.g., ` +1000`).

### Changed
- **License Logic**: Updated `check_license` to allow authorized users to operate in unauthorized groups (User-level license propagation).
- **Database**: Added `expire_at` and `license_key` columns to `group_configs` table.
- **Config**: Switched default `TG_MODE` to `polling` for easier local development.

### Fixed
- **Bot Responsiveness**: Fixed issue where Bot ignored commands in groups due to strict regex and missing `/start` handler.
- **Database Schema**: Fixed crash caused by missing columns in `GroupConfig`.

## [0.1.0] - 2026-01-20

### Added
- Initial release of HuiYing Ledger Bot.
- Core features: Multi-bot support, Ledger recording, Excel export.
- FastAPI backend with Webhook support.
