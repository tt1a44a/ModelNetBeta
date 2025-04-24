# H0W 2 USE THE C0MB1NED DATABASE T00LS

## WUT IZ THIS?

These t00ls let u c0mbine the Ollama and LiteLLM databases into 1 database and query it 2 find:
- Open AI endpoints
- M0dels running on them
- Locat10n & 0rganization data
- 0ther 1nf0 useful 4 h4cking

## PREREQS

- Python 3.x
- SQLite3
- Sc4nned databases (ollama.db and litellm.db)

## STEP 1: C0MBINE THE DATABASES

Run the c0mbiner tool:

```
./combine_db.py
```

This will:
- Check if ollama.db and litellm.db exist
- Create a new database called `ai_endpoints.db`
- C0py all server and model data 2 the new DB
- Add server type info (ollama or litellm)
- Sh0w statistics about the c0mbined database

## STEP 2: QUERY THE C0MBINED DATABASE

### BASIC C0MMANDS:

```
# List all servers
./query_combined.py servers

# List all models
./query_combined.py models  

# Search 4 specific model
./query_combined.py search llama

# View server details
./query_combined.py server 1

# Show statistics
./query_combined.py stats
```

### ADVANCED F1LTERING:

#### For servers:
```
# Filter by type
./query_combined.py servers -t ollama

# Filter by country
./query_combined.py servers -c US

# Filter by organization
./query_combined.py servers -o "Digital Ocean"

# Filter by IP
./query_combined.py servers -i "192.168"

# Sort by field (id, ip, port, type, country_code, model_count)
./query_combined.py servers -s model_count -d
```

#### For models:
```
# Filter by name
./query_combined.py models -n llama

# Filter by provider
./query_combined.py models -p mistral

# Filter by parameters
./query_combined.py models -r 7B

# Filter by server type
./query_combined.py models -t litellm

# Filter by country
./query_combined.py models -c DE

# Sort results (name, provider, params)
./query_combined.py models -s params -d
```

## C00L EXAMPLE QUERIES

Find all Ollama servers in United States:
```
./query_combined.py servers -t ollama -c US
```

Find largest models (sorted by parameter size):
```
./query_combined.py models -s params -d
```

Find all Llama models on LiteLLM servers:
```
./query_combined.py models -n llama -t litellm
```

Find all models in Germany:
```
./query_combined.py models -c DE
```

## TR0UBL3SH00TING

If u get error "Combined database not found", make sure:
1. You ran combine_db.py first
2. You're in the right directory
3. The database file hasn't been m0ved or deleted

If ur query returns no results, try:
1. Using less specific filters
2. Making sure the data actually exists in ur database
3. Check that ur filter values match wut's in the DB (case sensitive!)

## SECUR1TY N0TE

This t00l is for research only! Don't use it 4 bad things!
Don't try 2 hack endpoints without permissi0n!
Be responsible or else! 