/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Fixpoint API base URL. Empty by default so Vite's /api proxy is used. */
  readonly VITE_FIXPOINT_API_BASE?: string;
  /** Operator console URL, linked from refund status cards. */
  readonly VITE_FIXPOINT_CONSOLE_URL?: string;
  /** Platzi Fake Store API base URL. */
  readonly VITE_PLATZI_API_BASE?: string;
  /** Formspree form id used for order/refund notification emails. */
  readonly VITE_FORMSPREE_FORM_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
