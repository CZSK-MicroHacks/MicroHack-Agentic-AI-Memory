/**
 * A2UI Message Types
 * Type definitions following the A2UI v0.8 protocol specification.
 */

/* ---------- Bound Values ---------- */
export interface BoundValue {
  literalString?: string;
  literalNumber?: number;
  literalBoolean?: boolean;
  path?: string;
}

/* ---------- Actions ---------- */
export interface ActionContextItem {
  key: string;
  value: BoundValue;
}

export interface ComponentAction {
  name: string;
  context?: ActionContextItem[];
}

/* ---------- Children ---------- */
export interface ChildrenDef {
  explicitList?: string[];
  template?: { dataBinding: string; componentId: string };
}

/* ---------- Component Types (Standard Catalog v0.8) ---------- */
export interface TextComponent {
  text: BoundValue;
  usageHint?: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'body' | 'caption';
}

export interface IconComponent {
  name: BoundValue;
}

export interface ImageComponent {
  url: BoundValue;
}

export interface ButtonComponent {
  child: string;
  primary?: boolean;
  action?: ComponentAction;
}

export interface CardComponent {
  child: string;
}

export interface ColumnComponent {
  children: ChildrenDef;
  alignment?: string;
  distribution?: string;
  gap?: 'small' | 'medium' | 'large';
}

export interface RowComponent {
  children: ChildrenDef;
  alignment?: string;
  distribution?: string;
  gap?: 'small' | 'medium' | 'large';
}

export interface ListComponent {
  children: ChildrenDef;
  direction?: 'vertical' | 'horizontal';
}

export interface DividerComponent {
  axis?: 'horizontal' | 'vertical';
}

/* ---------- Component Wrapper ---------- */
export interface ComponentDef {
  id: string;
  weight?: number;
  component: {
    Text?: TextComponent;
    Icon?: IconComponent;
    Image?: ImageComponent;
    Button?: ButtonComponent;
    Card?: CardComponent;
    Column?: ColumnComponent;
    Row?: RowComponent;
    List?: ListComponent;
    Divider?: DividerComponent;
  };
}

/* ---------- Data Model ---------- */
export interface DataEntry {
  key: string;
  valueString?: string;
  valueNumber?: number;
  valueBoolean?: boolean;
  valueMap?: DataEntry[];
}

/* ---------- Server-to-Client Messages ---------- */
export interface SurfaceUpdateMessage {
  surfaceUpdate: {
    surfaceId: string;
    components: ComponentDef[];
  };
}

export interface DataModelUpdateMessage {
  dataModelUpdate: {
    surfaceId: string;
    path?: string;
    contents: DataEntry[];
  };
}

export interface BeginRenderingMessage {
  beginRendering: {
    surfaceId: string;
    root: string;
    catalogId?: string;
    styles?: Record<string, unknown>;
  };
}

export interface DeleteSurfaceMessage {
  deleteSurface: {
    surfaceId: string;
  };
}

export type A2UIMessage =
  | SurfaceUpdateMessage
  | DataModelUpdateMessage
  | BeginRenderingMessage
  | DeleteSurfaceMessage;
