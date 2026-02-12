/**
 * A2UI Message Processor
 *
 * Implements the client-side processing pipeline from the A2UI v0.8 spec:
 *   1. Buffer surfaceUpdate → component map per surface
 *   2. Buffer dataModelUpdate → data model per surface
 *   3. On beginRendering → mark surface ready to render
 *
 * This is a pure-data class with no rendering logic.
 */

import type {
  A2UIMessage,
  ComponentDef,
  DataEntry,
} from './types.js';

/* ── Surface State ─────────────────────────────────────────── */
export interface SurfaceState {
  /** Flat component map (id → ComponentDef) */
  components: Map<string, ComponentDef>;
  /** Nested data model (built from dataModelUpdate) */
  dataModel: Record<string, unknown>;
  /** Root component id (set by beginRendering) */
  rootId: string | null;
  /** Whether beginRendering has been received */
  ready: boolean;
}

/* ── Processor ─────────────────────────────────────────────── */
export class A2UIProcessor {
  private surfaces = new Map<string, SurfaceState>();

  /** Process a batch of A2UI messages. */
  processMessages(messages: A2UIMessage[]): void {
    for (const msg of messages) {
      this.processMessage(msg);
    }
  }

  /** Process a single A2UI message. */
  processMessage(msg: A2UIMessage): void {
    if ('surfaceUpdate' in msg) {
      const { surfaceId, components } = msg.surfaceUpdate;
      const surface = this.getOrCreateSurface(surfaceId);
      for (const comp of components) {
        surface.components.set(comp.id, comp);
      }
    } else if ('dataModelUpdate' in msg) {
      const { surfaceId, path, contents } = msg.dataModelUpdate;
      const surface = this.getOrCreateSurface(surfaceId);
      const target = path ? this.ensurePath(surface.dataModel, path) : surface.dataModel;
      this.applyContents(target, contents);
    } else if ('beginRendering' in msg) {
      const { surfaceId, root } = msg.beginRendering;
      const surface = this.getOrCreateSurface(surfaceId);
      surface.rootId = root;
      surface.ready = true;
    } else if ('deleteSurface' in msg) {
      this.surfaces.delete(msg.deleteSurface.surfaceId);
    }
  }

  /** Return all surfaces that are ready to render. */
  getReadySurfaces(): Map<string, SurfaceState> {
    const ready = new Map<string, SurfaceState>();
    for (const [id, s] of this.surfaces) {
      if (s.ready) ready.set(id, s);
    }
    return ready;
  }

  /** Clear all surfaces. */
  clear(): void {
    this.surfaces.clear();
  }

  /** Resolve a BoundValue path against a surface's data model. */
  resolveDataPath(surfaceId: string, path: string): unknown {
    const surface = this.surfaces.get(surfaceId);
    if (!surface) return undefined;

    // Paths look like "/user/name" — split on "/" and descend
    const parts = path.replace(/^\//, '').split('/').filter(Boolean);
    let current: unknown = surface.dataModel;
    for (const part of parts) {
      if (current == null || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }

  /* ── Private helpers ─────────────────────────────────────── */

  private getOrCreateSurface(surfaceId: string): SurfaceState {
    let s = this.surfaces.get(surfaceId);
    if (!s) {
      s = {
        components: new Map(),
        dataModel: {},
        rootId: null,
        ready: false,
      };
      this.surfaces.set(surfaceId, s);
    }
    return s;
  }

  /** Ensure nested object path exists and return the leaf object. */
  private ensurePath(root: Record<string, unknown>, path: string): Record<string, unknown> {
    const parts = path.replace(/^\//, '').split('/').filter(Boolean);
    let cur = root;
    for (const part of parts) {
      if (!(part in cur) || typeof cur[part] !== 'object') {
        cur[part] = {};
      }
      cur = cur[part] as Record<string, unknown>;
    }
    return cur;
  }

  /** Apply DataEntry[] (adjacency-list style) into a target object. */
  private applyContents(target: Record<string, unknown>, entries: DataEntry[]): void {
    for (const entry of entries) {
      if (entry.valueString !== undefined) {
        target[entry.key] = entry.valueString;
      } else if (entry.valueNumber !== undefined) {
        target[entry.key] = entry.valueNumber;
      } else if (entry.valueBoolean !== undefined) {
        target[entry.key] = entry.valueBoolean;
      } else if (entry.valueMap !== undefined) {
        const sub: Record<string, unknown> = (typeof target[entry.key] === 'object' && target[entry.key] !== null)
          ? target[entry.key] as Record<string, unknown>
          : {};
        this.applyContents(sub, entry.valueMap);
        target[entry.key] = sub;
      }
    }
  }
}
