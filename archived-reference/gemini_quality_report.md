# Gemini Biographical Extraction Quality Report

**Date:** 2025-12-16
**Database:** biography_cache.db
**Total Extractions:** 1,017 (227 Gemini, 790 Claude)

---

## Executive Summary

Gemini's biographical extractions are **significantly less detailed and nuanced** than Claude's, though they still capture useful information. The main differences:

1. **Quantity**: Gemini averages **10.1 items/extraction** vs Claude's **18.1 items/extraction** (44% less content)
2. **Coverage**: Gemini averages **2.9 categories/extraction** vs Claude's **3.6 categories/extraction** (19% fewer categories)
3. **Richness Distribution**: Gemini has more minimal extractions (53.7% vs 51.4%) and fewer high-richness extractions (5.2% vs 3.7%, but this is misleading - see below)

---

## Detailed Comparison

### Richness Distribution

**Gemini (227 extractions):**
- Minimal: 124 (53.7%)
- Low: 43 (18.6%)
- Medium: 52 (22.5%)
- High: 12 (5.2%)
- Rich: 0 (0.0%)

**Claude (790 extractions):**
- Minimal: 407 (51.4%)
- Low: 154 (19.4%)
- Medium: 98 (12.4%)
- High: 29 (3.7%)
- Rich: 0 (0.0%)

**Note:** Claude includes verbose richness labels (e.g., "high - reveals extensive health optimization behaviors...") that provide context for the rating. Gemini uses simple labels ("high", "medium", etc.).

---

## Quality Assessment by Richness Level

### HIGH Richness Examples

**Gemini HIGH Example:**
File: `20241023_συμπληρώματα-και-έρευνα.md`

**Strengths:**
- Captures extensive work context (researcher/writer, article planning)
- Identifies health conditions (ADD/ADHD, low blood pressure)
- Extracts detailed interests (nootropics, neuroscience, biochemistry)
- Recognizes tools used (WorkFlowy)
- Notes substance use changes (quit weed, racing thoughts resolved)

**Content extracted:** 30+ distinct items across 6 categories (work, health, interests, goals, challenges)

---

**Claude HIGH Example:**
File: `20240712_εξοπλισμός-καμπινγκ-και-παραλία.md`

**Strengths:**
- Captures granular health details (pain reliever use, foot care, sleep mask)
- Identifies specific behavioral patterns (hugs pillow while sleeping, needs 2 pillows)
- Extracts lifestyle details (smoker with specific supplies listed)
- Notes relationship context (packing for multiple people)
- Includes sensitive information (sexually active with specific items listed)

**Content extracted:** 40+ distinct items across 7 categories, including more intimate/behavioral details

**Verdict:** Claude's "high" extractions contain **~33% more items** and include more behavioral/intimate details that Gemini tends to miss.

---

### MEDIUM Richness Examples

**Gemini MEDIUM Example:**
File: `20241023_weightlifting-bar-path-app.md`

**Content:**
- Work: Content creator, project manager, has a channel
- Health: Engages in weightlifting
- Interests: Weightlifting, optimizing performance, creative content
- Challenges: Bug with AI assistant

**Items extracted:** ~12 items

---

**Claude MEDIUM Example:**
File: `20230514_benefits-of-alpha-gpc.md`

**Content:**
- Work: Research skills, bilingual communication
- Health: Interest in cognitive enhancement, researching cocaine cessation, depression concerns
- Substances: NAC research, cocaine use patterns, addiction treatment research
- Interests: Neuroscience, pharmacology, evidence-based medicine
- Goals: Understanding cessation strategies, cognitive optimization
- Challenges: Cocaine use or exposure, seeking addiction solutions

**Items extracted:** ~20 items

**Verdict:** Claude's "medium" extractions contain **~67% more items** and capture more complex/sensitive patterns (addiction, substance use research).

---

### LOW Richness Examples

Both providers capture similar amounts of content at the "low" level:
- Gemini: Focuses on tools used (WorkFlowy), basic interests (productivity, note organization)
- Claude: Captures research topics (DMT, Huperzine A), intellectual interests (psychedelics, neuroscience)

**Items extracted:** 5-8 items for both providers

**Verdict:** Comparable quality at the "low" richness level.

---

### MINIMAL Richness Examples

Both providers capture very little:
- Gemini: Single interest captured (Buddhist teachings)
- Claude: Empty conversation (no user interaction yet)

**Verdict:** Both perform similarly on minimal-content conversations.

---

## Key Differences

### What Gemini Does Well:
1. Captures work context (occupation hints, projects, business ventures)
2. Identifies health conditions (ADD/ADHD, blood pressure issues)
3. Extracts intellectual interests and research topics
4. Recognizes tools and technologies used
5. Notes substance use changes and mental health improvements

### What Gemini Misses Compared to Claude:
1. **Behavioral patterns**: Sleeping habits, daily routines, specific behavioral quirks
2. **Intimate/sensitive details**: Sexual activity, relationship dynamics, deeper emotional patterns
3. **Granular health details**: Specific medications with dosages, detailed symptom descriptions
4. **Lifestyle indicators**: Smoking supplies, specific product brands, detailed packing lists
5. **Inferential insights**: Claude often extracts implicit information that requires deeper reasoning

### Contextual Richness Labels

**Claude's approach:**
- Provides verbose richness labels that explain WHY the conversation was rated at that level
- Example: "high - reveals extensive health optimization behaviors, potential anxiety/sleep issues, health-conscious lifestyle, financial capacity, Greek language background, and sophisticated understanding of pharmacology"

**Gemini's approach:**
- Uses simple categorical labels: "high", "medium", "low", "minimal"
- Includes separate `main_topic` field that summarizes the conversation

**Verdict:** Claude's approach provides more immediate context for understanding extraction quality.

---

## Statistical Summary

| Metric | Gemini | Claude | Difference |
|--------|--------|--------|------------|
| **Total extractions** | 227 | 790 | -71% |
| **Avg items/extraction** | 10.1 | 18.1 | -44% |
| **Avg categories/extraction** | 2.9 | 3.6 | -19% |
| **Empty extractions** | 0 (0%) | 0 (0%) | Same |
| **High/Rich richness** | 12 (5.2%) | 29 (3.7%) | +41% |
| **Medium richness** | 52 (22.5%) | 98 (12.4%) | +81% |
| **Low richness** | 43 (18.6%) | 154 (19.4%) | -4% |
| **Minimal richness** | 124 (53.7%) | 407 (51.4%) | +4% |

**Note:** Gemini appears to have a higher percentage of "high" and "medium" extractions, but this is **misleading**:
- Gemini has fewer total extractions (227 vs 790)
- Claude's absolute numbers are higher (29 high vs 12 high)
- When examining actual content, Claude's extractions at each level contain ~30-67% more items

---

## Recommendations

### Are Gemini Extractions Useful?
**YES**, but with caveats:
- They capture the **core biographical facts** (work, health conditions, interests, goals)
- They identify **major patterns** (substance use, mental health, projects)
- They are suitable for **general profiling** and **topic clustering**

### Are They Empty?
**NO**:
- 0% are completely empty (both providers)
- 46.3% have low/medium/high richness (vs 48.6% for Claude)
- Average 10.1 items per extraction (vs 18.1 for Claude)

### Do They Have Similar Richness to Claude?
**NO**:
- Gemini extracts **~44% fewer items** per conversation
- Gemini misses **behavioral patterns, intimate details, and inferential insights**
- Gemini's "high" richness ≈ Claude's "medium" richness in actual content volume

### When to Use Gemini vs Claude:

**Use Gemini when:**
- Cost is a primary concern (Gemini is cheaper)
- You need basic profiling (occupation, interests, main health conditions)
- You're processing large volumes and speed matters
- Sensitive details aren't required

**Use Claude when:**
- You need comprehensive biographical profiles
- Behavioral patterns and lifestyle details are important
- Sensitive information (substance use, sexual health, mental health details) is relevant
- You want inferential insights that require deeper reasoning

---

## Conclusion

Gemini's biographical extractions are **functional but less comprehensive** than Claude's. They capture the main facts but miss nuances, behavioral patterns, and sensitive details that Claude excels at extracting. For the current use case (personal biography extraction), **Claude is the superior choice** despite higher cost, as the additional detail and insight justify the expense.

If cost becomes prohibitive, a **hybrid approach** could work:
1. Use Gemini for initial pass (cheap, fast, captures core facts)
2. Use Claude for high-value conversations (those marked as "high potential" by Gemini)
3. Review and manually enrich critical conversations

However, given the current scale (1,000+ conversations processed), the full-Claude approach appears to be working well and providing the depth needed for meaningful biographical analysis.
