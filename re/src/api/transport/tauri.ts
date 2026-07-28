/**
 * Tauri Desktop Transport Implementation
 *
 * Production transport implementation that communicates with the
 * Rust backend through Tauri v2 IPC. Uses @tauri-apps/api for
 * invoke, listen, and file system operations.
 *
 * Features:
 * - 30 second timeout for all IPC calls
 * - Consistent ApiResponse<T> wrapping
 * - Comprehensive error handling and logging
 * - File system operations via Tauri plugin commands
 */

import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import { listen as tauriListen } from "@tauri-apps/api/event";
import { convertFileSrc as tauriConvertFileSrc } from "@tauri-apps/api/core";
import type { ApiResponse } from "@/types/api";
import type { Transport } from "./types";

// ===========================================================================
// Constants
// ===========================================================================

/** Default timeout for IPC calls in milliseconds */
const IPC_TIMEOUT_MS = 30_000;

/** Log prefix for transport operations */
const LOG_PREFIX = "[TauriTransport]";

// ===========================================================================
// Helpers
// ===========================================================================

/**
 * Create a timeout promise that rejects after the specified duration.
 */
function createTimeout(ms: number, cmd: string): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => {
      reject(new Error(`IPC call "${cmd}" timed out after ${ms}ms`));
    }, ms);
  });
}

/**
 * Wrap a raw Tauri invoke call with timeout and ApiResponse formatting.
 */
async function invokeWithTimeout<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<ApiResponse<T>> {
  const startTime = performance.now();

  try {
    const data = await Promise.race([
      tauriInvoke<T>(cmd, args),
      createTimeout(IPC_TIMEOUT_MS, cmd),
    ]);

    const elapsed = Math.round(performance.now() - startTime);
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} invoke "${cmd}" succeeded in ${elapsed}ms`, {
        args,
        data,
      });
    }

    return {
      success: true,
      data,
      timestamp: Date.now(),
    };
  } catch (error: unknown) {
    const elapsed = Math.round(performance.now() - startTime);
    const message =
      error instanceof Error ? error.message : String(error);
    const code = error instanceof Error && "code" in error
      ? String((error as { code: unknown }).code)
      : undefined;

    console.error(`${LOG_PREFIX} invoke "${cmd}" failed after ${elapsed}ms`, {
      args,
      error: message,
      code,
    });

    return {
      success: false,
      error: message,
      code,
      timestamp: Date.now(),
    };
  }
}

/**
 * Safely read file bytes via Tauri plugin:fs invoke.
 * Falls back with a descriptive error if the plugin is not available.
 */
async function tauriReadFile(path: string): Promise<Uint8Array> {
  try {
    // Tauri plugin:fs returns number[] for file bytes
    const bytes = await tauriInvoke<number[]>("plugin:fs|read_file", { path });
    return new Uint8Array(bytes);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to read file "${path}": ${message}`);
  }
}

/**
 * Safely check file existence via Tauri plugin:fs invoke.
 */
async function tauriExists(path: string): Promise<boolean> {
  try {
    return await tauriInvoke<boolean>("plugin:fs|exists", { path });
  } catch {
    // If the command is not available, return false
    return false;
  }
}

/**
 * Safely read directory entries via Tauri plugin:fs invoke.
 */
async function tauriReadDir(path: string): Promise<string[]> {
  try {
    const entries = await tauriInvoke<
      Array<{ name: string; isDirectory: boolean }>
    >("plugin:fs|read_dir", { path });
    return entries.map((entry) => entry.name);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to read directory "${path}": ${message}`);
  }
}

/**
 * Resolve a path using the Tauri path API.
 * Dynamically imports the path module to avoid issues in non-Tauri environments.
 */
async function tauriResolvePath(path: string): Promise<string> {
  const { resolve } = await import("@tauri-apps/api/path");
  return resolve(path);
}

// ===========================================================================
// TauriTransport Implementation
// ===========================================================================

/**
 * Production transport implementation for Tauri desktop builds.
 *
 * Communicates with the Rust backend through Tauri's IPC bridge.
 * All invoke calls are wrapped with a 30-second timeout and
 * returned in the standard ApiResponse<T> format.
 */
export const tauriTransport: Transport = {
  async invoke<T>(
    cmd: string,
    args?: Record<string, unknown>,
  ): Promise<ApiResponse<T>> {
    return invokeWithTimeout<T>(cmd, args);
  },

  async listen<T>(
    event: string,
    handler: (payload: T) => void,
  ): Promise<() => void> {
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} listen registering for "${event}"`);
    }

    const unlisten = await tauriListen<T>(event, (eventPayload) => {
      if (import.meta.env.DEV) {
        console.debug(`${LOG_PREFIX} event "${event}" received`, eventPayload);
      }
      handler(eventPayload.payload);
    });

    return () => {
      if (import.meta.env.DEV) {
        console.debug(`${LOG_PREFIX} listen unregistered for "${event}"`);
      }
      unlisten();
    };
  },

  async readFile(path: string): Promise<Uint8Array> {
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} readFile "${path}"`);
    }
    return tauriReadFile(path);
  },

  async exists(path: string): Promise<boolean> {
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} exists "${path}"`);
    }
    return tauriExists(path);
  },

  async readDir(path: string): Promise<string[]> {
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} readDir "${path}"`);
    }
    return tauriReadDir(path);
  },

  async resolvePath(path: string): Promise<string> {
    if (import.meta.env.DEV) {
      console.debug(`${LOG_PREFIX} resolvePath "${path}"`);
    }
    return tauriResolvePath(path);
  },

  convertFileSrc(path: string): string {
    return tauriConvertFileSrc(path);
  },
};

export default tauriTransport;