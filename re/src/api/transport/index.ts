/**
 * Transport Factory
 *
 * Detects the runtime environment and returns the appropriate
 * transport implementation:
 * - Tauri desktop: uses @tauri-apps/api for IPC
 * - Browser (showcase): uses mock data with simulated delays
 *
 * Exports a singleton transport instance for application-wide use.
 */

import { tauriTransport } from "./tauri";
import { showcaseTransport } from "./showcase";
import type { Transport } from "./types";

// ===========================================================================
// Environment Detection
// ===========================================================================

/**
 * Check if the app is running inside a Tauri webview.
 * Tauri v2 injects `__TAURI_INTERNALS__` or `__TAURI__` on the window object.
 */
function isTauriEnvironment(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return (
    "__TAURI_INTERNALS__" in window ||
    "__TAURI__" in window
  );
}

// ===========================================================================
// Transport Creation
// ===========================================================================

/**
 * Lazily create the appropriate transport instance based on the
 * runtime environment. The transport is created once and cached.
 */
let _transport: Transport | null = null;

/**
 * Create the transport instance based on the current environment.
 */
function createTransport(): Transport {
  if (isTauriEnvironment()) {
    if (import.meta.env.DEV) {
      console.info("[Transport] Using TauriTransport (desktop mode)");
    }
    return tauriTransport;
  }

  if (import.meta.env.DEV) {
    console.info("[Transport] Using ShowcaseTransport (demo/browser mode)");
  }
  return showcaseTransport;
}

/**
 * Get the singleton transport instance.
 *
 * In Tauri desktop builds, returns the TauriTransport that communicates
 * with the Rust backend. In browser/demo mode, returns the ShowcaseTransport
 * with mock data.
 */
export function getTransport(): Transport {
  if (!_transport) {
    _transport = createTransport();
  }
  return _transport;
}

/**
 * Singleton transport instance. Use this throughout the application
 * for all backend communication.
 */
export const transport: Transport = getTransport();

/**
 * Re-initialize the transport with the given implementation.
 * Useful for testing or forcing a specific transport mode.
 */
export function setTransport(instance: Transport): void {
  _transport = instance;
  if (import.meta.env.DEV) {
    console.info("[Transport] Transport instance manually set");
  }
}

/**
 * Asynchronously initialize the transport. In most cases, the synchronous
 * `getTransport()` is sufficient. This method exists for compatibility
 * with code that expects async initialization.
 */
export async function getTransportAsync(): Promise<Transport> {
  return getTransport();
}

/**
 * Check if the current transport is running in showcase/demo mode.
 */
export function isShowcaseMode(): boolean {
  return !isTauriEnvironment();
}

// ===========================================================================
// Re-exports
// ===========================================================================

export type { Transport } from "./types";
export { tauriTransport } from "./tauri";
export { showcaseTransport } from "./showcase";