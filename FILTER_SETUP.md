# Setting Up Ollama Scanner as a Filter Function

This guide will walk you through the process of setting up and enabling the Ollama Scanner Filter Function in OpenWebUI after installation.

## Step 1: Install the Filter

First, run the installation script to copy the filter files to your OpenWebUI container:

```bash
./install_filter.sh open-webui
```

Replace `open-webui` with the name of your OpenWebUI container if different.

## Step 2: Restart the Container

Restart your OpenWebUI container to apply the changes:

```bash
docker restart open-webui
```

## Step 3: Access OpenWebUI Functions

Once OpenWebUI has restarted:

1. Log in to your OpenWebUI interface
2. Navigate to **Workspace** in the sidebar
3. Click on **Functions**

![Navigate to Functions](https://i.imgur.com/example1.png)

## Step 4: Find the Ollama Scanner Filter

In the Functions page, you should see a list of available functions, including the newly installed Ollama Scanner filter.

![Find Ollama Scanner Filter](https://i.imgur.com/example2.png)

## Step 5: Enable the Filter

Enable the filter by clicking the toggle switch next to "Ollama Scanner".

![Enable the Filter](https://i.imgur.com/example3.png)

## Step 6: Configure Filter Settings (Optional)

To configure the filter settings:

1. Click on the **Settings** icon (gear symbol) next to the Ollama Scanner filter
2. Adjust the **System Valves** as needed:
   - `SHODAN_API_KEY`: Your Shodan API key
   - `MAX_RESULTS`: Maximum number of results to return (default: 100)
   - `SEARCH_QUERY`: Default Shodan search query (default: "product:Ollama")
   - `REQUEST_TIMEOUT`: Timeout for requests in seconds (default: 5)

![Configure Filter Settings](https://i.imgur.com/example4.png)

## Step 7: Make the Filter Global (Optional)

If you want the filter to be applied to all models:

1. Click on the **More Options** menu (three dots)
2. Select **Global**

This will enable the filter for all conversations across all models.

![Make Filter Global](https://i.imgur.com/example5.png)

## Step 8: Testing the Filter

Test the filter by starting a new chat and asking about Ollama Scanner:

Example prompts:
- "How can I use Ollama Scanner to find instances?"
- "Tell me about discovering Ollama instances"
- "What is Ollama Scanner used for?"

The filter should enhance the model's response with information about accessing the Ollama Scanner feature.

![Testing the Filter](https://i.imgur.com/example6.png)

## Step 9: Accessing the Admin Interface

The administrative interface for Ollama Scanner can be accessed at:

```
http://your-openwebui-url/admin/ollama-scanner
```

This interface allows you to:
- Scan for Ollama instances using Shodan
- Search and filter discovered instances
- Add instances as endpoints in OpenWebUI
- View statistics about discovered instances

## Troubleshooting

If you encounter issues:

1. **Filter not appearing in Functions list:**
   - Check that the installation script completed successfully
   - Verify that the filter files are in the correct location in the container
   - Make sure you've restarted the container

2. **Filter enabled but not working:**
   - Check that the required dependencies (shodan, requests) are installed
   - Verify that the filter is enabled and/or set to global
   - Try restarting the OpenWebUI container again

3. **Admin interface not accessible:**
   - The Filter function only adds context to conversations
   - For the full scanner interface, you'll need to also install the UI components

For further assistance, please open an issue on the GitHub repository. 