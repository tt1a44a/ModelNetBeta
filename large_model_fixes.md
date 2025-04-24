# Large Model Timeout Fixes

## Issue Identified

After testing, we've identified that the timeout issue with the Discord bot occurs specifically with large models like `deepseek-r1:70b`. Our investigation shows:

1. The endpoint itself (99.178.157.123:11434) is responsive and working correctly
2. The `/api/tags` endpoint responds quickly (0.5s) showing the models available
3. The `/api/generate` endpoint processes requests but large models (70B) take longer than the bot's timeout
4. Smaller models (e.g., deepseek-r1:7b) respond within a reasonable time frame

## Applied Fix

We've implemented a fix that adjusts the timeout calculation in the Discord bot:

1. Increased the maximum dynamic timeout from 900s (15min) to 1500s (25min)
2. Added special handling for very large models (50B+) with larger timeout multipliers
3. The changes were applied to `DiscordBot/discord_bot.py` (with a backup created)

## Recommendations for Using Large Models

When using large models like deepseek-r1:70b through the Discord bot:

1. **Use smaller prompts**: Keep your prompts short and specific
2. **Limit max_tokens**: Set max_tokens to 100-200 for faster responses
3. **Try smaller models first**: For tasks that don't need the full 70B model, try using:
   - deepseek-r1:14b
   - deepseek-r1:7b
   - Other smaller models that respond more quickly

4. **For streaming responses**: Enable streaming for faster initial responses:
   ```
   /chat model_id:XXX prompt:"Your prompt" max_tokens:200 system_prompt:"" temperature:0.7
   ```

5. **Bot-specific parameters**: The bot now calculates timeouts dynamically based on:
   - Model size (e.g., 7B, 14B, 70B)
   - Prompt length
   - Max tokens requested

## Testing Your Changes

You can test if the bot is working correctly with large models:

1. **Simple API test**:
   ```bash
   curl -s "http://99.178.157.123:11434/api/tags" | grep deepseek
   ```

2. **Generation test** (with smaller model):
   ```bash
   curl -s -X POST "http://99.178.157.123:11434/api/generate" \
     -H "Content-Type: application/json" \
     -d '{"model":"deepseek-r1:7b","prompt":"Hi","stream":false}'
   ```

3. **Discord bot command**:
   ```
   /quickprompt model_name:deepseek-r1:7b prompt:"Say hello" max_tokens:100
   ```

## Troubleshooting

If you still experience timeouts after applying these fixes:

1. Check server load - the model may be busy with other requests
2. Verify network connectivity between the bot and the Ollama server
3. Check the Discord bot logs for any error messages
4. Try restarting the Discord bot service
5. Consider further increasing the timeout limits if needed

Remember that large models like deepseek-r1:70b require significant computational resources and will naturally respond more slowly than smaller models. 