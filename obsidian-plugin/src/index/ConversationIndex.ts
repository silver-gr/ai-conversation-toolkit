import { App, TFile, TAbstractFile, CachedMetadata, EventRef } from 'obsidian';
import MiniSearch from 'minisearch';
import type {
  IndexEntry,
  BrowseFilters,
  SearchResult,
  ConversationStats,
  ConversationMetadata,
  PluginSettings,
} from '../types';
import { INDEX_BATCH_SIZE } from '../constants';

/** Document shape for MiniSearch indexing */
interface SearchDocument {
  id: string;       // file path (unique key)
  title: string;
  content: string;
  path: string;
  date: string;
  source: string;
}

type EventName = 'index-progress' | 'index-ready' | 'entries-changed';

/**
 * ConversationIndex is the core data service for the AI Conversations plugin.
 *
 * It integrates with Obsidian's MetadataCache to maintain an in-memory index
 * of all conversation files (identified by `type: conversation` in YAML frontmatter),
 * and progressively builds a full-text search index using MiniSearch.
 *
 * All UI components consume this service for browsing, searching, and analytics.
 */
export default class ConversationIndex {
  private app: App;
  private settings: PluginSettings;

  /** Primary data store: vault-relative path -> IndexEntry */
  private entries: Map<string, IndexEntry> = new Map();

  /** MiniSearch full-text index */
  private miniSearch: MiniSearch<SearchDocument>;

  /** Background indexing state */
  private indexProgress: { indexed: number; total: number } = { indexed: 0, total: 0 };
  private indexReady = false;
  private indexQueue: string[] = [];
  private indexingInProgress = false;

  /** Custom event emitter: event name -> set of callbacks */
  private listeners: Map<EventName, Set<Function>> = new Map();

  /** Obsidian event references for cleanup */
  private metadataCacheRef: EventRef | null = null;
  private vaultDeleteRef: EventRef | null = null;
  private vaultRenameRef: EventRef | null = null;

  constructor(app: App, settings: PluginSettings) {
    this.app = app;
    this.settings = settings;

    this.miniSearch = new MiniSearch<SearchDocument>({
      fields: ['title', 'content'],
      storeFields: ['path', 'title', 'date', 'source'],
      idField: 'id',
    });
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  /**
   * Initialize the index by scanning existing vault files for conversation metadata,
   * registering vault event listeners, and queuing background full-text indexing.
   */
  async initialize(): Promise<void> {
    // Build initial entries from MetadataCache
    this.buildEntriesFromCache();

    // Register vault event listeners
    this.metadataCacheRef = this.app.metadataCache.on(
      'changed',
      (file: TFile, _data: string, cache: CachedMetadata) => {
        if (!cache) return; // Cache may be incomplete during initial parse
        this.handleFileChanged(file, cache);
      }
    );

    this.vaultDeleteRef = this.app.vault.on('delete', (file: TAbstractFile) => {
      if (file instanceof TFile) {
        this.handleFileDeleted(file);
      }
    });

    this.vaultRenameRef = this.app.vault.on(
      'rename',
      (file: TAbstractFile, oldPath: string) => {
        if (file instanceof TFile) {
          this.handleFileRenamed(file, oldPath);
        }
      }
    );

    // Queue all conversation files for full-text indexing
    this.queueAllForIndexing();
  }

  /**
   * Clean up event listeners and release resources.
   */
  destroy(): void {
    if (this.metadataCacheRef) {
      this.app.metadataCache.offref(this.metadataCacheRef);
      this.metadataCacheRef = null;
    }
    if (this.vaultDeleteRef) {
      this.app.vault.offref(this.vaultDeleteRef);
      this.vaultDeleteRef = null;
    }
    if (this.vaultRenameRef) {
      this.app.vault.offref(this.vaultRenameRef);
      this.vaultRenameRef = null;
    }

    this.entries.clear();
    this.listeners.clear();
    this.indexQueue = [];
    this.indexingInProgress = false;
  }

  // ─── MetadataCache Integration ────────────────────────────────────────────

  /**
   * Scan the vault for all markdown files and build entries from their frontmatter.
   */
  private buildEntriesFromCache(): void {
    const files = this.app.vault.getMarkdownFiles();

    for (const file of files) {
      if (!this.isInConversationFolder(file.path)) continue;

      const cache = this.app.metadataCache.getFileCache(file);
      if (!cache?.frontmatter) continue;

      const entry = this.parseEntry(file.path, cache.frontmatter);
      if (entry) {
        this.entries.set(file.path, entry);
      }
    }
  }

  /**
   * Check if a file path is within the configured conversation folder.
   * If no folder is configured (empty string), all vault files are considered.
   */
  private isInConversationFolder(path: string): boolean {
    if (!this.settings.conversationFolder) return true;
    return path.startsWith(this.settings.conversationFolder + '/') ||
           path === this.settings.conversationFolder;
  }

  /**
   * Parse frontmatter into an IndexEntry, returning null if this isn't
   * a valid conversation file.
   */
  private parseEntry(
    path: string,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    frontmatter: Record<string, any>
  ): IndexEntry | null {
    if (frontmatter.type !== 'conversation') return null;

    const metadata: ConversationMetadata = {
      type: 'conversation',
      title: String(frontmatter.title ?? ''),
      date: String(frontmatter.date ?? ''),
      source: this.normalizeSource(frontmatter.source),
      model: frontmatter.model ? String(frontmatter.model) : undefined,
      messages: Number(frontmatter.messages) || 0,
      characters: Number(frontmatter.characters) || 0,
      has_code: Boolean(frontmatter.has_code),
      topics: Array.isArray(frontmatter.topics)
        ? frontmatter.topics.map(String)
        : [],
      research_type: this.normalizeResearchType(frontmatter.research_type),
    };

    return { path, metadata };
  }

  /**
   * Normalize source string to one of the valid source values.
   */
  private normalizeSource(value: unknown): 'claude' | 'chatgpt' | 'gemini' {
    const str = String(value ?? '').toLowerCase();
    if (str === 'claude' || str === 'chatgpt' || str === 'gemini') {
      return str;
    }
    return 'chatgpt'; // Default fallback
  }

  /**
   * Normalize research_type to valid enum value or undefined.
   */
  private normalizeResearchType(
    value: unknown
  ): 'deep-research' | 'research-tool' | null | undefined {
    if (value === null) return null;
    if (value === 'deep-research' || value === 'research-tool') return value;
    return undefined;
  }

  // ─── Vault Event Handlers ─────────────────────────────────────────────────

  /**
   * Handle MetadataCache 'changed' event: update or remove an entry as needed.
   */
  private handleFileChanged(file: TFile, cache: CachedMetadata): void {
    if (!this.isInConversationFolder(file.path)) return;

    const frontmatter = cache.frontmatter;
    if (!frontmatter) {
      // File no longer has frontmatter — remove if previously tracked
      if (this.entries.has(file.path)) {
        this.entries.delete(file.path);
        this.removeFromSearchIndex(file.path);
        this.emit('entries-changed');
      }
      return;
    }

    const entry = this.parseEntry(file.path, frontmatter);
    if (entry) {
      const isNew = !this.entries.has(file.path);
      this.entries.set(file.path, entry);
      // Re-index content in background
      this.reindexFile(file.path);
      this.emit('entries-changed');
      if (isNew) {
        this.indexProgress.total++;
      }
    } else if (this.entries.has(file.path)) {
      // Was tracked but no longer qualifies
      this.entries.delete(file.path);
      this.removeFromSearchIndex(file.path);
      this.emit('entries-changed');
    }
  }

  /**
   * Handle vault 'delete' event: remove entry and search index data.
   */
  private handleFileDeleted(file: TFile): void {
    if (this.entries.has(file.path)) {
      this.entries.delete(file.path);
      this.removeFromSearchIndex(file.path);
      this.indexProgress.total = Math.max(0, this.indexProgress.total - 1);
      this.emit('entries-changed');
    }
  }

  /**
   * Handle vault 'rename' event: update the path for existing entries.
   */
  private handleFileRenamed(file: TFile, oldPath: string): void {
    const entry = this.entries.get(oldPath);
    if (entry) {
      this.entries.delete(oldPath);
      this.removeFromSearchIndex(oldPath);

      if (this.isInConversationFolder(file.path)) {
        entry.path = file.path;
        this.entries.set(file.path, entry);
        // Re-index at new path
        this.reindexFile(file.path);
      }
      this.emit('entries-changed');
    }
  }

  // ─── MiniSearch Background Indexer ────────────────────────────────────────

  /**
   * Queue all current entries for background full-text indexing.
   */
  private queueAllForIndexing(): void {
    this.indexQueue = Array.from(this.entries.keys());
    this.indexProgress = { indexed: 0, total: this.indexQueue.length };
    this.indexReady = false;

    if (this.indexQueue.length === 0) {
      this.indexReady = true;
      this.emit('index-ready');
      return;
    }

    if (!this.indexingInProgress) {
      this.processIndexBatch();
    }
  }

  /**
   * Process the next batch of files for full-text indexing.
   * Uses setTimeout(fn, 0) between batches to avoid blocking the UI.
   */
  private processIndexBatch(): void {
    this.indexingInProgress = true;

    const batch = this.indexQueue.splice(0, INDEX_BATCH_SIZE);
    if (batch.length === 0) {
      this.indexingInProgress = false;
      if (!this.indexReady) {
        this.indexReady = true;
        this.emit('index-ready');
      }
      return;
    }

    const promises = batch.map((path) => this.indexFile(path));
    Promise.all(promises).then(() => {
      this.indexProgress.indexed += batch.length;
      this.emit('index-progress');

      if (this.indexQueue.length > 0) {
        // Yield to the event loop before processing next batch
        setTimeout(() => this.processIndexBatch(), 0);
      } else {
        this.indexingInProgress = false;
        if (!this.indexReady) {
          this.indexReady = true;
          this.emit('index-ready');
        }
      }
    }).catch(() => {
      // Individual indexFile errors are already caught, but guard against
      // unexpected failures to prevent the indexing pipeline from stalling.
      this.indexProgress.indexed += batch.length;
      if (this.indexQueue.length > 0) {
        setTimeout(() => this.processIndexBatch(), 0);
      } else {
        this.indexingInProgress = false;
        if (!this.indexReady) {
          this.indexReady = true;
          this.emit('index-ready');
        }
      }
    });
  }

  /**
   * Index a single file's content into MiniSearch.
   */
  private async indexFile(path: string): Promise<void> {
    const entry = this.entries.get(path);
    if (!entry) return;

    const file = this.app.vault.getAbstractFileByPath(path);
    if (!(file instanceof TFile)) return;

    try {
      const rawContent = await this.app.vault.cachedRead(file);
      const content = this.stripFrontmatter(rawContent);

      const doc: SearchDocument = {
        id: path,
        title: entry.metadata.title,
        content,
        path,
        date: entry.metadata.date,
        source: entry.metadata.source,
      };

      // Remove existing entry if present before adding
      if (this.miniSearch.has(path)) {
        this.miniSearch.discard(path);
      }

      this.miniSearch.add(doc);
    } catch {
      // File read failed — skip silently
    }
  }

  /**
   * Re-index a single file (remove old entry, add new).
   */
  private async reindexFile(path: string): Promise<void> {
    await this.indexFile(path);
    this.emit('index-progress');
  }

  /**
   * Remove a file from the MiniSearch index.
   */
  private removeFromSearchIndex(path: string): void {
    if (this.miniSearch.has(path)) {
      this.miniSearch.discard(path);
    }
  }

  /**
   * Strip YAML frontmatter from file content.
   * Removes everything from start up to and including the second '---' line.
   */
  private stripFrontmatter(content: string): string {
    if (!content.startsWith('---')) return content;
    const endIndex = content.indexOf('\n---', 3);
    if (endIndex === -1) return content;
    return content.slice(endIndex + 4).trim();
  }

  // ─── Browse (MetadataCache-powered, instant) ──────────────────────────────

  /**
   * Get all indexed entries as an array.
   */
  getAllEntries(): IndexEntry[] {
    return Array.from(this.entries.values());
  }

  /**
   * Get entries filtered and sorted according to BrowseFilters.
   */
  getFiltered(filters: BrowseFilters): IndexEntry[] {
    let results = this.getAllEntries();

    // Filter by sources
    if (filters.sources.length > 0) {
      results = results.filter((e) => filters.sources.includes(e.metadata.source));
    }

    // Filter by date range
    if (filters.dateRange) {
      const { from, to } = filters.dateRange;
      if (from) {
        results = results.filter((e) => e.metadata.date >= from);
      }
      if (to) {
        results = results.filter((e) => e.metadata.date <= to);
      }
    }

    // Filter by models
    if (filters.models.length > 0) {
      results = results.filter(
        (e) => e.metadata.model !== undefined && filters.models.includes(e.metadata.model)
      );
    }

    // Filter by topics
    if (filters.topics.length > 0) {
      results = results.filter((e) =>
        filters.topics.some((t) => e.metadata.topics.includes(t))
      );
    }

    // Filter by has_code
    if (filters.hasCode !== undefined) {
      results = results.filter((e) => e.metadata.has_code === filters.hasCode);
    }

    // Filter by research only
    if (filters.researchOnly) {
      results = results.filter(
        (e) =>
          e.metadata.research_type === 'deep-research' ||
          e.metadata.research_type === 'research-tool'
      );
    }

    // Sort
    results.sort((a, b) => {
      let cmp = 0;
      switch (filters.sortBy) {
        case 'date':
          cmp = a.metadata.date.localeCompare(b.metadata.date);
          break;
        case 'messages':
          cmp = a.metadata.messages - b.metadata.messages;
          break;
        case 'characters':
          cmp = a.metadata.characters - b.metadata.characters;
          break;
      }
      return filters.sortOrder === 'desc' ? -cmp : cmp;
    });

    return results;
  }

  /**
   * Get all unique model names from indexed entries.
   */
  getAvailableModels(): string[] {
    const models = new Set<string>();
    for (const entry of this.entries.values()) {
      if (entry.metadata.model) {
        models.add(entry.metadata.model);
      }
    }
    return Array.from(models).sort();
  }

  /**
   * Get all unique topics from indexed entries, sorted by frequency (descending).
   */
  getAvailableTopics(): string[] {
    const topicCounts = new Map<string, number>();
    for (const entry of this.entries.values()) {
      for (const topic of entry.metadata.topics) {
        topicCounts.set(topic, (topicCounts.get(topic) ?? 0) + 1);
      }
    }
    return Array.from(topicCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([topic]) => topic);
  }

  // ─── Search (MiniSearch-powered, progressive) ─────────────────────────────

  /**
   * Full-text search across all indexed conversation content.
   * Returns top 50 results with snippets and scores.
   */
  search(query: string, filters?: Partial<BrowseFilters>): SearchResult[] {
    if (!this.indexReady || !query.trim()) {
      return [];
    }

    const rawResults = this.miniSearch.search(query, {
      boost: { title: 2 },
      prefix: true,
      fuzzy: 0.2,
    });

    let results: SearchResult[] = rawResults.map((result) => {
      const entry = this.entries.get(result.id as string);
      if (!entry) return null;

      const snippet = this.extractSnippet(result, query);
      return {
        entry,
        score: result.score,
        snippet,
      };
    }).filter((r): r is SearchResult => r !== null);

    // Apply optional post-search filters
    if (filters) {
      results = this.applyPartialFilters(results, filters);
    }

    return results.slice(0, 50);
  }

  /**
   * Extract a snippet from search result terms, providing context around the match.
   */
  private extractSnippet(
    result: { id: unknown; terms: string[]; score: number; match: Record<string, string[]>; [key: string]: unknown },
    query: string
  ): string {
    // Try to find the first matching term in the stored content
    const path = result.id as string;
    const file = this.app.vault.getAbstractFileByPath(path);
    if (!(file instanceof TFile)) {
      return '';
    }

    // Use the cached metadata title as fallback snippet
    const entry = this.entries.get(path);
    if (!entry) return '';

    // We don't have synchronous access to file content here,
    // so build snippet from search terms and title
    const terms = result.terms;
    if (terms.length > 0) {
      const matchedTerm = terms[0];
      return `...${matchedTerm}... (matched in: ${Object.values(result.match).flat().join(', ')})`;
    }

    return entry.metadata.title || query;
  }

  /**
   * Apply partial browse filters to search results for post-search filtering.
   */
  private applyPartialFilters(
    results: SearchResult[],
    filters: Partial<BrowseFilters>
  ): SearchResult[] {
    let filtered = results;

    if (filters.sources && filters.sources.length > 0) {
      filtered = filtered.filter((r) =>
        filters.sources!.includes(r.entry.metadata.source)
      );
    }

    if (filters.dateRange) {
      const { from, to } = filters.dateRange;
      if (from) {
        filtered = filtered.filter((r) => r.entry.metadata.date >= from);
      }
      if (to) {
        filtered = filtered.filter((r) => r.entry.metadata.date <= to);
      }
    }

    if (filters.models && filters.models.length > 0) {
      filtered = filtered.filter(
        (r) =>
          r.entry.metadata.model !== undefined &&
          filters.models!.includes(r.entry.metadata.model)
      );
    }

    if (filters.topics && filters.topics.length > 0) {
      filtered = filtered.filter((r) =>
        filters.topics!.some((t) => r.entry.metadata.topics.includes(t))
      );
    }

    if (filters.hasCode !== undefined) {
      filtered = filtered.filter((r) => r.entry.metadata.has_code === filters.hasCode);
    }

    if (filters.researchOnly) {
      filtered = filtered.filter(
        (r) =>
          r.entry.metadata.research_type === 'deep-research' ||
          r.entry.metadata.research_type === 'research-tool'
      );
    }

    return filtered;
  }

  /**
   * Get current indexing progress.
   */
  getIndexProgress(): { indexed: number; total: number } {
    return { ...this.indexProgress };
  }

  /**
   * Check if the full-text search index has been fully built.
   */
  isIndexReady(): boolean {
    return this.indexReady;
  }

  // ─── Analytics (computed from MetadataCache) ──────────────────────────────

  /**
   * Compute aggregate statistics from indexed entries.
   * Optionally scoped to a subset via partial BrowseFilters.
   */
  getStats(filters?: Partial<BrowseFilters>): ConversationStats {
    let entries = this.getAllEntries();

    // Apply partial filters if provided
    if (filters) {
      entries = this.applyPartialFiltersToEntries(entries, filters);
    }

    const bySource: Record<string, number> = {};
    const byMonth: Map<string, number> = new Map();
    const byModel: Record<string, number> = {};
    const topicCounts: Map<string, number> = new Map();
    const messagesBySource: Record<string, number> = {};
    const countBySource: Record<string, number> = {};

    let totalMessages = 0;
    let totalCharacters = 0;

    for (const entry of entries) {
      const m = entry.metadata;

      totalMessages += m.messages;
      totalCharacters += m.characters;

      // By source
      bySource[m.source] = (bySource[m.source] ?? 0) + 1;

      // Messages by source (for average calculation)
      messagesBySource[m.source] = (messagesBySource[m.source] ?? 0) + m.messages;
      countBySource[m.source] = (countBySource[m.source] ?? 0) + 1;

      // By month (extract YYYY-MM from ISO date)
      if (m.date) {
        const month = m.date.slice(0, 7); // "YYYY-MM"
        byMonth.set(month, (byMonth.get(month) ?? 0) + 1);
      }

      // By model
      if (m.model) {
        byModel[m.model] = (byModel[m.model] ?? 0) + 1;
      }

      // Topics
      for (const topic of m.topics) {
        topicCounts.set(topic, (topicCounts.get(topic) ?? 0) + 1);
      }
    }

    // Sort months chronologically
    const sortedMonths = Array.from(byMonth.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, count]) => ({ month, count }));

    // Top topics sorted by count descending
    const topTopics = Array.from(topicCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
      .map(([topic, count]) => ({ topic, count }));

    // Average messages per conversation by source
    const avgMessagesBySource: Record<string, number> = {};
    for (const source of Object.keys(countBySource)) {
      avgMessagesBySource[source] = Math.round(
        messagesBySource[source] / countBySource[source]
      );
    }

    return {
      total: entries.length,
      totalMessages,
      totalCharacters,
      bySource,
      byMonth: sortedMonths,
      byModel,
      topTopics,
      avgMessagesBySource,
    };
  }

  /**
   * Apply partial filters to an array of entries (for analytics scoping).
   */
  private applyPartialFiltersToEntries(
    entries: IndexEntry[],
    filters: Partial<BrowseFilters>
  ): IndexEntry[] {
    let filtered = entries;

    if (filters.sources && filters.sources.length > 0) {
      filtered = filtered.filter((e) => filters.sources!.includes(e.metadata.source));
    }

    if (filters.dateRange) {
      const { from, to } = filters.dateRange;
      if (from) {
        filtered = filtered.filter((e) => e.metadata.date >= from);
      }
      if (to) {
        filtered = filtered.filter((e) => e.metadata.date <= to);
      }
    }

    if (filters.models && filters.models.length > 0) {
      filtered = filtered.filter(
        (e) =>
          e.metadata.model !== undefined &&
          filters.models!.includes(e.metadata.model)
      );
    }

    if (filters.topics && filters.topics.length > 0) {
      filtered = filtered.filter((e) =>
        filters.topics!.some((t) => e.metadata.topics.includes(t))
      );
    }

    if (filters.hasCode !== undefined) {
      filtered = filtered.filter((e) => e.metadata.has_code === filters.hasCode);
    }

    if (filters.researchOnly) {
      filtered = filtered.filter(
        (e) =>
          e.metadata.research_type === 'deep-research' ||
          e.metadata.research_type === 'research-tool'
      );
    }

    return filtered;
  }

  // ─── Event Emitter ────────────────────────────────────────────────────────

  /**
   * Register a listener for an index event.
   */
  on(event: EventName, cb: Function): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(cb);
  }

  /**
   * Unregister a listener for an index event.
   */
  off(event: EventName, cb: Function): void {
    const set = this.listeners.get(event);
    if (set) {
      set.delete(cb);
    }
  }

  /**
   * Emit an event, calling all registered listeners.
   */
  private emit(event: EventName): void {
    const set = this.listeners.get(event);
    if (set) {
      for (const cb of set) {
        try {
          cb();
        } catch {
          // Don't let listener errors break the index
        }
      }
    }
  }
}
