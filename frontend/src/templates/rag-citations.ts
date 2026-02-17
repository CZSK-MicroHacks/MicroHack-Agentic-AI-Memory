/**
 * RAG Citations – A2UI Surface Template
 *
 * Renders knowledge base citations returned by the do_rag tool:
 *   Card → Column → header row, divider, dynamic citation list
 *
 * Data bindings:
 *   /citationCount  – e.g. "3 sources"
 *   /citations/N/annotation  – annotation tag  (e.g. 【0:return-policy_0†return-policy】)
 *   /citations/N/sourceName  – human-friendly source name
 *   /citations/N/snippet     – truncated content excerpt
 *
 * The citation list uses a data-bound template so the number of items is
 * determined at runtime from the data model — no hard-coded rows.
 */

import type { ComponentDef } from '../a2ui/types.js';

export const RAG_CITATIONS_TEMPLATE: ComponentDef[] = [
  /* ── Root card ───────────────────────────────────── */
  {
    id: 'root',
    component: {
      Card: { child: 'main-col' },
    },
  },
  {
    id: 'main-col',
    component: {
      Column: {
        children: {
          explicitList: ['header', 'divider', 'citation-list'],
        },
        gap: 'medium',
      },
    },
  },

  /* ── Header row ──────────────────────────────────── */
  {
    id: 'header',
    component: {
      Row: {
        children: { explicitList: ['header-icon', 'header-title', 'header-count'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  {
    id: 'header-icon',
    component: {
      Icon: { name: { literalString: 'menu_book' } },
    },
  },
  {
    id: 'header-title',
    component: {
      Text: { text: { literalString: 'Sources' }, usageHint: 'h3' },
    },
  },
  {
    id: 'header-count',
    component: {
      Text: { text: { path: '/citationCount' }, usageHint: 'caption' },
    },
  },

  /* ── Divider ─────────────────────────────────────── */
  {
    id: 'divider',
    component: { Divider: {} },
  },

  /* ── Citation list (data-bound template) ─────────── */
  {
    id: 'citation-list',
    component: {
      List: {
        direction: 'vertical',
        children: {
          template: {
            dataBinding: '/citations',
            componentId: 'citation-row',
          },
        },
      },
    },
  },

  /* ── Single citation row (reused per item) ───────── */
  {
    id: 'citation-row',
    component: {
      Row: {
        children: { explicitList: ['cite-icon', 'cite-details'] },
        gap: 'small',
        alignment: 'start',
      },
    },
  },
  {
    id: 'cite-icon',
    component: {
      Icon: { name: { literalString: 'description' } },
    },
  },
  {
    id: 'cite-details',
    component: {
      Column: {
        children: { explicitList: ['cite-source', 'cite-snippet'] },
        gap: 'small',
      },
    },
  },
  {
    id: 'cite-source',
    component: {
      Text: { text: { path: 'sourceName' }, usageHint: 'h5' },
    },
  },
  {
    id: 'cite-snippet',
    component: {
      Text: { text: { path: 'snippet' }, usageHint: 'caption' },
    },
  },
];
