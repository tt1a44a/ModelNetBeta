<script>
  import { onMount } from 'svelte';
  import { callFunction } from '$lib/api';
  import { addToast } from '$lib/stores/toast';
  import Button from '$lib/components/common/Button.svelte';
  import Input from '$lib/components/common/Input.svelte';
  import Select from '$lib/components/common/Select.svelte';
  import Spinner from '$lib/components/common/Spinner.svelte';
  import Card from '$lib/components/common/Card.svelte';
  import Switch from '$lib/components/common/Switch.svelte';
  import Badge from '$lib/components/common/Badge.svelte';
  import { getModalStore } from '$lib/stores/modal';
  
  // Component state
  let isLoading = false;
  let isAddingEndpoint = false;
  let searchResults = [];
  let filteredResults = [];
  let countries = [];
  let modelFilter = '';
  let countryFilter = '';
  let sortField = 'scan_date';
  let sortDirection = 'desc';
  let currentPage = 1;
  let itemsPerPage = 10;
  let totalPages = 1;
  let endpointDetails = null;
  let showEndpointModal = false;

  // On component mount
  onMount(async () => {
    await Promise.all([
      loadSearchResults(),
      loadCountries()
    ]);
  });

  // Load available countries for filtering
  async function loadCountries() {
    try {
      const response = await callFunction(
        'ollama_scanner',
        {
          action: 'get_countries',
          params: {}
        }
      );
      
      if (response && response.success) {
        countries = response.countries || [];
      } else {
        throw new Error(response?.error || 'Failed to load countries');
      }
    } catch (error) {
      console.error('Error loading countries:', error);
      addToast({
        message: `Error loading countries: ${error.message}`,
        type: 'error'
      });
    }
  }

  // Load search results
  async function loadSearchResults() {
    isLoading = true;
    
    try {
      const response = await callFunction(
        'ollama_scanner',
        {
          action: 'search',
          params: {
            model_filter: modelFilter || undefined,
            country_filter: countryFilter || undefined,
            sort_by: sortField,
            sort_direction: sortDirection,
            limit: 100 // Get enough results to handle pagination client-side
          }
        }
      );
      
      if (response && response.success) {
        searchResults = response.results || [];
        applyFiltersAndPagination();
      } else {
        throw new Error(response?.error || 'Failed to load search results');
      }
    } catch (error) {
      console.error('Error loading search results:', error);
      addToast({
        message: `Error loading search results: ${error.message}`,
        type: 'error'
      });
    } finally {
      isLoading = false;
    }
  }

  // Apply filters and pagination to search results
  function applyFiltersAndPagination() {
    // Apply filters (already applied on server, but we'll keep the logic here for client-side filtering as well)
    filteredResults = [...searchResults];
    
    // Calculate pagination
    totalPages = Math.ceil(filteredResults.length / itemsPerPage);
    if (currentPage > totalPages) {
      currentPage = totalPages > 0 ? totalPages : 1;
    }
    
    // Apply pagination
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    filteredResults = filteredResults.slice(startIndex, endIndex);
  }

  // Handle filter changes
  function handleFilterChange() {
    currentPage = 1;
    loadSearchResults();
  }

  // Handle sort changes
  function handleSortChange(field) {
    if (sortField === field) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortField = field;
      sortDirection = 'asc';
    }
    loadSearchResults();
  }

  // Handle pagination
  function handlePageChange(pageNumber) {
    if (pageNumber >= 1 && pageNumber <= totalPages) {
      currentPage = pageNumber;
      applyFiltersAndPagination();
    }
  }

  // Format scan date
  function formatDate(dateString) {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleString();
  }

  // Open endpoint details modal
  function openEndpointDetails(instance) {
    endpointDetails = {
      name: `Ollama (${instance.ip}:${instance.port})`,
      url: `http://${instance.ip}:${instance.port}`,
      models: instance.models.map(model => model.name).join(', '),
      weight: 1,
      context_length: 4096,
      is_active: true,
      instance: instance
    };
    
    showEndpointModal = true;
  }

  // Close endpoint details modal
  function closeEndpointDetails() {
    showEndpointModal = false;
    endpointDetails = null;
  }

  // Add instance as an endpoint to OpenWebUI
  async function addAsEndpoint() {
    if (!endpointDetails) return;
    
    isAddingEndpoint = true;
    
    try {
      const response = await callFunction(
        'ollama_scanner',
        {
          action: 'add_endpoints',
          params: {
            endpoints: [{
              name: endpointDetails.name,
              url: endpointDetails.url,
              weight: endpointDetails.weight,
              context_length: endpointDetails.context_length,
              is_active: endpointDetails.is_active
            }]
          }
        }
      );
      
      if (response && response.success) {
        addToast({
          message: `Endpoint added successfully: ${endpointDetails.name}`,
          type: 'success'
        });
        closeEndpointDetails();
      } else {
        throw new Error(response?.error || 'Failed to add endpoint');
      }
    } catch (error) {
      console.error('Error adding endpoint:', error);
      addToast({
        message: `Error adding endpoint: ${error.message}`,
        type: 'error'
      });
    } finally {
      isAddingEndpoint = false;
    }
  }

  // Get sort indicator
  function getSortIndicator(field) {
    if (sortField !== field) return '';
    return sortDirection === 'asc' ? '↑' : '↓';
  }
</script>

<div class="search-tab">
  <div class="search-filters">
    <Card>
      <div class="card-content">
        <h2>Search & Filter</h2>
        <p class="description">Browse and filter scanned Ollama instances</p>
        
        <div class="filters-container">
          <div class="filter-group">
            <label for="modelFilter">Model Filter</label>
            <Input 
              id="modelFilter"
              bind:value={modelFilter}
              placeholder="e.g. llama"
              on:change={handleFilterChange}
            />
          </div>
          
          <div class="filter-group">
            <label for="countryFilter">Country</label>
            <Select 
              id="countryFilter"
              bind:value={countryFilter}
              on:change={handleFilterChange}
            >
              <option value="">All Countries</option>
              {#each countries as country}
                <option value={country}>{country}</option>
              {/each}
            </Select>
          </div>
          
          <div class="filter-actions">
            <Button variant="secondary" on:click={() => {
              modelFilter = '';
              countryFilter = '';
              handleFilterChange();
            }}>
              Reset Filters
            </Button>
            
            <Button variant="primary" on:click={handleFilterChange}>
              Apply Filters
            </Button>
          </div>
        </div>
      </div>
    </Card>
  </div>
  
  <div class="search-results">
    <Card>
      <div class="card-content">
        <h2>Results</h2>
        
        {#if isLoading}
          <div class="loading-container">
            <Spinner size="lg" />
            <p>Loading search results...</p>
          </div>
        {:else if searchResults.length === 0}
          <div class="no-results">
            <p>No Ollama instances found.</p>
            <p>Run a scan first to discover Ollama instances.</p>
            <Button 
              variant="secondary" 
              on:click={() => window.dispatchEvent(new CustomEvent('ollamaScannerChangeTab', { detail: 'scan' }))}
            >
              Go to Scanner
            </Button>
          </div>
        {:else}
          <div class="results-table-container">
            <table class="results-table">
              <thead>
                <tr>
                  <th class="sortable" on:click={() => handleSortChange('ip')}>
                    IP Address {getSortIndicator('ip')}
                  </th>
                  <th class="sortable" on:click={() => handleSortChange('port')}>
                    Port {getSortIndicator('port')}
                  </th>
                  <th class="sortable" on:click={() => handleSortChange('country')}>
                    Location {getSortIndicator('country')}
                  </th>
                  <th>Models</th>
                  <th class="sortable" on:click={() => handleSortChange('scan_date')}>
                    Scan Date {getSortIndicator('scan_date')}
                  </th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {#each filteredResults as instance}
                  <tr>
                    <td>{instance.ip}</td>
                    <td>{instance.port}</td>
                    <td>
                      {#if instance.country}
                        {instance.country}
                      {:else}
                        Unknown
                      {/if}
                    </td>
                    <td>
                      <div class="models-list">
                        {#each instance.models.slice(0, 3) as model}
                          <Badge>{model.name}</Badge>
                        {/each}
                        {#if instance.models.length > 3}
                          <Badge>+{instance.models.length - 3} more</Badge>
                        {/if}
                      </div>
                    </td>
                    <td>{formatDate(instance.scan_date)}</td>
                    <td>
                      <Button 
                        variant="link" 
                        size="sm"
                        on:click={() => openEndpointDetails(instance)}
                      >
                        Add as Endpoint
                      </Button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          
          <!-- Pagination -->
          {#if totalPages > 1}
            <div class="pagination">
              <Button 
                variant="outline" 
                size="sm" 
                disabled={currentPage === 1}
                on:click={() => handlePageChange(currentPage - 1)}
              >
                Previous
              </Button>
              
              <span class="page-info">
                Page {currentPage} of {totalPages}
              </span>
              
              <Button 
                variant="outline" 
                size="sm" 
                disabled={currentPage === totalPages}
                on:click={() => handlePageChange(currentPage + 1)}
              >
                Next
              </Button>
            </div>
          {/if}
        {/if}
      </div>
    </Card>
  </div>
  
  <!-- Endpoint Modal -->
  {#if showEndpointModal && endpointDetails}
    <div class="modal-overlay">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Add Ollama Endpoint</h3>
          <button class="close-button" on:click={closeEndpointDetails}>×</button>
        </div>
        
        <div class="modal-body">
          <div class="form-group">
            <label for="endpointName">Endpoint Name</label>
            <Input 
              id="endpointName"
              bind:value={endpointDetails.name}
              placeholder="Endpoint Name"
            />
          </div>
          
          <div class="form-group">
            <label for="endpointUrl">Endpoint URL</label>
            <Input 
              id="endpointUrl"
              bind:value={endpointDetails.url}
              placeholder="http://example.com:11434"
            />
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label for="endpointWeight">Weight</label>
              <Input 
                id="endpointWeight"
                type="number"
                bind:value={endpointDetails.weight}
                min="1"
                max="10"
              />
            </div>
            
            <div class="form-group">
              <label for="contextLength">Context Length</label>
              <Input 
                id="contextLength"
                type="number"
                bind:value={endpointDetails.context_length}
                min="1"
                max="32000"
              />
            </div>
          </div>
          
          <div class="form-group">
            <div class="switch-container">
              <label for="isActive">Active</label>
              <Switch
                id="isActive"
                bind:checked={endpointDetails.is_active}
              />
            </div>
          </div>
          
          <div class="instance-details">
            <h4>Available Models</h4>
            <div class="models-grid">
              {#each endpointDetails.instance.models as model}
                <div class="model-card">
                  <div class="model-name">{model.name}</div>
                  <div class="model-details">
                    <span class="model-size">{(model.size / (1024 * 1024 * 1024)).toFixed(1)} GB</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          <Button variant="outline" on:click={closeEndpointDetails}>
            Cancel
          </Button>
          
          <Button 
            variant="primary" 
            on:click={addAsEndpoint}
            disabled={isAddingEndpoint}
          >
            {#if isAddingEndpoint}
              <Spinner size="sm" /> Adding...
            {:else}
              Add Endpoint
            {/if}
          </Button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .search-tab {
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
    margin-bottom: 0.75rem;
  }
  
  .description {
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
  }
  
  .filters-container {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: flex-end;
  }
  
  .filter-group {
    flex: 1;
    min-width: 200px;
  }
  
  .filter-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1.5rem;
  }
  
  label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
  }
  
  .loading-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 0;
    gap: 1rem;
    color: var(--text-secondary);
  }
  
  .no-results {
    text-align: center;
    padding: 3rem 0;
    color: var(--text-secondary);
  }
  
  .results-table-container {
    overflow-x: auto;
    margin-bottom: 1rem;
  }
  
  .results-table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
  }
  
  .results-table th {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    font-weight: 600;
  }
  
  .results-table th.sortable {
    cursor: pointer;
  }
  
  .results-table th.sortable:hover {
    background-color: var(--background-secondary);
  }
  
  .results-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  .results-table tr:hover {
    background-color: var(--background-secondary);
  }
  
  .models-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }
  
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 1rem;
    margin-top: 1.5rem;
  }
  
  .page-info {
    font-size: 0.9rem;
    color: var(--text-secondary);
  }
  
  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
  }
  
  .modal-content {
    background-color: var(--background-primary);
    border-radius: 0.5rem;
    max-width: 600px;
    width: 90%;
    max-height: 90vh;
    overflow-y: auto;
  }
  
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }
  
  .close-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-secondary);
  }
  
  .modal-body {
    padding: 1.5rem;
  }
  
  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1rem 1.5rem;
    border-top: 1px solid var(--border-color);
  }
  
  .form-group {
    margin-bottom: 1rem;
  }
  
  .form-row {
    display: flex;
    gap: 1rem;
  }
  
  .form-row .form-group {
    flex: 1;
  }
  
  .switch-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .instance-details {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-color);
  }
  
  .models-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.75rem;
  }
  
  .model-card {
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    padding: 0.75rem;
  }
  
  .model-name {
    font-weight: 500;
    margin-bottom: 0.25rem;
  }
  
  .model-details {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
</style> 