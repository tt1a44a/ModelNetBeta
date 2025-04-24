# Servers View Update Fix

This document explains the implementation of the "Fix View Update Issue" from the Ollama Scanner Improvement Plan.

## Problem Description

The Ollama Scanner system uses a view named `servers` for backward compatibility with older code. This view combines data from the `endpoints` and `verified_endpoints` tables. The issue was that this view was not updatable - changes made to the view were not propagated to the underlying tables, causing synchronization problems between different components of the system.

## Solution

We implemented proper PostgreSQL `INSTEAD OF` triggers on the `servers` view. These triggers intercept INSERT, UPDATE, and DELETE operations on the view and translate them into appropriate operations on the underlying tables.

### The Fix Includes:

1. **INSTEAD OF INSERT Trigger**: When a record is inserted into the `servers` view, it:
   - Inserts a new record into the `endpoints` table with `verified = 1`
   - Inserts a matching record into the `verified_endpoints` table
   - Handles conflict cases (duplicate IP/port) gracefully

2. **INSTEAD OF UPDATE Trigger**: When a record in the `servers` view is updated, it:
   - Updates the corresponding record in the `endpoints` table
   - Maintains the relationship with `verified_endpoints`

3. **INSTEAD OF DELETE Trigger**: When a record is deleted from the `servers` view, it:
   - Deletes the corresponding record from the `endpoints` table
   - The deletion cascades to `verified_endpoints` through foreign key constraints

## Files Implemented

1. **fix_servers_view.sql**: Contains the SQL commands to create the INSTEAD OF triggers
2. **apply_view_update_fix.sh**: Shell script to apply the fix and verify it works

## How to Apply the Fix

To apply the fix, follow these steps:

1. Make sure PostgreSQL is running and accessible
2. Run the script:
   ```bash
   ./apply_view_update_fix.sh
   ```
3. Check the log file (`view_update_fix.log`) to verify the fix was applied successfully

## Testing the Fix

The application script automatically tests the fix by:
1. Inserting a test record into the `servers` view
2. Verifying the record appears in the underlying tables
3. Deleting the test record via the view
4. Verifying the deletion propagates correctly

## Expected Results

After applying the fix:

1. Insert operations on the `servers` view will create records in both `endpoints` (with `verified = 1`) and `verified_endpoints` tables
2. Update operations on the `servers` view will update the corresponding records in the `endpoints` table
3. Delete operations on the `servers` view will delete the corresponding records from both tables
4. The Discord bot and pruner should now be able to correctly interact with the database through the `servers` view

## Why This Matters

This fix ensures consistent data flow between different components of the Ollama Scanner system:
- The scanner discovers endpoints and adds them to the `endpoints` table
- The pruner verifies endpoints and updates their status
- The Discord bot displays and manages endpoints through the `servers` view

With this fix, all components can read and write to the database correctly, eliminating data synchronization issues.

## Next Steps

After applying this fix, consider implementing:
1. Regular database integrity checks
2. Enhanced logging for database operations
3. A database status dashboard to monitor synchronization

These additional improvements are outlined in the Ollama Scanner Improvement Plan. 