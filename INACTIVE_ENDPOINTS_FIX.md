# Inactive Endpoints Fix

## The Issue

The Discord bot has been experiencing an issue where it tries to use endpoints that are inactive (timed out, cannot connect). This happens because:

1. When an endpoint times out or can't connect, it's correctly marked as inactive with `is_active = FALSE`
2. However, it still retains its `verified = 1` status
3. The Discord bot queries use `verified = 1 AND is_honeypot = FALSE AND is_active = TRUE`
4. The `is_active = TRUE` condition alone should filter out inactive endpoints
5. But due to possibly inconsistent query logic across the application, some queries might only check `verified = 1` without checking `is_active = TRUE`

## The Solution

We've implemented two fixes:

1. **Code Fix**: Modified the `mark_endpoint_as_inactive` function in `prune_bad_endpoints.py` to also set `verified = 0` when an endpoint is marked as inactive, and to remove it from the `verified_endpoints` table.

2. **Database Fix**: Created a SQL script `fix_inactive_endpoints.sql` to update existing inactive endpoints that are still marked as verified.

## How to Apply the Fixes

1. **Deploy the Code Fix**:
   - Update `prune_bad_endpoints.py` with the new `mark_endpoint_as_inactive` function
   - Restart any services using this function

2. **Run the Database Fix**:
   ```bash
   psql -h your_db_host -U your_db_user -d your_db_name -f fix_inactive_endpoints.sql
   ```
   
   This will:
   - Show the current state of inactive and verified endpoints
   - Update all inactive endpoints to also be unverified (set `verified = 0`)
   - Remove inactive endpoints from the `verified_endpoints` table
   - Show the updated state after the fixes

3. **Verify the Fix**:
   - Check that the Discord bot no longer tries to use inactive endpoints
   - Run the `/offline_endpoints stats` command to verify that all inactive endpoints are also unverified

## Expected Results

After applying these fixes:

1. All inactive endpoints will also be unverified (`verified = 0`)
2. The Discord bot will only select endpoints that are verified, active, and not honeypots
3. Users will no longer see timeout errors for inactive endpoints

## Maintenance Recommendations

To prevent this issue in the future:

1. Regularly run the pruner to detect and mark inactive endpoints
2. Periodically check for inconsistencies between `verified` and `is_active` statuses
3. Consider adding database constraints to ensure inactive endpoints cannot be verified 