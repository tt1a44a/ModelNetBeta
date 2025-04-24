# Database Schema Issues Report

Generated: 2025-04-18 11:04:38

## Warnings (4)

| Type             | Description                                                        | Impact   | Recommendation                                                                                                         |
|:-----------------|:-------------------------------------------------------------------|:---------|:-----------------------------------------------------------------------------------------------------------------------|
| NULL Values      | 7254 NULL values in endpoints.verification_date                    | Medium   | Update NULL values with CURRENT_TIMESTAMP                                                                              |
| NULL Values      | 167 NULL values in endpoints.last_check_date                       | Medium   | Update NULL values with CURRENT_TIMESTAMP                                                                              |
| Foreign Key Rule | FK benchmark_results_model_id_fkey has SET NULL instead of CASCADE | Medium   | ALTER TABLE benchmark_results DROP CONSTRAINT benchmark_results_model_id_fkey, then add it back with ON DELETE CASCADE |
| Table Bloat      | Table metadata has 17 dead tuples (57.0% of total)                 | Medium   | VACUUM ANALYZE metadata                                                                                                |

## Informational (10)

| Type            | Description                                                                                         | Impact   | Recommendation                                                                                         |
|:----------------|:----------------------------------------------------------------------------------------------------|:---------|:-------------------------------------------------------------------------------------------------------|
| Extra Tables    | Unexpected tables found: user_selected_models, chat_history                                         | Low      | Review and determine if they are needed                                                                |
| Redundant Index | Index endpoints_verified_idx might be redundant with idx_endpoints_verified_active                  | Low      | Consider dropping endpoints_verified_idx if queries use idx_endpoints_verified_active                  |
| Redundant Index | Index endpoints_verified_idx might be redundant with idx_endpoints_verified_honeypot                | Low      | Consider dropping endpoints_verified_idx if queries use idx_endpoints_verified_honeypot                |
| Redundant Index | Index models_endpoint_id_idx might be redundant with models_endpoint_id_name_key                    | Low      | Consider dropping models_endpoint_id_idx if queries use models_endpoint_id_name_key                    |
| Redundant Index | Index verified_endpoints_endpoint_id_idx might be redundant with verified_endpoints_endpoint_id_key | Low      | Consider dropping verified_endpoints_endpoint_id_idx if queries use verified_endpoints_endpoint_id_key |
| Redundant Index | Index verified_endpoints_endpoint_id_key might be redundant with verified_endpoints_endpoint_id_idx | Low      | Consider dropping verified_endpoints_endpoint_id_key if queries use verified_endpoints_endpoint_id_idx |
| View Triggers   | View 'servers' has all required INSTEAD OF triggers                                                 | Low      | No action needed                                                                                       |
| Unused Index    | Index metadata_key_idx on metadata (size: 16 kB) has never been used                                | Low      | Consider dropping: DROP INDEX metadata_key_idx                                                         |
| Unused Index    | Index idx_chat_history_user_id on chat_history (size: 8192 bytes) has never been used               | Low      | Consider dropping: DROP INDEX idx_chat_history_user_id                                                 |
| Unused Index    | Index idx_chat_history_model_id on chat_history (size: 8192 bytes) has never been used              | Low      | Consider dropping: DROP INDEX idx_chat_history_model_id                                                |

## Summary

- 0 critical issues
- 4 warnings
- 10 informational items

## Fix SQL

The following SQL commands can be used to fix the identified issues:

```sql
-- Fix for: FK benchmark_results_model_id_fkey has SET NULL instead of CASCADE
ALTER TABLE benchmark_results DROP CONSTRAINT benchmark_results_model_id_fkey, then add it back with ON DELETE CASCADE;

```
