import type { App } from 'obsidian';

// Core metadata (mirrors YAML frontmatter)
export interface ConversationMetadata {
  type: 'conversation';
  title: string;
  date: string;          // ISO 8601
  source: 'claude' | 'chatgpt' | 'gemini';
  model?: string;
  messages: number;
  characters: number;
  has_code: boolean;
  topics: string[];
  research_type?: 'deep-research' | 'research-tool' | null;
}

// Parsed message from markdown content
export interface ParsedMessage {
  role: 'user' | 'assistant';
  timestamp?: string;    // HH:MM
  content: string;       // Raw markdown content
  index: number;         // Message position
}

// Index entry (metadata + file reference)
export interface IndexEntry {
  path: string;          // Vault-relative file path
  metadata: ConversationMetadata;
}

// Search result
export interface SearchResult {
  entry: IndexEntry;
  score: number;
  snippet: string;       // Context around match
  matchPositions?: { start: number; end: number }[];
}

// Filter state for Browse tab
export interface BrowseFilters {
  sources: ('claude' | 'chatgpt' | 'gemini')[];
  dateRange?: { from: string; to: string };
  models: string[];
  topics: string[];
  hasCode?: boolean;
  researchOnly?: boolean;
  sortBy: 'date' | 'messages' | 'characters';
  sortOrder: 'asc' | 'desc';
}

// Analytics aggregation
export interface ConversationStats {
  total: number;
  totalMessages: number;
  totalCharacters: number;
  bySource: Record<string, number>;
  byMonth: { month: string; count: number }[];
  byModel: Record<string, number>;
  topTopics: { topic: string; count: number }[];
  avgMessagesBySource: Record<string, number>;
}

// Plugin settings
export interface PluginSettings {
  conversationFolder: string;  // Root folder for conversations
  enableRenderer: boolean;
  enableSidebar: boolean;
  userBubbleColor: string;
  platformColors: Record<string, string>;
  codeBlockCollapseLine: number; // Collapse if > N lines
  searchIndexOnStartup: boolean;
}

export const DEFAULT_SETTINGS: PluginSettings = {
  conversationFolder: '',      // Empty = scan entire vault
  enableRenderer: true,
  enableSidebar: true,
  userBubbleColor: '#374151',
  platformColors: {
    claude: '#d97706',
    chatgpt: '#10b981',
    gemini: '#3b82f6',
  },
  codeBlockCollapseLine: 15,
  searchIndexOnStartup: true,
};

// Each sidebar tab component follows this interface
export interface TabComponent {
  containerEl: HTMLElement;
  render(): void;
  destroy(): void;
  onIndexReady?(): void;
}
