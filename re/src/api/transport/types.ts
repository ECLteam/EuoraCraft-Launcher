/**
 * Transport Interface Definition
 *
 * Defines the abstract transport layer contract for the EuoraCraft Launcher.
 * All transport implementations (Tauri desktop, showcase mock) must
 * implement this interface.
 */

import type { ApiResponse } from "@/types/api";

// ===========================================================================
// Transport Interface
// ===========================================================================

/**
 * Generic transport layer abstraction for backend communication.
 *
 * The transport wraps all IPC calls in `ApiResponse<T>` for consistent
 * error handling. It also provides file system operations and event
 * listening capabilities.
 */
export interface Transport {
  /**
   * Send a command to the backend and receive a typed, wrapped response.
   * All IPC calls go through this method, ensuring consistent error handling.
   *
   * @param cmd - The command name to invoke (e.g. "get_config", "launch_game")
   * @param args - Optional command arguments
   * @returns A promise resolving to an ApiResponse wrapping the result data
   */
  invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<ApiResponse<T>>;

  /**
   * Listen for events emitted from the backend.
   * Returns an unlisten function to stop listening.
   *
   * @param event - The event name to listen for
   * @param handler - Callback invoked with the event payload
   * @returns A promise resolving to an unlisten function
   */
  listen<T>(event: string, handler: (payload: T) => void): Promise<() => void>;

  /**
   * Read a file from the file system as raw bytes.
   *
   * @param path - Absolute path to the file
   * @returns A promise resolving to the file contents as Uint8Array
   */
  readFile(path: string): Promise<Uint8Array>;

  /**
   * Check whether a file or directory exists at the given path.
   *
   * @param path - Absolute path to check
   * @returns A promise resolving to true if the path exists
   */
  exists(path: string): Promise<boolean>;

  /**
   * List the contents of a directory.
   *
   * @param path - Absolute path to the directory
   * @returns A promise resolving to an array of entry names
   */
  readDir(path: string): Promise<string[]>;

  /**
   * Resolve a relative path to an absolute path based on the app's
   * resource or data directory.
   *
   * @param path - Relative path to resolve
   * @returns A promise resolving to the absolute path
   */
  resolvePath(path: string): Promise<string>;

  /**
   * Convert a local file path to an asset URL that can be used
   * in the webview (e.g. for displaying images).
   *
   * @param path - Absolute file path to convert
   * @returns An asset protocol URL string
   */
  convertFileSrc(path: string): string;
}