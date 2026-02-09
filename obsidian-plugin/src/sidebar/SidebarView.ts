import { ItemView, WorkspaceLeaf, App } from 'obsidian';
import { VIEW_TYPE_AI_CONVERSATIONS } from '../constants';
import type ConversationIndex from '../index/ConversationIndex';
import { BrowseView } from './BrowseView';
import { SearchView } from './SearchView';
import { AnalyticsView } from './AnalyticsView';
import type { TabComponent } from '../types';

type TabName = 'browse' | 'search' | 'stats';

interface TabDef {
  name: TabName;
  label: string;
}

const TABS: TabDef[] = [
  { name: 'browse', label: 'Browse' },
  { name: 'search', label: 'Search' },
  { name: 'stats', label: 'Stats' },
];

export default class SidebarView extends ItemView {
  private index: ConversationIndex;
  private appRef: App;

  private tabs: Map<TabName, TabComponent> = new Map();
  private tabContainers: Map<TabName, HTMLElement> = new Map();
  private tabButtons: Map<TabName, HTMLElement> = new Map();
  private renderedTabs: Set<TabName> = new Set();
  private activeTab: TabName = 'browse';

  private indexReadyHandler: (() => void) | null = null;

  constructor(leaf: WorkspaceLeaf, index: ConversationIndex, app: App) {
    super(leaf);
    this.index = index;
    this.appRef = app;
  }

  getViewType(): string {
    return VIEW_TYPE_AI_CONVERSATIONS;
  }

  getDisplayText(): string {
    return 'AI Conversations';
  }

  getIcon(): string {
    return 'messages-square';
  }

  async onOpen(): Promise<void> {
    const contentEl = this.containerEl.children[1] as HTMLElement;
    contentEl.empty();
    contentEl.style.display = 'flex';
    contentEl.style.flexDirection = 'column';
    contentEl.style.height = '100%';

    // Tab bar
    const tabBar = contentEl.createDiv({ cls: 'sidebar-tab-bar' });

    for (const tabDef of TABS) {
      const btn = tabBar.createEl('button', {
        cls: `sidebar-tab-btn${tabDef.name === this.activeTab ? ' active' : ''}`,
        text: tabDef.label,
      });
      btn.addEventListener('click', () => this.switchTab(tabDef.name));
      this.tabButtons.set(tabDef.name, btn);
    }

    // Content wrapper
    const contentWrapper = contentEl.createDiv({ cls: 'sidebar-tab-content' });

    // Create containers for each tab
    for (const tabDef of TABS) {
      const container = contentWrapper.createDiv({ cls: 'sidebar-tab-panel' });
      container.style.display = tabDef.name === this.activeTab ? '' : 'none';
      this.tabContainers.set(tabDef.name, container);
    }

    // Instantiate tab components
    const browseContainer = this.tabContainers.get('browse')!;
    const searchContainer = this.tabContainers.get('search')!;
    const statsContainer = this.tabContainers.get('stats')!;

    const browseView = new BrowseView(browseContainer, this.index, this.appRef);
    const searchView = new SearchView(searchContainer, this.index, this.appRef);
    const analyticsView = new AnalyticsView(statsContainer, this.index);

    this.tabs.set('browse', browseView);
    this.tabs.set('search', searchView);
    this.tabs.set('stats', analyticsView);

    // Render the default active tab
    browseView.render();
    this.renderedTabs.add('browse');

    // Listen for index-ready event to notify all tabs
    this.indexReadyHandler = () => {
      for (const tab of this.tabs.values()) {
        if (tab.onIndexReady) {
          tab.onIndexReady();
        }
      }
    };
    this.index.on('index-ready', this.indexReadyHandler);
  }

  async onClose(): Promise<void> {
    // Unregister index listener
    if (this.indexReadyHandler) {
      this.index.off('index-ready', this.indexReadyHandler);
      this.indexReadyHandler = null;
    }

    // Destroy all tab components
    for (const tab of this.tabs.values()) {
      tab.destroy();
    }

    this.tabs.clear();
    this.tabContainers.clear();
    this.tabButtons.clear();
    this.renderedTabs.clear();
  }

  private switchTab(name: TabName): void {
    if (name === this.activeTab) return;

    // Update button states
    for (const [tabName, btn] of this.tabButtons.entries()) {
      if (tabName === name) {
        btn.addClass('active');
      } else {
        btn.removeClass('active');
      }
    }

    // Hide all containers, show selected
    for (const [tabName, container] of this.tabContainers.entries()) {
      container.style.display = tabName === name ? '' : 'none';
    }

    // Render the tab if it hasn't been rendered yet
    if (!this.renderedTabs.has(name)) {
      const tab = this.tabs.get(name);
      if (tab) {
        tab.render();
        this.renderedTabs.add(name);
      }
    }

    this.activeTab = name;
  }
}
