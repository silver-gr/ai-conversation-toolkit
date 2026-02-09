import { App } from 'obsidian';
import type ConversationIndex from '../index/ConversationIndex';
import type { TabComponent, SearchResult, BrowseFilters } from '../types';
import { PLATFORM_COLORS, SEARCH_DEBOUNCE_MS } from '../constants';

/**
 * SearchView implements cross-conversation full-text search as a sidebar tab.
 *
 * It provides a debounced search input, source scope filters, indexing progress
 * display, and a paginated results list with score visualization.
 */
export class SearchView implements TabComponent {
  containerEl: HTMLElement;
  private index: ConversationIndex;
  private app: App;
  private searchInput: HTMLInputElement | null = null;
  private resultsContainer: HTMLElement | null = null;
  private progressEl: HTMLElement | null = null;
  private currentResults: SearchResult[] = [];
  private displayedCount: number = 50;
  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private progressCallback: (() => void) | null = null;
  private readyCallback: (() => void) | null = null;

  /** Currently active source scope filters */
  private activeScopes: ('claude' | 'chatgpt' | 'gemini')[] = [];

  constructor(containerEl: HTMLElement, index: ConversationIndex, app: App) {
    this.containerEl = containerEl;
    this.index = index;
    this.app = app;
  }

  render(): void {
    this.containerEl.empty();
    this.containerEl.addClass('search-tab-root');

    // Build UI sections
    this.renderInputArea();
    this.renderResultsContainer();

    // Register index event listeners
    this.progressCallback = () => this.updateProgress();
    this.readyCallback = () => {
      this.updateProgress();
      this.onIndexReady();
    };

    this.index.on('index-progress', this.progressCallback);
    this.index.on('index-ready', this.readyCallback);

    // Initial progress display
    this.updateProgress();

    // Show initial empty state
    this.renderEmptyState();
  }

  destroy(): void {
    // Clear debounce timer
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }

    // Unregister index event listeners
    if (this.progressCallback) {
      this.index.off('index-progress', this.progressCallback);
      this.progressCallback = null;
    }
    if (this.readyCallback) {
      this.index.off('index-ready', this.readyCallback);
      this.readyCallback = null;
    }

    // Clear references
    this.searchInput = null;
    this.resultsContainer = null;
    this.progressEl = null;
    this.currentResults = [];

    // Clear DOM
    this.containerEl.empty();
  }

  onIndexReady(): void {
    // Re-run current search if there is a query
    if (this.searchInput && this.searchInput.value.trim()) {
      this.executeSearch(this.searchInput.value.trim());
    }
  }

  // ─── Input Area ──────────────────────────────────────────────────────────

  private renderInputArea(): void {
    const inputContainer = this.containerEl.createDiv({ cls: 'search-input-container' });

    // Input wrapper (for relative positioning of clear button)
    const inputWrapper = inputContainer.createDiv({ cls: 'search-input-wrapper' });

    // Search input
    this.searchInput = inputWrapper.createEl('input', {
      cls: 'search-input',
      attr: {
        type: 'text',
        placeholder: 'Search across all conversations...',
        spellcheck: 'false',
      },
    });

    // Clear button
    const clearBtn = inputWrapper.createDiv({ cls: 'search-clear-btn' });
    clearBtn.textContent = '\u00d7';
    clearBtn.style.display = 'none';

    // Input event: debounced search
    this.searchInput.addEventListener('input', () => {
      const query = this.searchInput!.value.trim();
      clearBtn.style.display = query ? 'block' : 'none';

      if (this.debounceTimer !== null) {
        clearTimeout(this.debounceTimer);
      }

      this.debounceTimer = setTimeout(() => {
        if (query) {
          this.executeSearch(query);
        } else {
          this.currentResults = [];
          this.renderEmptyState();
        }
      }, SEARCH_DEBOUNCE_MS);
    });

    // Clear button click
    clearBtn.addEventListener('click', () => {
      if (this.searchInput) {
        this.searchInput.value = '';
        clearBtn.style.display = 'none';
        this.currentResults = [];
        this.renderEmptyState();
        // Defer focus to next tick so DOM changes don't steal it
        const input = this.searchInput;
        setTimeout(() => input.focus(), 0);
      }
    });

    // Scope filter row
    this.renderScopeRow(inputContainer);

    // Progress indicator
    this.progressEl = inputContainer.createDiv({ cls: 'search-progress' });
  }

  private renderScopeRow(parent: HTMLElement): void {
    const scopeRow = parent.createDiv({ cls: 'search-scope-row' });

    const scopes: { label: string; value: 'claude' | 'chatgpt' | 'gemini' | 'all' }[] = [
      { label: 'All', value: 'all' },
      { label: 'Claude', value: 'claude' },
      { label: 'ChatGPT', value: 'chatgpt' },
      { label: 'Gemini', value: 'gemini' },
    ];

    let allBtnRef: HTMLElement | null = null;

    for (const scope of scopes) {
      const btn = scopeRow.createDiv({ cls: 'search-scope-btn' });
      btn.textContent = scope.label;

      // "All" is active by default
      if (scope.value === 'all') {
        btn.addClass('active');
        allBtnRef = btn;
      }

      btn.addEventListener('click', () => {
        if (scope.value === 'all') {
          // Clear all specific scope filters
          this.activeScopes = [];
          // Update button states
          scopeRow.querySelectorAll('.search-scope-btn').forEach((el) => {
            el.removeClass('active');
          });
          btn.addClass('active');
        } else {
          // Toggle this specific scope
          if (allBtnRef) allBtnRef.removeClass('active');

          const idx = this.activeScopes.indexOf(scope.value);
          if (idx >= 0) {
            this.activeScopes.splice(idx, 1);
            btn.removeClass('active');
          } else {
            this.activeScopes.push(scope.value);
            btn.addClass('active');
          }

          // If no scopes selected, revert to "All"
          if (this.activeScopes.length === 0) {
            if (allBtnRef) allBtnRef.addClass('active');
          }
        }

        // Re-run search with updated scope
        if (this.searchInput && this.searchInput.value.trim()) {
          this.executeSearch(this.searchInput.value.trim());
        }
      });
    }
  }

  // ─── Progress ────────────────────────────────────────────────────────────

  private updateProgress(): void {
    if (!this.progressEl) return;

    this.progressEl.empty();

    const dot = this.progressEl.createSpan({ cls: 'search-progress-dot' });
    const label = this.progressEl.createSpan();

    if (this.index.isIndexReady()) {
      dot.addClass('ready');
      label.textContent = 'Ready';
    } else {
      dot.addClass('indexing');
      const progress = this.index.getIndexProgress();
      label.textContent = `Indexing: ${progress.indexed}/${progress.total}`;
    }
  }

  // ─── Results ─────────────────────────────────────────────────────────────

  private renderResultsContainer(): void {
    this.resultsContainer = this.containerEl.createDiv({ cls: 'search-results' });
  }

  private executeSearch(query: string): void {
    if (!this.index.isIndexReady()) {
      if (this.resultsContainer) {
        this.resultsContainer.empty();
        const notice = this.resultsContainer.createDiv({ cls: 'search-empty-state' });
        notice.textContent = 'Search index is still building\u2026 Results will appear when ready.';
      }
      return;
    }

    const filters: Partial<BrowseFilters> = {};
    if (this.activeScopes.length > 0) {
      filters.sources = [...this.activeScopes];
    }

    this.currentResults = this.index.search(query, filters);
    this.displayedCount = 50;
    this.renderResults(query);
  }

  private renderResults(query: string): void {
    if (!this.resultsContainer) return;
    this.resultsContainer.empty();

    if (this.currentResults.length === 0) {
      const emptyState = this.resultsContainer.createDiv({ cls: 'search-empty-state' });
      emptyState.textContent = `No matches found for '${query}'`;
      return;
    }

    const maxScore = this.currentResults.reduce(
      (max, r) => Math.max(max, r.score),
      0
    );

    const toShow = this.currentResults.slice(0, this.displayedCount);

    for (const result of toShow) {
      this.renderResultItem(result, query, maxScore);
    }

    // "Show more" button if there are remaining results
    if (this.currentResults.length > this.displayedCount) {
      const showMore = this.resultsContainer.createDiv({ cls: 'search-show-more' });
      showMore.textContent = `Show more (${this.currentResults.length - this.displayedCount} remaining)`;
      showMore.addEventListener('click', () => {
        this.displayedCount += 50;
        this.renderResults(query);
      });
    }
  }

  private renderResultItem(
    result: SearchResult,
    query: string,
    maxScore: number
  ): void {
    if (!this.resultsContainer) return;

    const item = this.resultsContainer.createDiv({ cls: 'search-result-item' });

    // Row 1: Title + source dot + date
    const titleRow = item.createDiv({ cls: 'search-result-title' });

    const titleSpan = titleRow.createSpan();
    titleSpan.textContent = result.entry.metadata.title || 'Untitled';

    const sourceDot = titleRow.createSpan({ cls: 'search-source-dot' });
    const sourceColor = PLATFORM_COLORS[result.entry.metadata.source] || '#888';
    sourceDot.style.backgroundColor = sourceColor;

    const dateSpan = titleRow.createSpan({ cls: 'search-result-date' });
    dateSpan.textContent = this.formatDate(result.entry.metadata.date);

    // Row 2: Snippet with highlighted matches
    const snippetEl = item.createDiv({ cls: 'search-snippet' });
    this.renderHighlightedSnippet(snippetEl, result.snippet, query);

    // Row 3: Score bar
    const scoreBar = item.createDiv({ cls: 'search-score-bar' });
    const scorePercent = maxScore > 0 ? (result.score / maxScore) * 100 : 0;
    scoreBar.style.width = `${scorePercent}%`;

    // Click handler: open the file
    item.addEventListener('click', () => {
      this.app.workspace.openLinkText(result.entry.path, '', false);
    });
  }

  private renderHighlightedSnippet(
    container: HTMLElement,
    snippet: string,
    query: string
  ): void {
    if (!snippet) {
      container.textContent = '';
      return;
    }

    // Split query into individual terms for highlighting
    const terms = query
      .toLowerCase()
      .split(/\s+/)
      .filter((t) => t.length > 0);

    if (terms.length === 0) {
      container.textContent = snippet;
      return;
    }

    // Build a regex that matches any of the query terms
    const escapedTerms = terms.map((t) =>
      t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    );
    const regex = new RegExp(`(${escapedTerms.join('|')})`, 'gi');

    // split() with a capturing group alternates: non-match, match, non-match, ...
    const parts = snippet.split(regex);

    for (let i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      // Odd indices are captured groups (matches)
      if (i % 2 === 1) {
        const strong = container.createEl('strong', { cls: 'search-match' });
        strong.textContent = parts[i];
      } else {
        container.appendText(parts[i]);
      }
    }
  }

  private renderEmptyState(): void {
    if (!this.resultsContainer) return;
    this.resultsContainer.empty();

    const emptyState = this.resultsContainer.createDiv({ cls: 'search-empty-state' });
    emptyState.textContent = 'Start typing to search across all conversations';
  }

  // ─── Helpers ─────────────────────────────────────────────────────────────

  private formatDate(dateStr: string): string {
    if (!dateStr) return '';
    // Parse ISO date and format as short date
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  }
}
