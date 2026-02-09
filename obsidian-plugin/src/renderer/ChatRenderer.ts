import { Component, MarkdownRenderer, Plugin, TFile } from 'obsidian';
import type { MarkdownPostProcessorContext } from 'obsidian';
import type { PluginSettings, ParsedMessage } from '../types';

/**
 * Parses conversation markdown content into structured messages.
 * Handles headings in the format: ### USER (HH:MM) or ### ASSISTANT (HH:MM)
 * Also handles headings without timestamps: ### USER or ### ASSISTANT
 */
export function parseConversationContent(markdown: string): ParsedMessage[] {
  const messages: ParsedMessage[] = [];
  const headingRegex = /^###\s+(USER|ASSISTANT)(?:\s+\((\d{1,2}:\d{2})\))?$/gm;

  let match: RegExpExecArray | null;
  const headings: { role: 'user' | 'assistant'; timestamp?: string; startIndex: number; contentStart: number }[] = [];

  while ((match = headingRegex.exec(markdown)) !== null) {
    const role = match[1].toLowerCase() as 'user' | 'assistant';
    const timestamp = match[2] || undefined;
    const startIndex = match.index;
    const contentStart = startIndex + match[0].length;

    headings.push({ role, timestamp, startIndex, contentStart });
  }

  for (let i = 0; i < headings.length; i++) {
    const heading = headings[i];
    const nextHeadingStart = i < headings.length - 1 ? headings[i + 1].startIndex : markdown.length;
    const content = markdown.slice(heading.contentStart, nextHeadingStart).trim();

    messages.push({
      role: heading.role,
      timestamp: heading.timestamp,
      content,
      index: i,
    });
  }

  return messages;
}

/**
 * Registers a MarkdownPostProcessor that transforms conversation markdown
 * files into an interactive chat bubble interface in Reading View.
 */
export function registerChatRenderer(plugin: Plugin, settings: PluginSettings): void {
  plugin.registerMarkdownPostProcessor(async (el: HTMLElement, ctx: MarkdownPostProcessorContext) => {
    // Only process conversation-type files
    if (ctx.frontmatter?.type !== 'conversation') {
      return;
    }

    // Obsidian calls post-processors once per markdown section (each heading
    // creates a section). Use getSectionInfo to deterministically pick ONLY
    // the section containing the first ### USER/ASSISTANT heading. All other
    // sections get emptied. This is timing-independent and works across
    // multiple render passes.
    const info = ctx.getSectionInfo(el);
    if (info) {
      const lines = info.text.split('\n');
      let firstMsgLine = -1;
      for (let i = 0; i < lines.length; i++) {
        if (/^###\s+(USER|ASSISTANT)/.test(lines[i])) {
          firstMsgLine = i;
          break;
        }
      }
      if (firstMsgLine === -1) {
        el.empty();
        return;
      }
      // Only the section that contains the first message heading renders
      if (firstMsgLine < info.lineStart || firstMsgLine > info.lineEnd) {
        el.empty();
        return;
      }
    }

    const source: string = ctx.frontmatter?.source || '';
    const sourcePath = ctx.sourcePath;

    // Read the full source file content
    const file = plugin.app.vault.getAbstractFileByPath(sourcePath);
    if (!(file instanceof TFile)) return;

    const fileContent = await plugin.app.vault.cachedRead(file);

    // Parse messages from the markdown
    const messages = parseConversationContent(fileContent);
    if (messages.length === 0) return;

    // Clear existing content and build chat UI
    el.empty();

    // Build the chat container
    const chatContainer = el.createDiv({ cls: 'chat-container' });

    // Add search bar
    const searchState = createSearchBar(chatContainer, settings);

    // Render each message as a chat bubble
    for (const message of messages) {
      const bubble = chatContainer.createDiv({
        cls: `chat-bubble chat-bubble-${message.role}`,
        attr: { 'data-source': source },
      });

      // Header with role label and optional timestamp
      const header = bubble.createDiv({ cls: 'chat-bubble-header' });
      const roleLabel = message.role === 'user' ? 'You' : capitalizeSource(source);
      header.textContent = message.timestamp ? `${roleLabel} · ${message.timestamp}` : roleLabel;

      // Content rendered via Obsidian's MarkdownRenderer
      const contentEl = bubble.createDiv({ cls: 'chat-bubble-content' });
      const component = new Component();
      component.load();
      ctx.addChild(component as import('obsidian').MarkdownRenderChild);

      await MarkdownRenderer.render(
        plugin.app,
        message.content,
        contentEl,
        sourcePath,
        component
      );

      // Process code blocks for collapse + copy functionality
      processCodeBlocks(contentEl, settings);

      // Actions (copy button)
      const actions = bubble.createDiv({ cls: 'chat-message-actions' });
      const copyBtn = actions.createEl('button', {
        cls: 'chat-action-btn',
        attr: { 'aria-label': 'Copy message' },
      });
      copyBtn.innerHTML = getCopyIcon();
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(message.content).then(() => {
          copyBtn.innerHTML = getCheckIcon();
          setTimeout(() => {
            copyBtn.innerHTML = getCopyIcon();
          }, 2000);
        }).catch(() => { /* clipboard permission denied — ignore silently */ });
      });
    }

    // Initialize search functionality after all bubbles are rendered
    searchState.initialize();
  });
}

/**
 * Capitalizes the source name for display in bubble headers.
 */
function capitalizeSource(source: string): string {
  const names: Record<string, string> = {
    claude: 'Claude',
    chatgpt: 'ChatGPT',
    gemini: 'Gemini',
  };
  return names[source] || 'Assistant';
}

/**
 * Creates the sticky search bar at the top of the chat container.
 * Returns an object with an initialize() method to wire up event listeners
 * after all bubbles have been rendered.
 */
function createSearchBar(container: HTMLElement, _settings: PluginSettings): { initialize: () => void } {
  const searchBar = container.createDiv({ cls: 'chat-search-bar' });

  const input = searchBar.createEl('input', {
    cls: 'chat-search-input',
    attr: { type: 'text', placeholder: 'Search in conversation...' },
  });

  const matchBadge = searchBar.createSpan({ cls: 'chat-search-badge' });
  matchBadge.style.display = 'none';

  const navContainer = searchBar.createDiv({ cls: 'chat-search-nav' });
  const prevBtn = navContainer.createEl('button', {
    cls: 'chat-search-nav-btn',
    attr: { 'aria-label': 'Previous match' },
  });
  prevBtn.textContent = '\u2191';
  const nextBtn = navContainer.createEl('button', {
    cls: 'chat-search-nav-btn',
    attr: { 'aria-label': 'Next match' },
  });
  nextBtn.textContent = '\u2193';
  navContainer.style.display = 'none';

  // Filter row
  const filterRow = searchBar.createDiv({ cls: 'chat-search-filters' });
  const filters = ['All', 'User', 'Assistant'] as const;
  let activeFilter: 'All' | 'User' | 'Assistant' = 'All';

  const filterButtons: HTMLButtonElement[] = [];
  for (const label of filters) {
    const btn = filterRow.createEl('button', {
      cls: `chat-filter-btn${label === 'All' ? ' chat-filter-active' : ''}`,
      text: label,
    });
    filterButtons.push(btn);
  }

  return {
    initialize() {
      let debounceTimer: ReturnType<typeof setTimeout> | null = null;
      let currentMatchIndex = 0;
      let matchElements: HTMLElement[] = [];

      const bubbles = container.querySelectorAll<HTMLElement>('.chat-bubble');

      // Filter button logic
      filterButtons.forEach((btn, idx) => {
        btn.addEventListener('click', () => {
          activeFilter = filters[idx];
          filterButtons.forEach(b => b.removeClass('chat-filter-active'));
          btn.addClass('chat-filter-active');
          applyFilter();
          performSearch(input.value);
        });
      });

      function applyFilter(): void {
        bubbles.forEach(bubble => {
          if (activeFilter === 'All') {
            bubble.style.display = '';
          } else if (activeFilter === 'User') {
            bubble.style.display = bubble.hasClass('chat-bubble-user') ? '' : 'none';
          } else {
            bubble.style.display = bubble.hasClass('chat-bubble-assistant') ? '' : 'none';
          }
        });
      }

      function clearHighlights(): void {
        // Convert to array first — DOM mutations during iteration can skip nodes
        Array.from(container.querySelectorAll('.chat-highlight')).forEach(mark => {
          const parent = mark.parentNode;
          if (parent) {
            parent.replaceChild(document.createTextNode(mark.textContent || ''), mark);
            parent.normalize();
          }
        });
        matchElements = [];
        currentMatchIndex = 0;
      }

      function performSearch(query: string): void {
        clearHighlights();

        if (!query.trim()) {
          matchBadge.style.display = 'none';
          navContainer.style.display = 'none';
          return;
        }

        const visibleBubbles = Array.from(bubbles).filter(b => b.style.display !== 'none');
        const lowerQuery = query.toLowerCase();

        for (const bubble of visibleBubbles) {
          const contentEl = bubble.querySelector('.chat-bubble-content');
          if (!contentEl) continue;
          highlightTextInElement(contentEl as HTMLElement, lowerQuery);
        }

        matchElements = Array.from(container.querySelectorAll<HTMLElement>('.chat-highlight'));
        const count = matchElements.length;

        if (count > 0) {
          matchBadge.textContent = `${count} match${count !== 1 ? 'es' : ''}`;
          matchBadge.style.display = '';
          navContainer.style.display = '';
          currentMatchIndex = 0;
          scrollToMatch(0);
        } else {
          matchBadge.textContent = 'No matches';
          matchBadge.style.display = '';
          navContainer.style.display = 'none';
        }
      }

      function scrollToMatch(index: number): void {
        matchElements.forEach(el => el.removeClass('chat-highlight-active'));
        if (matchElements[index]) {
          matchElements[index].addClass('chat-highlight-active');
          matchElements[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }

      // Debounced search input
      input.addEventListener('input', () => {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          // Guard against firing on detached DOM after view is closed
          if (!container.isConnected) return;
          performSearch(input.value);
        }, 200);
      });

      // Escape key clears search
      input.addEventListener('keydown', (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          input.value = '';
          clearHighlights();
          matchBadge.style.display = 'none';
          navContainer.style.display = 'none';
        } else if (e.key === 'Enter') {
          if (e.shiftKey) {
            navigatePrev();
          } else {
            navigateNext();
          }
        }
      });

      function navigateNext(): void {
        if (matchElements.length === 0) return;
        currentMatchIndex = (currentMatchIndex + 1) % matchElements.length;
        updateBadgePosition();
        scrollToMatch(currentMatchIndex);
      }

      function navigatePrev(): void {
        if (matchElements.length === 0) return;
        currentMatchIndex = (currentMatchIndex - 1 + matchElements.length) % matchElements.length;
        updateBadgePosition();
        scrollToMatch(currentMatchIndex);
      }

      function updateBadgePosition(): void {
        matchBadge.textContent = `${currentMatchIndex + 1}/${matchElements.length}`;
      }

      prevBtn.addEventListener('click', navigatePrev);
      nextBtn.addEventListener('click', navigateNext);
    },
  };
}

/**
 * Recursively highlights matching text within an element's text nodes.
 */
function highlightTextInElement(el: HTMLElement, query: string): void {
  if (query.length === 0) return;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodesToProcess: Text[] = [];

  let node: Node | null;
  while ((node = walker.nextNode())) {
    if (node.textContent && node.textContent.toLowerCase().includes(query)) {
      nodesToProcess.push(node as Text);
    }
  }

  for (const textNode of nodesToProcess) {
    const text = textNode.textContent || '';
    const lowerText = text.toLowerCase();
    const fragments = document.createDocumentFragment();
    let lastIndex = 0;

    let searchIndex = lowerText.indexOf(query, lastIndex);
    while (searchIndex !== -1) {
      // Text before match
      if (searchIndex > lastIndex) {
        fragments.appendChild(document.createTextNode(text.slice(lastIndex, searchIndex)));
      }
      // Highlighted match
      const mark = document.createElement('mark');
      mark.className = 'chat-highlight';
      mark.textContent = text.slice(searchIndex, searchIndex + query.length);
      fragments.appendChild(mark);
      lastIndex = searchIndex + query.length;
      searchIndex = lowerText.indexOf(query, lastIndex);
    }

    // Remaining text
    if (lastIndex < text.length) {
      fragments.appendChild(document.createTextNode(text.slice(lastIndex)));
    }

    if (textNode.parentNode) {
      textNode.parentNode.replaceChild(fragments, textNode);
    }
  }
}

/**
 * Processes code blocks within a content element:
 * - Adds copy button overlay
 * - Collapses blocks exceeding the configured line threshold
 */
function processCodeBlocks(contentEl: HTMLElement, settings: PluginSettings): void {
  const codeBlocks = contentEl.querySelectorAll<HTMLElement>('pre > code');

  codeBlocks.forEach(codeEl => {
    const preEl = codeEl.parentElement;
    if (!preEl) return;

    // Wrap in a relative container for positioning
    preEl.style.position = 'relative';

    // Copy button for code block
    const copyBtn = document.createElement('button');
    copyBtn.className = 'chat-code-copy-btn chat-message-actions';
    copyBtn.innerHTML = getCopyIcon();
    copyBtn.setAttribute('aria-label', 'Copy code');
    copyBtn.style.position = 'absolute';
    copyBtn.style.top = '4px';
    copyBtn.style.right = '4px';
    copyBtn.style.opacity = '0';
    copyBtn.style.transition = 'opacity 0.2s';

    preEl.addEventListener('mouseenter', () => { copyBtn.style.opacity = '1'; });
    preEl.addEventListener('mouseleave', () => { copyBtn.style.opacity = '0'; });

    copyBtn.addEventListener('click', () => {
      const codeText = codeEl.textContent || '';
      navigator.clipboard.writeText(codeText).then(() => {
        copyBtn.innerHTML = getCheckIcon();
        setTimeout(() => {
          copyBtn.innerHTML = getCopyIcon();
        }, 2000);
      }).catch(() => { /* clipboard permission denied — ignore silently */ });
    });

    preEl.appendChild(copyBtn);

    // Collapse logic: count lines
    const lines = (codeEl.textContent || '').split('\n');
    if (lines.length > settings.codeBlockCollapseLine) {
      preEl.style.maxHeight = `${settings.codeBlockCollapseLine * 1.5}em`;
      preEl.style.overflow = 'hidden';

      const toggle = document.createElement('div');
      toggle.className = 'chat-code-collapse-toggle';
      toggle.textContent = `Show more (${lines.length} lines)`;
      let expanded = false;

      toggle.addEventListener('click', () => {
        expanded = !expanded;
        if (expanded) {
          preEl.style.maxHeight = '';
          preEl.style.overflow = '';
          toggle.textContent = 'Show less';
        } else {
          preEl.style.maxHeight = `${settings.codeBlockCollapseLine * 1.5}em`;
          preEl.style.overflow = 'hidden';
          toggle.textContent = `Show more (${lines.length} lines)`;
        }
      });

      // Insert toggle after the pre element
      if (preEl.parentNode) {
        preEl.parentNode.insertBefore(toggle, preEl.nextSibling);
      }
    }
  });
}

/** SVG icon for the copy action */
function getCopyIcon(): string {
  return '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
}

/** SVG icon for the check/success state */
function getCheckIcon(): string {
  return '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
}
