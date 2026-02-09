import { Plugin, PluginSettingTab, Setting, App, Notice } from 'obsidian';
import type { PluginSettings } from './types';
import { DEFAULT_SETTINGS } from './types';
import { VIEW_TYPE_AI_CONVERSATIONS } from './constants';
import ConversationIndex from './index/ConversationIndex';
import { registerChatRenderer } from './renderer/ChatRenderer';
import SidebarView from './sidebar/SidebarView';

export default class AIConversationsPlugin extends Plugin {
  settings!: PluginSettings;
  index!: ConversationIndex;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.index = new ConversationIndex(this.app, this.settings);

    if (this.settings.enableRenderer) {
      registerChatRenderer(this, this.settings);
    }

    this.registerView(
      VIEW_TYPE_AI_CONVERSATIONS,
      (leaf) => new SidebarView(leaf, this.index, this.app)
    );

    this.addRibbonIcon('messages-square', 'AI Conversations', () => {
      this.activateSidebarView();
    });

    this.addCommand({
      id: 'open-ai-conversations',
      name: 'Open AI Conversations',
      callback: () => this.activateSidebarView(),
    });

    this.addSettingTab(new AIConversationsSettingTab(this.app, this));

    this.app.workspace.onLayoutReady(async () => {
      await this.index.initialize();
    });
  }

  onunload(): void {
    this.index?.destroy();
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  async activateSidebarView(): Promise<void> {
    const { workspace } = this.app;

    let leaf = workspace.getLeavesOfType(VIEW_TYPE_AI_CONVERSATIONS)[0];
    if (!leaf) {
      const rightLeaf = workspace.getRightLeaf(false);
      if (rightLeaf) {
        leaf = rightLeaf;
        await leaf.setViewState({
          type: VIEW_TYPE_AI_CONVERSATIONS,
          active: true,
        });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
    } else {
      new Notice('Could not open AI Conversations panel. Try opening the right sidebar first.');
    }
  }
}

class AIConversationsSettingTab extends PluginSettingTab {
  plugin: AIConversationsPlugin;

  constructor(app: App, plugin: AIConversationsPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl('h2', { text: 'AI Conversations Settings' });

    new Setting(containerEl)
      .setName('Conversation folder')
      .setDesc('Path to the folder containing conversation files. Leave empty to scan the entire vault.')
      .addText((text) =>
        text
          .setPlaceholder('e.g. AI Conversations')
          .setValue(this.plugin.settings.conversationFolder)
          .onChange(async (value) => {
            this.plugin.settings.conversationFolder = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Enable chat renderer')
      .setDesc('Render conversation files as chat bubbles in Reading View.')
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.enableRenderer)
          .onChange(async (value) => {
            this.plugin.settings.enableRenderer = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Enable sidebar panel')
      .setDesc('Show the AI Conversations sidebar panel with Browse, Search, and Stats tabs.')
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.enableSidebar)
          .onChange(async (value) => {
            this.plugin.settings.enableSidebar = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Code block collapse threshold')
      .setDesc('Collapse code blocks with more than this many lines. Set to 0 to disable.')
      .addText((text) =>
        text
          .setPlaceholder('15')
          .setValue(String(this.plugin.settings.codeBlockCollapseLine))
          .onChange(async (value) => {
            const num = parseInt(value, 10);
            if (!isNaN(num) && num >= 0) {
              this.plugin.settings.codeBlockCollapseLine = num;
              await this.plugin.saveSettings();
            }
          })
      );

    new Setting(containerEl)
      .setName('Build search index on startup')
      .setDesc('Automatically build the full-text search index when the plugin loads.')
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.searchIndexOnStartup)
          .onChange(async (value) => {
            this.plugin.settings.searchIndexOnStartup = value;
            await this.plugin.saveSettings();
          })
      );
  }
}
