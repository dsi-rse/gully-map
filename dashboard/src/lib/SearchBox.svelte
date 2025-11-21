<script lang="ts">
  /**
   * Search input for jumping to known Sonoma County places using fuzzy matching.
   */
  import { onMount } from "svelte";
  import { Input } from "@smui/textfield";
  import List, { Item, Text } from "@smui/list";
  import Menu from "@smui/menu";
  import Fuse from "fuse.js";

  import places from "../data/sonoma-county-places.json";

  type PlaceRecord = { name: string; coords: [number, number] };
  type SearchResult = { name: string; center: [number, number]; zoom: number };
  type ListComponent = { getElement: () => HTMLElement };

  const MAX_SEARCH_RESULTS = 10;
  const DEFAULT_ZOOM = 15;
  const ENTER_KEY = "Enter";
  const TAB_KEY = "Tab";

  const fuse = new Fuse<SearchResult>(
    (places as PlaceRecord[]).map((place) => ({
      name: place.name,
      center: place.coords,
      zoom: DEFAULT_ZOOM,
    })),
    { keys: ["name"], threshold: 0.2 },
  );

  export let onSelect: (result: SearchResult) => void = () => {};

  let query = "";
  let results: SearchResult[] = [];
  let noResultsFound = false;
  let menuVisible = false;

  let searchBox: HTMLDivElement | null = null;
  let resultsList: ListComponent | null = null;

  let bodyClickHandler: ((event: MouseEvent) => void) | null = null;

  onMount(() => {
    bodyClickHandler = (event: MouseEvent) => handleOutsideClick(event);
    document.body.addEventListener("click", bodyClickHandler);

    return () => {
      if (bodyClickHandler) {
        document.body.removeEventListener("click", bodyClickHandler);
      }
    };
  });

  /**
   * Close the results list when the user clicks outside the search box.
   * @param event Browser click event to inspect.
   */
  function handleOutsideClick(event: MouseEvent): void {
    const clickedOutside = searchBox && !searchBox.contains(event.target as Node);
    if (menuVisible && clickedOutside) {
      hideResultsMenu();
    }
    noResultsFound = false;
  }

  /**
   * Refresh search results as the user types.
   * @param event Input event from the search field.
   */
  function handleInput(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    query = target?.value ?? "";
    results = performSearch(query);
    menuVisible = results.length > 0;
    noResultsFound = false;
  }

  /**
   * Handle keyboard actions for submitting or navigating search results.
   * @param event Keyboard event fired on the search field.
   */
  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === ENTER_KEY) {
      const [bestMatch] = performSearch(query, 1);
      if (bestMatch) {
        selectResult(bestMatch);
      }
      else {
        results = [];
        noResultsFound = true;
        menuVisible = true;
      }
      return;
    }

    if (event.key === TAB_KEY) {
      focusFirstResult(event);
    }
  }

  /**
   * Move focus to the first search result when tab is pressed.
   * @param event Keyboard event to prevent default tabbing.
   */
  function focusFirstResult(event: KeyboardEvent): void {
    if (!menuVisible || !resultsList) {
      return;
    }
    event.preventDefault();
    const firstItem = resultsList.getElement().querySelector<HTMLElement>('[tabindex="0"]');
    firstItem?.focus();
  }

  /**
   * Run a fuzzy search over Sonoma County places.
   * @param term Query string entered by the user.
   * @param limit Maximum number of results to return.
   * @returns Matching place names with map coordinates.
   */
  function performSearch(term: string, limit = MAX_SEARCH_RESULTS): SearchResult[] {
    if (!term.trim()) {
      return [];
    }
    return fuse.search(term, { limit }).map((result) => result.item);
  }

  /**
   * Apply the selected search result and notify listeners.
   * @param result Selected place record.
   */
  function selectResult(result: SearchResult): void {
    query = result.name;
    onSelect(result);
    hideResultsMenu();
  }

  /**
   * Hide the search results dropdown.
   */
  function hideResultsMenu(): void {
    menuVisible = false;
  }
</script>

<div bind:this={searchBox} class="search-box">
  <Input
    bind:value={query}
    oninput={handleInput}
    onkeydown={handleKeyDown}
    placeholder="Search..."
  />
  <Menu class="search-results" style={menuVisible ? "" : "display: none;"}>
    {#if results.length !== 0}
      <List bind:this={resultsList}>
        {#each results as result (result.name)}
          <Item tabindex={0} onSMUIAction={() => { selectResult(result); }}>
            <Text>{result.name}</Text>
          </Item>
        {/each}
      </List>
    {:else if noResultsFound}
      <Item><Text style="color: #808080;">(no results found)</Text></Item>
    {/if}
  </Menu>
</div>
