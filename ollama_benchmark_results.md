# Ollama Server Benchmark Results

## Command-a:latest Model Testing

The command-a:latest model (111.1B parameters) was not successfully tested on any server due to either:
1. Insufficient memory on the servers
2. Servers being overloaded with requests

## Available Models on Servers

### Server: 203.69.53.137:11434 / 203.69.53.137:12368
- command-a:latest (111.1B, Q4_K_M)
- deepseek-r1:70b (70.6B, Q4_K_M)
- llama3.2-vision:latest (9.8B, Q4_K_M)

### Server: 116.14.227.16:5271
- command-a:latest (111.1B, Q4_K_M)
- qwen2.5:14b (14.8B, Q4_K_M)

## Successful Test Results

We were able to successfully test one server with a smaller model:

### Server: 116.14.227.16:5271 with qwen2.5:14b model

| Metric | Result |
| ------ | ------ |
| Average response time | 21.49 seconds |
| Tokens per second | 1.6 |
| First token latency | 1.19 seconds |
| Success rate | 66% |
| Context handling | Failed |
| Concurrent requests | Failed |

## Error Responses

Most servers returned the following error:
```
{"error":"server busy, please try again.  maximum pending requests exceeded"}
```

The 116.14.227.16:5271 server returned this error when trying to use command-a:latest:
```
{"error":"model requires more system memory (63.6 GiB) than is available (18.9 GiB)"}
```

## Summary

1. The requested model (command-a:latest) is very large (111.1B parameters) and requires significant memory resources (~64 GiB).
2. Most servers appear to be under heavy load and are rejecting new requests.
3. We were able to successfully test one server with a smaller model (qwen2.5:14b).
4. The successfully tested server showed reasonable first token latency but slower overall response time and throughput.

## Recommendations

1. Retry testing at a time when servers might be under less load
2. Test with smaller models (like llama3.2-vision which is 9.8B parameters)
3. Consider using dedicated or less busy servers for important workloads 