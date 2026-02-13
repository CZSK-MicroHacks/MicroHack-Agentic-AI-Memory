/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly AUTH_MODE?: string;
  readonly VITE_AUTH_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
