<script>
  import { onMount } from 'svelte';
  import { callFunction } from '$lib/api';
  import { addToast } from '$lib/stores/toast';
  import Button from '$lib/components/common/Button.svelte';
  import Input from '$lib/components/common/Input.svelte';
  import Spinner from '$lib/components/common/Spinner.svelte';
  import Card from '$lib/components/common/Card.svelte';
  
  // Props
  export let onScanComplete = () => {};

  // Component state
  let isScanning = false;
  let scanProgress = { current: 0, total: 0, percent: 0 };
  let scanResults = null;
  let shodanApiKey = '';
  let searchQuery = 'product:Ollama';
  let maxResults = 100;
  let timeout = 5;
  let portsToTry = '11434,8000,8001';
  let advancedOptionsVisible = false;

  // On component mount
  onMount(async () => {
    // Try to load saved settings from localStorage
    try {
      const savedSettings = localStorage.getItem('ollama_scanner_settings');
      if (savedSettings) {
        const settings = JSON.parse(savedSettings);
        shodanApiKey = settings.shodanApiKey || '';
        searchQuery = settings.searchQuery || 'product:Ollama';
        maxResults = settings.maxResults || 100;
        timeout = settings.timeout || 5;
        portsToTry = settings.portsToTry || '11434,8000,8001';
      }
    } catch (error) {
      console.error('Error loading saved settings:', error);
    }
  });

  // Save settings to localStorage
  function saveSettings() {
    try {
      localStorage.setItem('ollama_scanner_settings', JSON.stringify({
        shodanApiKey,
        searchQuery,
        maxResults,
        timeout,
        portsToTry
      }));
    } catch (error) {
      console.error('Error saving settings:', error);
    }
  }

  // Start scanning
  async function startScan() {
    if (!shodanApiKey) {
      addToast({
        message: 'Please enter a Shodan API key',
        type: 'error'
      });
      return;
    }

    isScanning = true;
    scanResults = null;
    scanProgress = { current: 0, total: 0, percent: 0 };
    saveSettings();

    try {
      // Parse ports
      const ports = portsToTry.split(',')
        .map(port => parseInt(port.trim()))
        .filter(port => !isNaN(port));

      // Call the backend function
      const response = await callFunction(
        'ollama_scanner',
        {
          action: 'scan',
          params: {
            api_key: shodanApiKey,
            search_query: searchQuery,
            max_results: maxResults,
            timeout: timeout,
            ports_to_try: ports
          }
        }
      );

      if (response && response.success) {
        scanResults = response;
        addToast({
          message: `Scan complete. Found ${response.valid_count} valid Ollama instances.`,
          type: 'success'
        });
        onScanComplete();
      } else {
        throw new Error(response?.error || 'Scan failed');
      }
    } catch (error) {
      addToast({
        message: `Scan failed: ${error.message}`,
        type: 'error'
      });
      console.error('Scan error:', error);
    } finally {
      isScanning = false;
    }
  }

  // Toggle advanced options
  function toggleAdvancedOptions() {
    advancedOptionsVisible = !advancedOptionsVisible;
  }
</script>

<div class="scanner-tab">
  <div class="scan-form">
    <Card>
      <div class="card-content">
        <h2>Scan Configuration</h2>
        <p class="description">Configure and run a scan to discover Ollama instances</p>
        
        <div class="form-group">
          <label for="shodanApiKey">Shodan API Key <span class="required">*</span></label>
          <Input 
            id="shodanApiKey"
            bind:value={shodanApiKey}
            placeholder="Enter your Shodan API key"
            type="password"
            disabled={isScanning}
          />
          <small>
            <a href="https://account.shodan.io/" target="_blank" rel="noopener noreferrer">
              Get a Shodan API key
            </a>
          </small>
        </div>
        
        <div class="form-actions">
          <Button 
            variant="link" 
            on:click={toggleAdvancedOptions}
            class="toggle-button"
          >
            {advancedOptionsVisible ? 'Hide' : 'Show'} Advanced Options
          </Button>
          
          <Button 
            variant="primary" 
            on:click={startScan}
            disabled={isScanning || !shodanApiKey}
          >
            {#if isScanning}
              <Spinner size="sm" /> Scanning...
            {:else}
              Start Scan
            {/if}
          </Button>
        </div>
        
        {#if advancedOptionsVisible}
          <div class="advanced-options" transition:slide={{ duration: 300 }}>
            <div class="form-group">
              <label for="searchQuery">Search Query</label>
              <Input 
                id="searchQuery"
                bind:value={searchQuery}
                placeholder="product:Ollama"
                disabled={isScanning}
              />
              <small>Shodan search query for finding Ollama instances</small>
            </div>
            
            <div class="form-row">
              <div class="form-group">
                <label for="maxResults">Max Results</label>
                <Input 
                  id="maxResults"
                  type="number"
                  bind:value={maxResults}
                  min="1"
                  max="1000"
                  disabled={isScanning}
                />
              </div>
              
              <div class="form-group">
                <label for="timeout">Timeout (seconds)</label>
                <Input 
                  id="timeout"
                  type="number"
                  bind:value={timeout}
                  min="1"
                  max="60"
                  disabled={isScanning}
                />
              </div>
            </div>
            
            <div class="form-group">
              <label for="portsToTry">Ports to Try</label>
              <Input 
                id="portsToTry"
                bind:value={portsToTry}
                placeholder="11434,8000,8001"
                disabled={isScanning}
              />
              <small>Comma-separated list of ports to check for each IP</small>
            </div>
          </div>
        {/if}
      </div>
    </Card>
  </div>
  
  {#if isScanning}
    <div class="scan-progress">
      <Card>
        <div class="card-content">
          <h3>Scan in Progress</h3>
          <Spinner size="lg" />
          <p>Scanning for Ollama instances, please wait...</p>
        </div>
      </Card>
    </div>
  {:else if scanResults}
    <div class="scan-results">
      <Card>
        <div class="card-content">
          <h3>Scan Results</h3>
          <div class="results-summary">
            <div class="summary-item">
              <div class="summary-value">{scanResults.valid_count}</div>
              <div class="summary-label">Valid Instances</div>
            </div>
            <div class="summary-item">
              <div class="summary-value">{scanResults.total_count}</div>
              <div class="summary-label">Total Scanned</div>
            </div>
            <div class="summary-item">
              <div class="summary-value">{scanResults.error_count}</div>
              <div class="summary-label">Errors</div>
            </div>
          </div>
          
          {#if scanResults.valid_count > 0}
            <div class="results-list">
              <h4>Valid Instances</h4>
              <p class="help-text">
                These Ollama instances are accessible and running. 
                View details and add them as endpoints in the Search tab.
              </p>
              <Button 
                variant="secondary" 
                on:click={() => window.dispatchEvent(new CustomEvent('ollamaScannerChangeTab', { detail: 'search' }))}
              >
                Go to Search Results
              </Button>
            </div>
          {:else}
            <div class="no-results">
              <p>No valid Ollama instances found.</p>
              <p>Try adjusting your search parameters and running the scan again.</p>
            </div>
          {/if}
        </div>
      </Card>
    </div>
  {/if}
</div>

<style>
  .scanner-tab {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding-bottom: 2rem;
  }
  
  .card-content {
    padding: 1.5rem;
  }
  
  h2 {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  
  h3 {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 1rem;
  }
  
  h4 {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  
  .description {
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
  }
  
  .form-group {
    margin-bottom: 1.25rem;
  }
  
  .form-row {
    display: flex;
    gap: 1rem;
  }
  
  .form-row .form-group {
    flex: 1;
  }
  
  label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
  }
  
  small {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
  
  .required {
    color: var(--error);
  }
  
  .form-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .toggle-button {
    font-size: 0.9rem;
  }
  
  .advanced-options {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }
  
  .scan-progress {
    text-align: center;
  }
  
  .results-summary {
    display: flex;
    justify-content: space-around;
    margin: 1.5rem 0;
  }
  
  .summary-item {
    text-align: center;
    padding: 1rem;
  }
  
  .summary-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary);
  }
  
  .summary-label {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
  }
  
  .results-list {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-color);
  }
  
  .help-text {
    margin-bottom: 1rem;
    color: var(--text-secondary);
  }
  
  .no-results {
    text-align: center;
    padding: 2rem 0;
    color: var(--text-secondary);
  }
</style> 