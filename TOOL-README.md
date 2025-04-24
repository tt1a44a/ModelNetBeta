# Ollama Scanner

use these commands to scan for open ollama servers and look at the results

## How to Use

Run the scanner:
```
./run.sh
```

Or just:
```
python ollama_scanner.py
```

## Query Commands

Use the query tool to search the database:

### List Servers
```
./query_models.py servers
```
options:
- --sort models|ip|date
- --desc

### List All models
```
./query_models.py models
```
options:
- --sort name|params|quant|count
- --desc

### Models with servers
```
./query_models.py models-servers
```
options:
- --sort name|params|quant|size|ip
- --desc

### Search for a model
```
./query_models.py search llama
```
options:
- --sort name|params|quant|size
- --desc

### Find models by parameter size
```
./query_models.py params 7B
```
options:
- --sort name|params|quant|size
- --desc

### Look at a server
```
./query_models.py server 192.168.1.1
```
options:
- --port 11434
- --sort name|params|quant|size
- --desc

### Fix duplicates
```
./query_models.py prune
```
removes duplicate entries from database 