# Dynamic Timeout Features for Ollama Scanner

## Overview

We've implemented enhanced timeout handling for API requests in the ollama_scanner tools. These enhancements address the timeout issues when using large models like deepseek-r1:70b.

The main improvements are:

1. **Dynamic timeout calculation** based on model size, prompt length, and max tokens
2. **Timeout flag** that allows specifying a custom timeout or disabling timeouts entirely
3. **Special handling for large models** (50B+) which naturally take longer to respond

## How to Use

### 1. Dynamic Timeout (Default)

When you run the command without specifying a timeout, it will automatically calculate an appropriate timeout based on:

- Model size (e.g., 7B, 14B, 70B)
- Prompt length (longer prompts need more time)
- Maximum tokens to generate (more tokens need more time)

```bash
python ollama_scanner.py [other args]
```

### 2. Manual Timeout

You can specify an exact timeout in seconds:

```bash
python ollama_scanner.py --timeout 300 [other args]
```

### 3. No Timeout

To disable timeouts completely (wait indefinitely for a response):

```bash
python ollama_scanner.py --timeout 0 [other args]
```

## Technical Details

### Dynamic Timeout Calculation

The dynamic timeout is calculated using the following formula:

```
final_timeout = base_timeout * model_factor * prompt_factor * token_factor
```

Where:
- `base_timeout` = 180 seconds (3 minutes)
- `model_factor` is based on model size:
  - 70B models: 6.0x
  - 13-14B models: 2.4x
  - 7-8B models: 1.7x
  - Other sizes: 1.0 + (size_in_billions / 10)
- `prompt_factor` = 1.0 + (prompt_length / 1000)
- `token_factor` = max(1.0, max_tokens / 1000)

The final timeout is capped between 60 seconds (minimum) and 1800 seconds (maximum).

### Files Modified

The following files have been updated with enhanced timeout handling:

- `ollama_scanner.py`
- `DiscordBot/ollama_scanner.py`
- `OpenWebui/backend/ollama_scanner_function.py`
- `ollama_scanner_function_filter.py`

All files have backups created before modifications.

## Testing Results

We've conducted extensive testing with different model sizes:

### Small Model (deepseek-r1:7b)
- Responds quickly (typically 5-20 seconds)
- Works well with default dynamic timeout

### Large Model (deepseek-r1:70b)
- Takes significantly longer to respond (60-120+ seconds)
- May timeout with standard settings
- Works well with:
  - Dynamic timeout calculation (which assigns longer timeouts)
  - Manual timeout of 300+ seconds
  - No timeout (timeout=0)

## Best Practices

For optimal use of large models:

1. **Keep prompts short** - Shorter prompts generate faster responses
2. **Limit max tokens** - Set to the minimum needed (50-100 tokens if possible)
3. **Consider smaller models** - For tasks that don't require the 70B model's capabilities
4. **Use appropriate timeouts**:
   - 60-120 seconds for 7B models
   - 120-300 seconds for 14B models
   - 300-900 seconds for 70B models (or use timeout=0)

## Troubleshooting

If you still experience timeout issues:

1. **Verify the model exists** - Check that the requested model is available on the endpoint
2. **Check server load** - The server may be busy with other requests
3. **Increase timeout** - Try a higher manual timeout or use timeout=0
4. **Reduce request size** - Use shorter prompts and fewer max tokens
5. **Check logs** - Look for any error messages in the logs

## Example Commands

```bash
# Using a small model with dynamic timeout
python ollama_scanner.py --model "deepseek-r1:7b" [other args]

# Using a large model with 5-minute timeout
python ollama_scanner.py --model "deepseek-r1:70b" --timeout 300 [other args]

# Using a large model with no timeout
python ollama_scanner.py --model "deepseek-r1:70b" --timeout 0 [other args]
``` 