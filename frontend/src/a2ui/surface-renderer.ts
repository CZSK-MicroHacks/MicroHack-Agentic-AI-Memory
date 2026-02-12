/**
 * <a2ui-surface> – A2UI Native Surface Renderer
 *
 * A Lit web component that takes an A2UI SurfaceState and recursively renders
 * the component tree using native HTML elements styled to match the A2UI
 * standard catalog (Card, Column, Row, Text, Icon, Button, Image, Divider, List).
 *
 * This is intentionally lightweight — no heavy framework, just the spec.
 */

import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { SurfaceState } from './processor.js';
import type { ComponentDef, BoundValue, ChildrenDef, ComponentAction } from './types.js';

@customElement('a2ui-surface')
export class A2UISurface extends LitElement {
  @property({ type: Object })
  surface: SurfaceState | null = null;

  @property({ type: String })
  surfaceId = '';

  static styles = css`
    /* Material Symbols – must be declared inside Shadow DOM */
    .material-symbols-outlined {
      font-family: 'Material Symbols Outlined';
      font-weight: normal;
      font-style: normal;
      font-size: 24px;
      line-height: 1;
      letter-spacing: normal;
      text-transform: none;
      display: inline-block;
      white-space: nowrap;
      word-wrap: normal;
      direction: ltr;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
      font-feature-settings: 'liga';
    }

    :host {
      display: block;
      width: 100%;
    }

    /* ── Card ─────────────────────────────────────────── */
    .a2ui-card {
      background: light-dark(var(--n-100, #fff), var(--n-20, #2d2d3a));
      border: 1px solid light-dark(var(--n-90, #d9d9e3), var(--n-25, #3a3b44));
      border-radius: 12px;
      overflow: hidden;
    }

    /* ── Column ───────────────────────────────────────── */
    .a2ui-column {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .a2ui-column.gap-small  { gap: 4px; }
    .a2ui-column.gap-medium { gap: 10px; }
    .a2ui-column.gap-large  { gap: 16px; }

    /* ── Row ───────────────────────────────────────────── */
    .a2ui-row {
      display: flex;
      flex-direction: row;
      gap: 10px;
      align-items: center;
    }
    .a2ui-row.gap-small  { gap: 6px; }
    .a2ui-row.gap-medium { gap: 10px; }
    .a2ui-row.gap-large  { gap: 16px; }
    .a2ui-row.align-start   { align-items: flex-start; }
    .a2ui-row.align-center  { align-items: center; }
    .a2ui-row.align-end     { align-items: flex-end; }
    .a2ui-row.align-stretch { align-items: stretch; }

    .a2ui-row.dist-spaceBetween { justify-content: space-between; }
    .a2ui-row.dist-spaceAround  { justify-content: space-around; }
    .a2ui-row.dist-spaceEvenly  { justify-content: space-evenly; }
    .a2ui-row.dist-center        { justify-content: center; }
    .a2ui-row.dist-end           { justify-content: flex-end; }

    /* ── List ──────────────────────────────────────────── */
    .a2ui-list {
      display: flex;
      gap: 10px;
      padding: 4px;
    }
    .a2ui-list.vertical   { flex-direction: column; }
    .a2ui-list.horizontal { flex-direction: row; flex-wrap: wrap; }

    /* ── Text ──────────────────────────────────────────── */
    .a2ui-text {
      margin: 0;
      font-family: var(--font-family, 'Inter', -apple-system, sans-serif);
      color: light-dark(var(--n-10, #171717), var(--n-90, #e2e2e2));
      line-height: 1.5;
      word-break: break-word;
    }
    .a2ui-text.h1 { font-size: 20px; font-weight: 600; }
    .a2ui-text.h2 { font-size: 17px; font-weight: 600; }
    .a2ui-text.h3 { font-size: 15px; font-weight: 600; }
    .a2ui-text.h4 { font-size: 14px; font-weight: 600; }
    .a2ui-text.h5 { font-size: 13px; font-weight: 600; }
    .a2ui-text.body   { font-size: 13px; font-weight: 400; }
    .a2ui-text.caption { font-size: 12px; font-weight: 400; color: light-dark(var(--n-50), var(--n-60)); }

    /* ── Icon ──────────────────────────────────────────── */
    .a2ui-icon {
      font-family: 'Material Symbols Outlined';
      font-weight: normal;
      font-style: normal;
      font-size: 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: light-dark(var(--n-50), var(--n-60));
    }

    /* ── Image ─────────────────────────────────────────── */
    .a2ui-image {
      max-width: 100%;
      border-radius: 8px;
      object-fit: cover;
    }

    /* ── Button ────────────────────────────────────────── */
    .a2ui-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 6px 14px;
      border: none;
      border-radius: 8px;
      font-family: var(--font-family, 'Inter', -apple-system, sans-serif);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s, transform 0.1s;
    }
    .a2ui-button:active { transform: scale(0.97); }
    .a2ui-button.primary {
      background: light-dark(var(--n-10, #171717), var(--n-90, #e2e2e2));
      color: light-dark(var(--n-100, #fff), var(--n-10, #171717));
    }
    .a2ui-button.primary:hover {
      opacity: 0.85;
    }
    .a2ui-button.secondary {
      background: transparent;
      color: light-dark(var(--n-30), var(--n-80));
      border: 1px solid light-dark(var(--n-90), var(--n-30));
    }
    .a2ui-button.secondary:hover {
      background: light-dark(var(--n-98), var(--n-20));
    }

    /* ── Divider ───────────────────────────────────────── */
    .a2ui-divider {
      border: none;
      margin: 4px 0;
    }
    .a2ui-divider.horizontal {
      border-top: 1px solid light-dark(var(--n-90), var(--n-25));
    }
    .a2ui-divider.vertical {
      border-left: 1px solid light-dark(var(--n-90), var(--n-25));
      align-self: stretch;
    }

    /* ── Padding helper for card child ─────────────────── */
    .a2ui-card-body {
      padding: 14px 16px;
    }
  `;

  render() {
    if (!this.surface || !this.surface.ready || !this.surface.rootId) {
      return nothing;
    }
    return this.renderComponent(this.surface.rootId);
  }

  /* ── Recursive component renderer ───────────────────── */

  private renderComponent(id: string, dataContextPath?: string): TemplateResult | typeof nothing {
    if (!this.surface) return nothing;
    const def = this.surface.components.get(id);
    if (!def) return nothing;

    const c = def.component;

    if (c.Column)  return this.renderColumn(c.Column, dataContextPath);
    if (c.Row)     return this.renderRow(c.Row, dataContextPath);
    if (c.Card)    return this.renderCard(c.Card, dataContextPath);
    if (c.Text)    return this.renderText(c.Text, dataContextPath);
    if (c.Icon)    return this.renderIcon(c.Icon, dataContextPath);
    if (c.Image)   return this.renderImage(c.Image, dataContextPath);
    if (c.Button)  return this.renderButton(c.Button, dataContextPath);
    if (c.List)    return this.renderList(c.List, dataContextPath);
    if (c.Divider) return this.renderDivider(c.Divider);

    return html`<span>[unknown component]</span>`;
  }

  /* ── Individual renderers ───────────────────────────── */

  private renderColumn(col: NonNullable<ComponentDef['component']['Column']>, ctx?: string) {
    const gapCls = col.gap ? `gap-${col.gap}` : '';
    return html`
      <div class="a2ui-column ${gapCls}">
        ${this.renderChildren(col.children, ctx)}
      </div>
    `;
  }

  private renderRow(row: NonNullable<ComponentDef['component']['Row']>, ctx?: string) {
    const alignCls = row.alignment ? `align-${row.alignment}` : '';
    const distCls  = row.distribution ? `dist-${row.distribution}` : '';
    const gapCls   = row.gap ? `gap-${row.gap}` : '';
    return html`
      <div class="a2ui-row ${alignCls} ${distCls} ${gapCls}">
        ${this.renderChildren(row.children, ctx)}
      </div>
    `;
  }

  private renderCard(card: NonNullable<ComponentDef['component']['Card']>, ctx?: string) {
    return html`
      <div class="a2ui-card">
        <div class="a2ui-card-body">
          ${this.renderComponent(card.child, ctx)}
        </div>
      </div>
    `;
  }

  private renderText(text: NonNullable<ComponentDef['component']['Text']>, ctx?: string) {
    const value = this.resolveBoundValue(text.text, ctx);
    const hint = text.usageHint || 'body';
    return html`<p class="a2ui-text ${hint}">${value ?? ''}</p>`;
  }

  private renderIcon(icon: NonNullable<ComponentDef['component']['Icon']>, ctx?: string) {
    const name = this.resolveBoundValue(icon.name, ctx);
    return html`<span class="a2ui-icon material-symbols-outlined">${name ?? ''}</span>`;
  }

  private renderImage(img: NonNullable<ComponentDef['component']['Image']>, ctx?: string) {
    const url = this.resolveBoundValue(img.url, ctx) as string;
    return url ? html`<img class="a2ui-image" src=${url} alt="" />` : nothing;
  }

  private renderButton(btn: NonNullable<ComponentDef['component']['Button']>, ctx?: string) {
    const cls = btn.primary ? 'primary' : 'secondary';
    return html`
      <button class="a2ui-button ${cls}" @click=${() => this.handleAction(btn.action, ctx)}>
        ${this.renderComponent(btn.child, ctx)}
      </button>
    `;
  }

  private renderList(list: NonNullable<ComponentDef['component']['List']>, ctx?: string) {
    const dir = list.direction || 'vertical';
    return html`
      <div class="a2ui-list ${dir}">
        ${this.renderChildren(list.children, ctx)}
      </div>
    `;
  }

  private renderDivider(div: NonNullable<ComponentDef['component']['Divider']>) {
    const axis = div.axis || 'horizontal';
    return html`<hr class="a2ui-divider ${axis}" />`;
  }

  /* ── Children resolution ────────────────────────────── */

  private renderChildren(children: ChildrenDef, ctx?: string): TemplateResult | typeof nothing {
    if (children.explicitList) {
      return html`${children.explicitList.map(id => this.renderComponent(id, ctx))}`;
    }
    if (children.template) {
      const { dataBinding, componentId } = children.template;
      const listData = this.resolveBoundValue({ path: dataBinding }, ctx);
      if (!listData || typeof listData !== 'object') return nothing;

      // listData can be an array or object-map
      const entries = Array.isArray(listData) ? listData : Object.values(listData);
      return html`${entries.map((_item, index) => {
        const itemPath = `${dataBinding}/${index}`;
        return this.renderComponent(componentId, itemPath);
      })}`;
    }
    return nothing;
  }

  /* ── BoundValue resolution ──────────────────────────── */

  private resolveBoundValue(bv: BoundValue, _ctx?: string): unknown {
    if (bv.literalString !== undefined) return bv.literalString;
    if (bv.literalNumber !== undefined) return bv.literalNumber;
    if (bv.literalBoolean !== undefined) return bv.literalBoolean;
    if (bv.path && this.surface) {
      // Resolve relative to context path if present
      const fullPath = _ctx && !bv.path.startsWith('/')
        ? `${_ctx}/${bv.path}`
        : bv.path;
      return this.resolveDataPath(fullPath);
    }
    return undefined;
  }

  private resolveDataPath(path: string): unknown {
    if (!this.surface) return undefined;
    const parts = path.replace(/^\//, '').split('/').filter(Boolean);
    let current: unknown = this.surface.dataModel;
    for (const part of parts) {
      if (current == null || typeof current !== 'object') return undefined;
      current = (current as Record<string, unknown>)[part];
    }
    return current;
  }

  /* ── Action handling ────────────────────────────────── */

  private handleAction(action: ComponentAction | undefined, _ctx?: string) {
    if (!action) return;
    this.dispatchEvent(new CustomEvent('a2ui-action', {
      detail: { name: action.name, context: action.context },
      bubbles: true,
      composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'a2ui-surface': A2UISurface;
  }
}
