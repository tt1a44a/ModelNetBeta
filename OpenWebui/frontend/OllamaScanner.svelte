<script>
  import { onMount } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import { callFunction } from '$lib/api';
  import { addToast } from '$lib/stores/toast';
  import Spinner from '$lib/components/common/Spinner.svelte';
  import Button from '$lib/components/common/Button.svelte';
  import Input from '$lib/components/common/Input.svelte';
  import ScannerTab from './ScannerTab.svelte';
  import SearchTab from './SearchTab.svelte';
  import DashboardTab from './DashboardTab.svelte';
  
  // Component state
  let activeTab = 'dashboard';
  let isLoading = false;
  let stats = null;
  
  // Function to load dashboard stats
  async function loadStats() {
    isLoading = true;
    try {
      const response = await callFunction(
        'ollama_scanner', 
        { 
          action: 'get_stats',
          params: {}
        }
      );
      
      if (response && response.success) {
        stats = response;
      } else {
        throw new Error(response?.error || 'Failed to load stats');
      }
    } catch (error) {
      addToast({
        message: `Error loading statistics: ${error.message}`,
        type: 'error'
      });
      console.error('Error loading stats:', error);
    } finally {
      isLoading = false;
    }
  }
  
  // On component mount
  onMount(() => {
    loadStats();
  });
  
  // Tabs configuration
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: 'chart-pie' },
    { id: 'scan', label: 'Scan', icon: 'search' },
    { id: 'search', label: 'Search Results', icon: 'list' }
  ];
  
  // Handle tab change
  function changeTab(tabId) {
    activeTab = tabId;
    
    // Refresh data when switching to dashboard
    if (tabId === 'dashboard') {
      loadStats();
    }
  }
</script>

<div class="ollama-scanner-container">
  <header>
    <h1>Ollama Scanner</h1>
    <p class="description">
      Discover, search, and add Ollama instances to your OpenWebUI configuration
    </p>
  </header>
  
  <div class="tab-navigation">
    {#each tabs as tab}
      <button 
        class="tab-button {activeTab === tab.id ? 'active' : ''}"
        on:click={() => changeTab(tab.id)}
      >
        <i class="fas fa-{tab.icon}"></i>
        <span>{tab.label}</span>
      </button>
    {/each}
  </div>
  
  <div class="tab-content">
    {#if activeTab === 'dashboard'}
      <div class="tab-panel" transition:fade={{ duration: 150 }}>
        {#if isLoading}
          <div class="loading-container">
            <Spinner size="lg" />
            <p>Loading dashboard data...</p>
          </div>
        {:else if stats}
          <DashboardTab {stats} onRefresh={loadStats} />
        {:else}
          <div class="empty-state">
            <p>No scanner data found. Start by running a scan.</p>
            <Button 
              variant="primary" 
              on:click={() => changeTab('scan')}
            >
              Go to Scanner
            </Button>
          </div>
        {/if}
      </div>
    {:else if activeTab === 'scan'}
      <div class="tab-panel" transition:fade={{ duration: 150 }}>
        <ScannerTab onScanComplete={loadStats} />
      </div>
    {:else if activeTab === 'search'}
      <div class="tab-panel" transition:fade={{ duration: 150 }}>
        <SearchTab />
      </div>
    {/if}
  </div>
</div>

<style>
  .ollama-scanner-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
    color: var(--text-primary);
  }
  
  header {
    padding: 1.5rem 0;
    margin-bottom: 1rem;
  }
  
  h1 {
    font-size: 1.75rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  
  .description {
    font-size: 1rem;
    color: var(--text-secondary);
  }
  
  .tab-navigation {
    display: flex;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1rem;
  }
  
  .tab-button {
    padding: 0.75rem 1.25rem;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-secondary);
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .tab-button:hover {
    color: var(--text-primary);
    background-color: var(--bg-hover);
  }
  
  .tab-button.active {
    color: var(--primary);
    border-bottom: 2px solid var(--primary);
  }
  
  .tab-content {
    flex: 1;
    overflow: auto;
  }
  
  .tab-panel {
    height: 100%;
  }
  
  .loading-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    gap: 1rem;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    gap: 1rem;
    text-align: center;
  }
</style> 