# Honeypot Detection Fix - EC2 Installation Guide

This package contains files to fix the honeypot detection and verification in the ModelNetBeta system. It ensures that no honeypots are accidentally marked as verified or used by the bot.

## Files Included

1. `cleanup_honeypots.py` - Python script to clean up any incorrectly verified honeypots
2. `setup_crontab_ec2.sh` - Shell script to set up weekly automatic cleanup

## Installation Steps

1. **Copy files to the EC2 server**:

   Place the files in the correct locations:
   ```bash
   # Copy the cleanup script to the ModelNetBeta directory
   cp cleanup_honeypots.py /home/ec2-user/ModelNetBeta/
   
   # Make it executable
   chmod +x /home/ec2-user/ModelNetBeta/cleanup_honeypots.py
   ```

2. **Setup the crontab**:

   ```bash
   # Run the setup script (needs sudo)
   sudo bash setup_crontab_ec2.sh
   ```

3. **Run the initial cleanup**:

   ```bash
   # Run the initial cleanup
   cd /home/ec2-user/ModelNetBeta
   python3 cleanup_honeypots.py
   ```

4. **Verify the crontab entry**:

   ```bash
   # Check that the crontab entry was added
   crontab -l
   ```

## Expected Output

The cleanup script will:

1. Check the current state of the database regarding honeypots
2. Execute SQL queries to:
   - Set verified = 0 for all honeypots
   - Remove honeypots from the verified_endpoints table
3. Verify that the cleanup was successful
4. Log all actions to `/var/log/honeypot_cleanup.log`

## Troubleshooting

If you encounter issues:

1. **Check the log file**:
   ```bash
   sudo cat /var/log/honeypot_cleanup.log
   ```

2. **Verify database connection**:
   Make sure the script can connect to the database by checking environment variables.

3. **Manual execution**:
   Try running the script manually to see detailed errors:
   ```bash
   cd /home/ec2-user/ModelNetBeta
   python3 -v cleanup_honeypots.py
   ```

## Next Steps

After this installation, proceed with the other phases of the honeypot detection fix plan, including:

1. Code Enhancement - Standardizing SQL queries
2. Pruner Enhancement - Improved logging and transaction management
3. User Interface Improvements - Clearer display of honeypot information
4. Enhanced Logging - More detailed logging of model selection
5. Debugging Tools - Tools to verify honeypot filtering
6. Regular Verification - Scheduled audits
7. Documentation Updates - Better explanation of honeypot detection
8. Testing - Unit and integration tests

These additional fixes will be provided in subsequent updates. 