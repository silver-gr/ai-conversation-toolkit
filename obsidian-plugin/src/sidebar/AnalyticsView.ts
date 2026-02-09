import type ConversationIndex from '../index/ConversationIndex';
import type { TabComponent, ConversationStats } from '../types';

/** Platform colors matching plugin settings defaults */
const PLATFORM_COLORS: Record<string, string> = {
  claude: '#d97706',
  chatgpt: '#10b981',
  gemini: '#3b82f6',
};

/**
 * AnalyticsView renders aggregate statistics and charts
 * for the conversation index, using pure CSS visualizations.
 */
export class AnalyticsView implements TabComponent {
  containerEl: HTMLElement;
  private index: ConversationIndex;
  private contentEl: HTMLElement | null = null;
  private entriesChangedCallback: (() => void) | null = null;

  constructor(containerEl: HTMLElement, index: ConversationIndex) {
    this.containerEl = containerEl;
    this.index = index;
  }

  render(): void {
    this.containerEl.empty();

    const wrapper = this.containerEl.createDiv({ cls: 'analytics-container' });
    this.contentEl = wrapper;

    // Register for live updates
    this.entriesChangedCallback = () => {
      const stats = this.index.getStats();
      this.renderStats(stats);
    };
    this.index.on('entries-changed', this.entriesChangedCallback);

    const stats = this.index.getStats();
    this.renderStats(stats);
  }

  destroy(): void {
    if (this.entriesChangedCallback) {
      this.index.off('entries-changed', this.entriesChangedCallback);
      this.entriesChangedCallback = null;
    }
    this.contentEl = null;
    this.containerEl.empty();
  }

  onIndexReady(): void {
    const stats = this.index.getStats();
    this.renderStats(stats);
  }

  private renderStats(stats: ConversationStats): void {
    if (!this.contentEl) return;
    this.contentEl.empty();

    // Empty state
    if (stats.total === 0) {
      const emptyEl = this.contentEl.createDiv({ cls: 'analytics-empty' });
      emptyEl.setText('No data available');
      return;
    }

    this.renderSummary(stats);
    this.renderPlatformDistribution(stats);
    this.renderMonthlyActivity(stats);
    this.renderAverageMessages(stats);
    this.renderTopTopics(stats);
  }

  // ─── Summary Cards ───────────────────────────────────────────────────────

  private renderSummary(stats: ConversationStats): void {
    if (!this.contentEl) return;

    const section = this.contentEl.createDiv({ cls: 'analytics-summary' });

    this.createStatCard(section, stats.total.toLocaleString(), 'Total Conversations');
    this.createStatCard(section, stats.totalMessages.toLocaleString(), 'Total Messages');
    this.createStatCard(section, stats.totalCharacters.toLocaleString(), 'Total Characters');
  }

  private createStatCard(parent: HTMLElement, value: string, label: string): void {
    const card = parent.createDiv({ cls: 'analytics-stat-card' });
    const numberEl = card.createDiv({ cls: 'analytics-stat-number' });
    numberEl.setText(value);
    const labelEl = card.createDiv({ cls: 'analytics-stat-label' });
    labelEl.setText(label);
  }

  // ─── Platform Distribution ────────────────────────────────────────────────

  private renderPlatformDistribution(stats: ConversationStats): void {
    if (!this.contentEl) return;

    const section = this.contentEl.createDiv({ cls: 'analytics-platform-chart' });
    const header = section.createDiv({ cls: 'analytics-section-header' });
    header.setText('Platform Distribution');

    const total = stats.total;
    const entries = Object.entries(stats.bySource).sort((a, b) => b[1] - a[1]);

    for (const [platform, count] of entries) {
      const pct = total > 0 ? (count / total) * 100 : 0;

      const row = section.createDiv({ cls: 'analytics-bar-row' });

      // Label: platform name + count
      const label = row.createDiv({ cls: 'analytics-bar-label' });
      const nameSpan = label.createSpan();
      nameSpan.setText(this.capitalize(platform));
      const countSpan = label.createSpan();
      countSpan.setText(count.toLocaleString());

      // Bar wrapper with colored bar inside
      const barWrapper = row.createDiv({ cls: 'analytics-bar-wrapper' });
      const bar = barWrapper.createDiv({ cls: 'analytics-bar' });
      bar.style.width = `${pct}%`;
      bar.style.backgroundColor = PLATFORM_COLORS[platform] ?? 'var(--interactive-accent)';

      // Percentage
      const pctEl = row.createDiv({ cls: 'analytics-bar-pct' });
      pctEl.setText(`${Math.round(pct)}%`);
    }
  }

  // ─── Monthly Activity ─────────────────────────────────────────────────────

  private renderMonthlyActivity(stats: ConversationStats): void {
    if (!this.contentEl) return;
    if (stats.byMonth.length === 0) return;

    const section = this.contentEl.createDiv();
    const header = section.createDiv({ cls: 'analytics-section-header' });
    header.setText('Monthly Activity');

    const chartContainer = section.createDiv({ cls: 'analytics-monthly-chart' });

    const maxCount = Math.max(...stats.byMonth.map((m) => m.count));

    for (const { month, count } of stats.byMonth) {
      const heightPct = maxCount > 0 ? (count / maxCount) * 100 : 0;

      const bar = chartContainer.createDiv({ cls: 'analytics-monthly-bar' });
      bar.style.height = `${heightPct}%`;
      bar.setAttribute('title', `${month}: ${count.toLocaleString()} conversations`);
      bar.setAttribute('aria-label', `${month}: ${count} conversations`);
    }
  }

  // ─── Average Messages ─────────────────────────────────────────────────────

  private renderAverageMessages(stats: ConversationStats): void {
    if (!this.contentEl) return;

    const entries = Object.entries(stats.avgMessagesBySource);
    if (entries.length === 0) return;

    const section = this.contentEl.createDiv();
    const header = section.createDiv({ cls: 'analytics-section-header' });
    header.setText('Average Messages');

    const container = section.createDiv({ cls: 'analytics-averages' });

    for (const [platform, avg] of entries.sort((a, b) => b[1] - a[1])) {
      const item = container.createDiv({ cls: 'analytics-avg-item' });

      const dot = item.createDiv({ cls: 'analytics-avg-dot' });
      dot.style.backgroundColor = PLATFORM_COLORS[platform] ?? 'var(--interactive-accent)';

      const text = item.createSpan();
      text.setText(`${this.capitalize(platform)} ${avg} msgs`);
    }
  }

  // ─── Top Topics ───────────────────────────────────────────────────────────

  private renderTopTopics(stats: ConversationStats): void {
    if (!this.contentEl) return;

    const topics = stats.topTopics.slice(0, 15);
    if (topics.length === 0) return;

    const section = this.contentEl.createDiv({ cls: 'analytics-topics-section' });
    const header = section.createDiv({ cls: 'analytics-section-header' });
    header.setText('Top Topics');

    for (let i = 0; i < topics.length; i++) {
      const { topic, count } = topics[i];

      const item = section.createDiv({ cls: 'analytics-topic-item' });

      const rank = item.createDiv({ cls: 'analytics-topic-rank' });
      rank.setText(`${i + 1}`);

      const name = item.createDiv({ cls: 'analytics-topic-name' });
      name.setText(topic);

      const badge = item.createDiv({ cls: 'analytics-topic-count' });
      badge.setText(count.toLocaleString());
    }
  }

  // ─── Utilities ────────────────────────────────────────────────────────────

  private capitalize(str: string): string {
    if (!str) return str;
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
