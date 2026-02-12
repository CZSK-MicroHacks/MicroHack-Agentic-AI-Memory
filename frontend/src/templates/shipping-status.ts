/**
 * Shipping Status – A2UI Surface Template
 *
 * Declarative component definition using only standard A2UI catalog components:
 * Card, Column, Row, Text, Icon, Divider.
 *
 * Data bindings:
 *   /trackingNumber   – e.g. "Tracking: 1Z999AA10123456784"
 *   /currentStepIcon  – Material Symbol name for the active step (e.g. "local_shipping")
 *   /eta              – e.g. "Estimated delivery: Today by 8 PM"
 *
 * This JSON definition is consumed by the template inflater in converters.ts
 * and rendered by the generic <a2ui-surface> renderer — zero custom widget code.
 */

import type { ComponentDef } from '../a2ui/types.js';

export const SHIPPING_STATUS_TEMPLATE: ComponentDef[] = [
  {
    id: 'root',
    component: {
      Card: { child: 'main-column' },
    },
  },
  {
    id: 'main-column',
    component: {
      Column: {
        children: {
          explicitList: ['header', 'tracking-number', 'divider', 'steps', 'eta'],
        },
        gap: 'medium',
      },
    },
  },

  /* ── Header ──────────────────────────────────────── */
  {
    id: 'header',
    component: {
      Row: {
        children: { explicitList: ['package-icon', 'title'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  {
    id: 'package-icon',
    component: {
      Icon: { name: { literalString: 'package_2' } },
    },
  },
  {
    id: 'title',
    component: {
      Text: { text: { literalString: 'Package Status' }, usageHint: 'h3' },
    },
  },

  /* ── Tracking number (data-bound) ────────────────── */
  {
    id: 'tracking-number',
    component: {
      Text: { text: { path: '/trackingNumber' }, usageHint: 'caption' },
    },
  },

  /* ── Divider ─────────────────────────────────────── */
  {
    id: 'divider',
    component: { Divider: {} },
  },

  /* ── Steps ───────────────────────────────────────── */
  {
    id: 'steps',
    component: {
      Column: {
        children: { explicitList: ['step1', 'step2', 'step3', 'step4'] },
        gap: 'small',
      },
    },
  },

  // Step 1 – Order Placed (completed)
  {
    id: 'step1',
    component: {
      Row: {
        children: { explicitList: ['step1-icon', 'step1-text'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  { id: 'step1-icon', component: { Icon: { name: { literalString: 'check_circle' } } } },
  { id: 'step1-text', component: { Text: { text: { literalString: 'Order Placed' }, usageHint: 'body' } } },

  // Step 2 – Shipped (completed)
  {
    id: 'step2',
    component: {
      Row: {
        children: { explicitList: ['step2-icon', 'step2-text'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  { id: 'step2-icon', component: { Icon: { name: { literalString: 'check_circle' } } } },
  { id: 'step2-text', component: { Text: { text: { literalString: 'Shipped' }, usageHint: 'body' } } },

  // Step 3 – Out for Delivery (active, icon data-bound)
  {
    id: 'step3',
    component: {
      Row: {
        children: { explicitList: ['step3-icon', 'step3-text'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  { id: 'step3-icon', component: { Icon: { name: { path: '/currentStepIcon' } } } },
  { id: 'step3-text', component: { Text: { text: { literalString: 'Out for Delivery' }, usageHint: 'h4' } } },

  // Step 4 – Delivered (pending)
  {
    id: 'step4',
    component: {
      Row: {
        children: { explicitList: ['step4-icon', 'step4-text'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  { id: 'step4-icon', component: { Icon: { name: { literalString: 'circle' } } } },
  { id: 'step4-text', component: { Text: { text: { literalString: 'Delivered' }, usageHint: 'caption' } } },

  /* ── ETA (data-bound) ────────────────────────────── */
  {
    id: 'eta',
    component: {
      Row: {
        children: { explicitList: ['eta-icon', 'eta-text'] },
        gap: 'small',
        alignment: 'center',
      },
    },
  },
  { id: 'eta-icon', component: { Icon: { name: { literalString: 'schedule' } } } },
  { id: 'eta-text', component: { Text: { text: { path: '/eta' }, usageHint: 'body' } } },
];
