// Platform colors
export const PLATFORM_COLORS = {
  claude: '#d97706',
  chatgpt: '#10b981',
  gemini: '#3b82f6',
} as const;

// Platform display names
export const PLATFORM_NAMES = {
  claude: 'Claude',
  chatgpt: 'ChatGPT',
  gemini: 'Gemini',
} as const;

// View type identifier
export const VIEW_TYPE_AI_CONVERSATIONS = 'ai-conversations-viewer';

// CSS class prefixes
export const CSS_PREFIX = {
  chat: 'chat-',
  browse: 'browse-',
  search: 'search-',
  analytics: 'analytics-',
} as const;

// Default batch size for background indexing
export const INDEX_BATCH_SIZE = 20;

// Search debounce delays
export const SEARCH_DEBOUNCE_MS = 300;
export const FILTER_DEBOUNCE_MS = 200;

// Virtual list settings
export const VIRTUAL_LIST_ITEM_HEIGHT = 60; // px
export const VIRTUAL_LIST_BUFFER = 10; // items above/below viewport
