/**
 * Tool-Result → A2UI Message Converters
 *
 * Each converter takes a tool name, its JSON result, and produces an array of
 * A2UI messages (surfaceUpdate + dataModelUpdate + beginRendering) that the
 * native A2UI renderer can display.
 *
 * KEY IDEA #1: The backend sends raw JSON tool results, and the frontend
 * converts them into A2UI component trees on the fly.
 *
 * KEY IDEA #2: We use **declarative A2UI surface templates** (JSON arrays of
 * standard ComponentDefs) so that adding new visualisations requires zero
 * custom rendering code — just a template + a data mapper.
 */

import type { A2UIMessage, ComponentDef, DataEntry } from './a2ui/types.js';
import { SHIPPING_STATUS_TEMPLATE } from './templates/shipping-status.js';

/* ────────────────────────────────────────────────────────────
 * Template inflater
 *
 * Takes a reusable A2UI surface template (ComponentDef[]) and a flat
 * data-model object, then produces the three A2UI messages that the
 * processor/renderer need:  surfaceUpdate → dataModelUpdate → beginRendering.
 * ──────────────────────────────────────────────────────────── */

function inflateSurfaceTemplate(
  template: ComponentDef[],
  dataModel: Record<string, unknown>,
  surfaceId: string,
  rootId = 'root',
): A2UIMessage[] {
  // Build DataEntry[] from flat key/value object
  const contents: DataEntry[] = Object.entries(dataModel).map(([key, value]) => {
    if (typeof value === 'string')  return { key, valueString: value };
    if (typeof value === 'number')  return { key, valueNumber: value };
    if (typeof value === 'boolean') return { key, valueBoolean: value };
    // Nested objects → recursive valueMap
    if (typeof value === 'object' && value !== null) {
      return { key, valueMap: objectToDataEntries(value as Record<string, unknown>) };
    }
    return { key, valueString: String(value) };
  });

  return [
    { surfaceUpdate: { surfaceId, components: template } },
    { dataModelUpdate: { surfaceId, contents } },
    { beginRendering: { surfaceId, root: rootId } },
  ];
}

function objectToDataEntries(obj: Record<string, unknown>): DataEntry[] {
  return Object.entries(obj).map(([key, value]) => {
    if (typeof value === 'string')  return { key, valueString: value };
    if (typeof value === 'number')  return { key, valueNumber: value };
    if (typeof value === 'boolean') return { key, valueBoolean: value };
    if (typeof value === 'object' && value !== null) {
      return { key, valueMap: objectToDataEntries(value as Record<string, unknown>) };
    }
    return { key, valueString: String(value) };
  });
}

/* ────────────────────────────────────────────────────────────
 * Converter registry
 * ──────────────────────────────────────────────────────────── */

/** Registry of converters keyed by tool name. */
const converters = new Map<string, (result: unknown, surfaceId: string) => A2UIMessage[]>();

/**
 * Attempt to convert a tool result into A2UI messages.
 * Returns null if no converter exists for this tool.
 */
export function convertToolResult(
  toolName: string,
  resultJson: string,
  surfaceId: string,
): A2UIMessage[] | null {
  const converter = converters.get(toolName);
  if (!converter) return null;

  try {
    const data = JSON.parse(resultJson);
    return converter(data, surfaceId);
  } catch {
    return null;
  }
}

/* ────────────────────────────────────────────────────────────
 * get_order_status converter  →  Shipping Status template
 *
 * The backend already returns the data model in the shape the
 * template expects ({ trackingNumber, currentStepIcon, eta }),
 * so this is a pure pass-through — zero mapping code.
 * ──────────────────────────────────────────────────────────── */

converters.set('get_order_status', (result: unknown, surfaceId: string): A2UIMessage[] => {
  return inflateSurfaceTemplate(
    SHIPPING_STATUS_TEMPLATE,
    result as Record<string, unknown>,
    surfaceId,
  );
});

/* ────────────────────────────────────────────────────────────
 * Generic fallback converter
 *
 * For any tool without a specialised converter, renders the raw
 * JSON result inside a Card with a Text component.
 * ──────────────────────────────────────────────────────────── */

export function convertGenericResult(
  toolName: string,
  resultJson: string,
  surfaceId: string,
): A2UIMessage[] {
  let displayText: string;
  try {
    const parsed = JSON.parse(resultJson);
    displayText = JSON.stringify(parsed, null, 2);
  } catch {
    displayText = resultJson;
  }

  const components: ComponentDef[] = [
    {
      id: 'root',
      component: { Card: { child: 'card-content' } },
    },
    {
      id: 'card-content',
      component: {
        Column: { children: { explicitList: ['tool-header', 'tool-divider', 'tool-result'] } },
      },
    },
    {
      id: 'tool-header',
      component: {
        Row: {
          alignment: 'center',
          children: { explicitList: ['tool-icon', 'tool-name'] },
        },
      },
    },
    {
      id: 'tool-icon',
      component: { Icon: { name: { literalString: 'info' } } },
    },
    {
      id: 'tool-name',
      component: {
        Text: { text: { literalString: toolName }, usageHint: 'h4' },
      },
    },
    {
      id: 'tool-divider',
      component: { Divider: { axis: 'horizontal' } },
    },
    {
      id: 'tool-result',
      component: {
        Text: { text: { literalString: displayText }, usageHint: 'body' },
      },
    },
  ];

  return [
    { surfaceUpdate: { surfaceId, components } },
    { dataModelUpdate: { surfaceId, contents: [] } },
    { beginRendering: { surfaceId, root: 'root' } },
  ];
}
