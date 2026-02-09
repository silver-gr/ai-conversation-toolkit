import { App } from 'obsidian';
import type ConversationIndex from '../index/ConversationIndex';
import type { TabComponent, BrowseFilters, IndexEntry } from '../types';
import { PLATFORM_COLORS, PLATFORM_NAMES, VIRTUAL_LIST_ITEM_HEIGHT, VIRTUAL_LIST_BUFFER } from '../constants';

/**
 * BrowseView renders filter controls and a virtual-scrolling conversation list
 * inside the sidebar's "Browse" tab.
 */
export class BrowseView implements TabComponent {
  containerEl: HTMLElement;
  private index: ConversationIndex;
  private app: App;
  private currentFilters: BrowseFilters;
  private filteredEntries: IndexEntry[] = [];
  private listContainerEl: HTMLElement | null = null;
  private resultCountEl: HTMLElement | null = null;

  /** Virtual list state */
  private scrollTop = 0;
  private rafId: number | null = null;
  private spacerEl: HTMLElement | null = null;
  private itemsEl: HTMLElement | null = null;

  /** Debounce timer for filter changes */
  private filterDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  /** Bound event handlers for cleanup */
  private boundOnEntriesChanged: () => void;
  private boundOnScroll: () => void;

  constructor(containerEl: HTMLElement, index: ConversationIndex, app: App) {
    this.containerEl = containerEl;
    this.index = index;
    this.app = app;

    this.currentFilters = {
      sources: ['claude', 'chatgpt', 'gemini'],
      models: [],
      topics: [],
      sortBy: 'date',
      sortOrder: 'desc',
    };

    this.boundOnEntriesChanged = () => this.updateResults();
    this.boundOnScroll = () => this.scheduleRender();
  }

  render(): void {
    this.containerEl.empty();
    this.containerEl.addClass('browse-container');

    this.renderFilters();
    this.renderResultCount();
    this.renderList();
    this.updateResults();

    this.index.on('entries-changed', this.boundOnEntriesChanged);
  }

  destroy(): void {
    this.index.off('entries-changed', this.boundOnEntriesChanged);

    if (this.filterDebounceTimer !== null) {
      clearTimeout(this.filterDebounceTimer);
      this.filterDebounceTimer = null;
    }

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    if (this.listContainerEl) {
      this.listContainerEl.removeEventListener('scroll', this.boundOnScroll);
    }

    this.containerEl.empty();
    this.listContainerEl = null;
    this.resultCountEl = null;
    this.spacerEl = null;
    this.itemsEl = null;
  }

  onIndexReady(): void {
    this.updateResults();
  }

  // ─── Filter Controls ─────────────────────────────────────────────────────

  private renderFilters(): void {
    const filtersEl = this.containerEl.createDiv({ cls: 'browse-filters' });

    // Source toggle buttons
    this.renderSourceRow(filtersEl);

    // Date range
    this.renderDateRow(filtersEl);

    // Model select
    this.renderModelRow(filtersEl);

    // Topic input with datalist
    this.renderTopicRow(filtersEl);

    // Toggles row: Has code, Research only
    this.renderTogglesRow(filtersEl);

    // Sort row
    this.renderSortRow(filtersEl);
  }

  private renderSourceRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });
    row.createSpan({ cls: 'browse-filter-label', text: 'Source' });

    const sources: Array<'claude' | 'chatgpt' | 'gemini'> = ['claude', 'chatgpt', 'gemini'];
    for (const source of sources) {
      const btn = row.createEl('button', {
        cls: 'browse-source-btn active',
        text: PLATFORM_NAMES[source],
      });
      btn.dataset.source = source;
      btn.addEventListener('click', () => {
        const idx = this.currentFilters.sources.indexOf(source);
        if (idx >= 0) {
          this.currentFilters.sources.splice(idx, 1);
          btn.removeClass('active');
        } else {
          this.currentFilters.sources.push(source);
          btn.addClass('active');
        }
        this.debouncedUpdateResults();
      });
    }
  }

  private renderDateRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });
    row.createSpan({ cls: 'browse-filter-label', text: 'Date' });

    const fromInput = row.createEl('input', {
      type: 'date',
      cls: 'browse-date-input',
    });
    row.createSpan({ text: '-', cls: 'browse-date-separator' });
    const toInput = row.createEl('input', {
      type: 'date',
      cls: 'browse-date-input',
    });

    const handleDateChange = () => {
      const from = fromInput.value;
      const to = toInput.value;
      if (from || to) {
        this.currentFilters.dateRange = { from, to };
      } else {
        this.currentFilters.dateRange = undefined;
      }
      this.debouncedUpdateResults();
    };

    fromInput.addEventListener('change', handleDateChange);
    toInput.addEventListener('change', handleDateChange);
  }

  private renderModelRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });
    row.createSpan({ cls: 'browse-filter-label', text: 'Model' });

    const select = row.createEl('select', { cls: 'browse-model-select' });
    const defaultOpt = select.createEl('option', { text: 'All models', value: '' });
    defaultOpt.value = '';

    const models = this.index.getAvailableModels();
    for (const model of models) {
      const opt = select.createEl('option', { text: model, value: model });
      opt.value = model;
    }

    select.addEventListener('change', () => {
      if (select.value) {
        this.currentFilters.models = [select.value];
      } else {
        this.currentFilters.models = [];
      }
      this.debouncedUpdateResults();
    });
  }

  private renderTopicRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });
    row.createSpan({ cls: 'browse-filter-label', text: 'Topic' });

    const listId = 'browse-topics-list';
    const input = row.createEl('input', {
      type: 'text',
      cls: 'browse-topic-input',
      placeholder: 'Filter by topic...',
    });
    input.setAttribute('list', listId);

    const datalist = row.createEl('datalist');
    datalist.id = listId;

    const topics = this.index.getAvailableTopics().slice(0, 50);
    for (const topic of topics) {
      datalist.createEl('option', { value: topic });
    }

    input.addEventListener('change', () => {
      const val = input.value.trim();
      if (val) {
        this.currentFilters.topics = [val];
      } else {
        this.currentFilters.topics = [];
      }
      this.debouncedUpdateResults();
    });

    input.addEventListener('input', () => {
      const val = input.value.trim();
      if (!val) {
        this.currentFilters.topics = [];
        this.debouncedUpdateResults();
      }
    });
  }

  private renderTogglesRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });

    const codeLabel = row.createEl('label', { cls: 'browse-checkbox-label' });
    const codeCheckbox = codeLabel.createEl('input', { type: 'checkbox' });
    codeLabel.appendText(' Has code');

    codeCheckbox.addEventListener('change', () => {
      this.currentFilters.hasCode = codeCheckbox.checked ? true : undefined;
      this.debouncedUpdateResults();
    });

    const researchLabel = row.createEl('label', { cls: 'browse-checkbox-label' });
    const researchCheckbox = researchLabel.createEl('input', { type: 'checkbox' });
    researchLabel.appendText(' Research only');

    researchCheckbox.addEventListener('change', () => {
      this.currentFilters.researchOnly = researchCheckbox.checked ? true : undefined;
      this.debouncedUpdateResults();
    });
  }

  private renderSortRow(parent: HTMLElement): void {
    const row = parent.createDiv({ cls: 'browse-filter-row' });
    row.createSpan({ cls: 'browse-filter-label', text: 'Sort' });

    const select = row.createEl('select', { cls: 'browse-sort-select' });
    const options: Array<{ value: BrowseFilters['sortBy']; label: string }> = [
      { value: 'date', label: 'Date' },
      { value: 'messages', label: 'Messages' },
      { value: 'characters', label: 'Characters' },
    ];
    for (const opt of options) {
      const el = select.createEl('option', { text: opt.label, value: opt.value });
      el.value = opt.value;
    }

    select.addEventListener('change', () => {
      this.currentFilters.sortBy = select.value as BrowseFilters['sortBy'];
      this.debouncedUpdateResults();
    });

    const orderBtn = row.createEl('button', {
      cls: 'browse-sort-order-btn',
      text: this.currentFilters.sortOrder === 'desc' ? '\u2193' : '\u2191',
    });

    orderBtn.addEventListener('click', () => {
      this.currentFilters.sortOrder = this.currentFilters.sortOrder === 'desc' ? 'asc' : 'desc';
      orderBtn.textContent = this.currentFilters.sortOrder === 'desc' ? '\u2193' : '\u2191';
      this.debouncedUpdateResults();
    });
  }

  // ─── Result Count ────────────────────────────────────────────────────────

  private renderResultCount(): void {
    this.resultCountEl = this.containerEl.createDiv({ cls: 'browse-result-count' });
    this.resultCountEl.textContent = '0 conversations';
  }

  // ─── Virtual List ────────────────────────────────────────────────────────

  private renderList(): void {
    this.listContainerEl = this.containerEl.createDiv({ cls: 'browse-virtual-container' });

    this.spacerEl = this.listContainerEl.createDiv({ cls: 'browse-virtual-spacer' });
    this.itemsEl = this.listContainerEl.createDiv({ cls: 'browse-virtual-items' });

    this.listContainerEl.addEventListener('scroll', this.boundOnScroll);
  }

  /** Debounce filter changes so rapid clicking doesn't cause redundant recalculation */
  private debouncedUpdateResults(): void {
    if (this.filterDebounceTimer !== null) {
      clearTimeout(this.filterDebounceTimer);
    }
    this.filterDebounceTimer = setTimeout(() => {
      this.filterDebounceTimer = null;
      this.updateResults();
    }, 100);
  }

  private updateResults(): void {
    this.filteredEntries = this.index.getFiltered(this.currentFilters);

    if (this.resultCountEl) {
      const count = this.filteredEntries.length;
      this.resultCountEl.textContent = count === 0
        ? 'No conversations found'
        : `${count} conversation${count !== 1 ? 's' : ''}`;
    }

    // Reset scroll to top so filtered results start from the beginning
    if (this.listContainerEl) {
      this.listContainerEl.scrollTop = 0;
    }

    this.renderVirtualList();
  }

  private scheduleRender(): void {
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      this.renderVirtualList();
    });
  }

  private renderVirtualList(): void {
    if (!this.listContainerEl || !this.spacerEl || !this.itemsEl) return;

    const itemHeight = VIRTUAL_LIST_ITEM_HEIGHT;
    const buffer = VIRTUAL_LIST_BUFFER;
    const totalItems = this.filteredEntries.length;
    const totalHeight = totalItems * itemHeight;

    this.spacerEl.style.height = `${totalHeight}px`;

    this.scrollTop = this.listContainerEl.scrollTop;
    const containerHeight = this.listContainerEl.clientHeight;

    const startIndex = Math.max(0, Math.floor(this.scrollTop / itemHeight) - buffer);
    const endIndex = Math.min(
      totalItems,
      Math.ceil((this.scrollTop + containerHeight) / itemHeight) + buffer
    );

    // Clear existing items
    this.itemsEl.empty();
    this.itemsEl.style.position = 'absolute';
    this.itemsEl.style.top = `${startIndex * itemHeight}px`;
    this.itemsEl.style.left = '0';
    this.itemsEl.style.right = '0';

    for (let i = startIndex; i < endIndex; i++) {
      const entry = this.filteredEntries[i];
      if (!entry) continue;
      this.renderListItem(this.itemsEl, entry);
    }
  }

  private renderListItem(parent: HTMLElement, entry: IndexEntry): void {
    const item = parent.createDiv({ cls: 'browse-list-item' });

    // Source dot
    const dot = item.createDiv({ cls: 'browse-source-dot' });
    dot.style.backgroundColor = PLATFORM_COLORS[entry.metadata.source] || '#888';

    // Content container
    const content = item.createDiv({ cls: 'browse-item-content' });

    // Title
    content.createDiv({
      cls: 'browse-item-title',
      text: entry.metadata.title || 'Untitled',
    });

    // Meta row: messages + date
    const meta = content.createDiv({ cls: 'browse-item-meta' });
    meta.createSpan({ text: `${entry.metadata.messages} msgs` });
    meta.createSpan({ text: this.formatDate(entry.metadata.date) });

    // Topic pills (first 3)
    if (entry.metadata.topics.length > 0) {
      const topicsRow = content.createDiv({ cls: 'browse-item-topics' });
      const maxTopics = Math.min(3, entry.metadata.topics.length);
      for (let i = 0; i < maxTopics; i++) {
        topicsRow.createSpan({
          cls: 'browse-topic-tag',
          text: entry.metadata.topics[i],
        });
      }
    }

    // Click handler
    item.addEventListener('click', () => {
      this.app.workspace.openLinkText(entry.path, '', false);
    });
  }

  /**
   * Format an ISO date string to a compact display format.
   * Same year: "Jan 24", different year: "2025-07-02"
   */
  private formatDate(dateStr: string): string {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;

      const now = new Date();
      if (date.getFullYear() === now.getFullYear()) {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${months[date.getMonth()]} ${date.getDate()}`;
      }
      return dateStr.slice(0, 10);
    } catch {
      return dateStr;
    }
  }
}
