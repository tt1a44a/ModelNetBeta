# Ollama Scanner Update Guide

This guide will help you migrate from older versions of the Ollama Scanner to the latest version, addressing changes in command-line arguments and functionality.

## New Parameters in Version 2.4.0

The latest version includes two new parameters that provide more control over how the scanner interacts with your database:

### `--status` Parameter

The `--status` parameter allows you to specify the status to assign to newly verified instances.

- **Default value**: `scanned`
- **Possible values**: Any string (common values include `scanned`, `verified`, `failed`, etc.)
- **Example usage**: `--status verified`

This parameter is useful when:
- You want to differentiate between instances discovered in different scanning sessions
- You're using a custom workflow for processing instances
- You're integrating with other tools that rely on specific status values

### `--preserve-verified` Parameter

The `--preserve-verified` parameter controls whether existing verified instances in the database are preserved during scanning.

- **Default value**: `true` (preserve existing verified instances)
- **Related parameter**: `--no-preserve-verified` (explicitly sets preserve-verified to false)
- **Example usage**: `--preserve-verified` or `--no-preserve-verified`

This parameter is useful when:
- You want to keep instances that have been manually verified or validated
- You want to run a completely fresh scan that overrides all previous data
- You're maintaining multiple databases with different verification states

## Migrating from Older Versions

If you're upgrading from an older version of the Ollama Scanner, here's how to adapt your existing scripts and commands:

### Updating Command-Line Arguments

**Old command:**
```
python3 ollama_scanner.py --method masscan --network 192.168.1.0/24 --threads 10
```

**New command:**
```
python3 ollama_scanner.py --method masscan --network 192.168.1.0/24 --threads 10 --status scanned --preserve-verified
```

Note that the new default behavior is the same as the old behavior, so if you want to maintain the previous functionality, you don't need to change anything. The new parameters just provide more control.

### Updating Shell Scripts

If you have your own custom shell scripts calling the scanner, update them to include the new parameters:

**Old script:**
```bash
python3 ollama_scanner.py --method masscan --input results.txt --threads 10
```

**New script:**
```bash
python3 ollama_scanner.py --method masscan --input results.txt --threads 10 --status scanned --preserve-verified
```

### Using the Automated Scanner Script

For the most convenient usage, use the provided `run_scanner.sh` script:

```bash
./run_scanner.sh --status verified --limit 1000 --network 192.168.1.0/24 --threads 10 --verbose
```

## Common Workflows

### Standard Scan with Default Settings

```bash
./run_scanner.sh
```

This is equivalent to the old default behavior - it will scan using default settings and mark new instances as "scanned" while preserving any existing verified instances.

### Fresh Scan (Overwriting Existing Data)

```bash
./run_scanner.sh --no-preserve-verified
```

This will perform a scan without preserving existing verified instances, effectively starting fresh.

### Verification Scan (Marking Instances as Verified)

```bash
./run_scanner.sh --status verified
```

This will scan and mark new instances as "verified" instead of "scanned".

### Targeted Scan with Custom Status

```bash
./run_scanner.sh --network 192.168.1.0/24 --status custom_scan_2024
```

This will scan a specific network range and mark new instances with a custom status to identify them.

## Additional Resources

- See the README.md file for full documentation of all parameters
- Check the SCHEMA_README.md for information about the database schema 
- Refer to the main help text by running `./run_scanner.sh --help`

For any issues or questions, please open an issue on the GitHub repository. 