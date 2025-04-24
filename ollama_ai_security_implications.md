# Ollama Security Research Assisted by AI

## Overview

This document chronicles the development of a proof-of-concept tool for discovering and benchmarking exposed Ollama API instances, created entirely through a conversation with Claude (Anthropic's AI assistant). The entire process - from initial vulnerability discovery to writing functional code that can scan the internet, create databases of vulnerable instances, and benchmark their performance - was accomplished through AI assistance alone.

## Security Implications

This project demonstrates a concerning security trend: **the barrier to entry for finding and exploiting vulnerabilities has been dramatically lowered by generative AI**. What previously required specialized knowledge in network security, programming, and vulnerability research can now be accomplished by individuals with minimal technical background by leveraging AI assistants.

Key concerns:
- Complex security research can be performed without deep technical expertise
- Vulnerability scanning tools can be created rapidly with AI assistance
- From concept to working exploit can happen in hours rather than days or weeks
- AI can suggest methods of exploitation not initially considered by the user

## Conversation History

### Initial Vulnerability Analysis

**Human**: Can you analyze these three files to understand the vulnerability proof of concept?

**AI**: After analyzing the files (ollama_scanner.py, query_models.py, and run.sh), I can see they form a proof-of-concept tool for finding exposed Ollama AI model servers on the internet. The vulnerability is that Ollama instances are publicly accessible without authentication, allowing unauthorized access to AI models.

The ollama_scanner.py file scans IP addresses to find servers with the Ollama API exposed, while query_models.py allows querying these exposed servers to find what models are available. The run.sh script is a simple automation tool.

### CVE Report Creation

**Human**: Can you create a CVE report for this vulnerability?

**AI**: *[Created a detailed CVE report describing an authentication bypass vulnerability in Ollama API that allows unauthorized access to AI models, with a CVSS score of 9.1 (Critical)]*

### UPnP Auto-Forwarding Concerns

**Human**: Can you update the report with details about UPnP auto-forwarding?

**AI**: *[Updated the report to include how UPnP auto-forwarding exacerbates the vulnerability by potentially exposing private Ollama instances to the internet without user knowledge]*

### Creating the Scanner and Benchmark Tools

**Human**: *[Various requests for code refinements, database integration, and expanded functionality]*

**AI**: *[Created and refined multiple Python scripts for scanning, database management, and benchmarking exposed Ollama instances]*

### Benchmark Database Integration

**Human**: *[Request for integrated benchmark script that connects to database]*

**AI**: *[Created ollama_benchmark_db.py with functionality to test performance metrics and save results to database]*

## Technical Details

The created tools can:
1. Scan the internet for exposed Ollama instances
2. Extract available models and server information
3. Store findings in a SQLite database
4. Benchmark discovered instances for performance metrics:
   - Response time
   - Tokens per second
   - First token latency
   - Context handling capability
   - Concurrency support

## Conclusion

This project was constructed entirely through conversation with an AI assistant, without requiring specialized knowledge of vulnerability research or advanced programming skills. It serves as a proof-of-concept demonstrating how AI drastically lowers the barrier to entry for security research and potentially malicious exploitation.

The implications for security are significant: organizations must be increasingly vigilant about securing AI infrastructure, as the knowledge gap that previously served as a barrier against widespread exploitation is rapidly disappearing thanks to generative AI tools.

The continuous scanning command for this tool is:
```bash
python ollama_scanner.py --continuous --delay 3600 --db ollama_instances.db --port-range 11434-11444 --timeout 5 --threads 50 --save-results
```

This conversation and the resulting code demonstrate the need for:
1. Better security practices for AI deployment
2. Authentication requirements for AI model APIs
3. Raising awareness about the lowered barrier to entry for vulnerability research
4. Consideration of these factors when evaluating the severity of security vulnerabilities

This document was compiled as supporting material for a CVE submission regarding Ollama's lack of authentication mechanisms. 