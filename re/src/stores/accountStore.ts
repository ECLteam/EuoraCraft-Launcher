/**
 * Account Management Store
 *
 * Zustand store managing Minecraft account state:
 * - Microsoft login flow (device code, polling)
 * - Offline login
 * - Account CRUD operations
 * - Selected account tracking
 *
 * Uses the transport layer for backend communication and
 * provides mock data when running in showcase mode.
 */

import { create } from "zustand";
import { transport } from "@/api/transport";
import { isShowcaseMode } from "@/api/transport";
import type { MinecraftAccount } from "@/types/api";

// ===========================================================================
// Types
// ===========================================================================

/** Microsoft device code login response */
export interface DeviceCodeResponse {
  deviceCode: string;
  userCode: string;
  verificationUri: string;
  expiresIn: number;
  interval: number;
  message?: string;
}

/** Microsoft OAuth polling status */
export type MicrosoftPollStatus =
  | "authorization_pending"
  | "authorization_declined"
  | "expired_token"
  | "slow_down"
  | "success";

/** Microsoft OAuth poll response */
export interface MicrosoftPollResponse {
  status: MicrosoftPollStatus;
  account?: MinecraftAccount;
  error?: string;
}

/** Microsoft login flow state */
export interface MicrosoftLoginState {
  /** Whether the login flow is active */
  isActive: boolean;
  /** Current step in the flow */
  step: "idle" | "waiting_for_code" | "polling" | "completed" | "error";
  /** Device code response */
  deviceCode?: DeviceCodeResponse;
  /** Current polling status */
  pollStatus?: MicrosoftPollStatus;
  /** The resulting account (on success) */
  account?: MinecraftAccount;
  /** Error message (on failure) */
  error?: string;
  /** Polling interval ID */
  pollingIntervalId?: ReturnType<typeof setInterval>;
}

/** Account store state */
export interface AccountState {
  // ---- Data ----
  /** All registered accounts */
  accounts: MinecraftAccount[];
  /** Currently selected account */
  selectedAccount: MinecraftAccount | null;
  /** Whether accounts are being loaded */
  loading: boolean;
  /** Error message if loading failed */
  error: string | null;
  /** Microsoft login flow state */
  microsoftLogin: MicrosoftLoginState;

  // ---- Actions ----
  /** Fetch all accounts from the backend */
  fetchAccounts: () => Promise<void>;
  /** Add a new account */
  addAccount: (account: MinecraftAccount) => Promise<void>;
  /** Remove an account by UUID */
  removeAccount: (uuid: string) => Promise<void>;
  /** Select an account by UUID */
  selectAccount: (uuid: string) => void;
  /** Start the Microsoft OAuth login flow */
  loginMicrosoft: () => Promise<void>;
  /** Cancel the Microsoft login flow */
  cancelMicrosoftLogin: () => void;
  /** Perform an offline login with a username */
  loginOffline: (username: string) => Promise<void>;
  /** Clear any error state */
  clearError: () => void;
}

// ===========================================================================
// Default Login State
// ===========================================================================

function createDefaultLoginState(): MicrosoftLoginState {
  return {
    isActive: false,
    step: "idle",
  };
}

// ===========================================================================
// Mock Data
// ===========================================================================

const mockAccounts: MinecraftAccount[] = [
  {
    uuid: "account-1",
    type: "microsoft",
    username: "EuoraPlayer",
    playerUuid: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    accessToken: "mock_access_token",
    refreshToken: "mock_refresh_token",
    expiresAt: Date.now() + 86400000,
    isSelected: true,
    avatarUrl: "https://crafatar.com/avatars/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4?size=64&overlay",
    lastLogin: Date.now() - 3600000,
    isLoggedIn: true,
  },
  {
    uuid: "account-2",
    type: "offline",
    username: "Steve",
    playerUuid: "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f",
    accessToken: "",
    refreshToken: "",
    expiresAt: 0,
    isSelected: false,
    avatarUrl: "",
    lastLogin: Date.now() - 86400000,
    isLoggedIn: true,
  },
];

// ===========================================================================
// Helpers
// ===========================================================================

/**
 * Generate a simple UUID v4-like string.
 */
function generateUuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Generate a deterministic offline player UUID from a username.
 */
function offlinePlayerUuid(username: string): string {
  // Simple hash-based UUID generation for offline mode
  let hash = 0;
  for (let i = 0; i < username.length; i++) {
    hash = ((hash << 5) - hash + username.charCodeAt(i)) | 0;
  }
  const hex = Math.abs(hash).toString(16).padStart(32, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// ===========================================================================
// Store
// ===========================================================================

export const useAccountStore = create<AccountState>()((set, get) => ({
  // ---- Initial State ----
  accounts: [],
  selectedAccount: null,
  loading: false,
  error: null,
  microsoftLogin: createDefaultLoginState(),

  // ---- Actions ----

  fetchAccounts: async () => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        // Simulate network delay
        await new Promise((r) => setTimeout(r, 300));
        const selected = mockAccounts.find((a) => a.isSelected) ?? mockAccounts[0] ?? null;
        set({ accounts: mockAccounts, selectedAccount: selected, loading: false });
        return;
      }

      const response = await transport.invoke<MinecraftAccount[]>("get_accounts");
      if (response.success && response.data) {
        const selected = response.data.find((a) => a.isSelected) ?? response.data[0] ?? null;
        set({ accounts: response.data, selectedAccount: selected, loading: false });
      } else {
        set({ error: response.error ?? "Failed to fetch accounts", loading: false });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message, loading: false });
    }
  },

  addAccount: async (account: MinecraftAccount) => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 200));
        set((state) => ({
          accounts: [...state.accounts, account],
          loading: false,
        }));
        return;
      }

      const response = await transport.invoke<MinecraftAccount>("add_account", {
        account,
      });
      if (response.success && response.data) {
        set((state) => ({
          accounts: [...state.accounts, response.data!],
          loading: false,
        }));
      } else {
        set({ error: response.error ?? "Failed to add account", loading: false });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message, loading: false });
    }
  },

  removeAccount: async (uuid: string) => {
    set({ loading: true, error: null });

    try {
      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 200));
        set((state) => {
          const accounts = state.accounts.filter((a) => a.uuid !== uuid);
          const selectedAccount =
            state.selectedAccount?.uuid === uuid
              ? (accounts[0] ?? null)
              : state.selectedAccount;
          return { accounts, selectedAccount, loading: false };
        });
        return;
      }

      const response = await transport.invoke<{ ok: boolean }>("remove_account", {
        uuid,
      });
      if (response.success) {
        set((state) => {
          const accounts = state.accounts.filter((a) => a.uuid !== uuid);
          const selectedAccount =
            state.selectedAccount?.uuid === uuid
              ? (accounts[0] ?? null)
              : state.selectedAccount;
          return { accounts, selectedAccount, loading: false };
        });
      } else {
        set({ error: response.error ?? "Failed to remove account", loading: false });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message, loading: false });
    }
  },

  selectAccount: (uuid: string) => {
    set((state) => {
      const accounts = state.accounts.map((a) => ({
        ...a,
        isSelected: a.uuid === uuid,
      }));
      const selectedAccount = accounts.find((a) => a.uuid === uuid) ?? null;
      return { accounts, selectedAccount };
    });
  },

  loginMicrosoft: async () => {
    const state = get();
    // Prevent duplicate login flows
    if (state.microsoftLogin.isActive) {
      return;
    }

    set({
      microsoftLogin: {
        isActive: true,
        step: "waiting_for_code",
      },
      error: null,
    });

    try {
      if (isShowcaseMode()) {
        // Simulate device code flow
        await new Promise((r) => setTimeout(r, 500));

        const deviceCode: DeviceCodeResponse = {
          deviceCode: "MOCK-DEVICE-CODE-" + Date.now(),
          userCode: "MOCK-USER-CODE",
          verificationUri: "https://microsoft.com/link",
          expiresIn: 900,
          interval: 5,
          message: "To sign in, use a web browser to open the page https://microsoft.com/link and enter the code MOCK-USER-CODE to authenticate.",
        };

        set({
          microsoftLogin: {
            isActive: true,
            step: "polling",
            deviceCode,
            pollStatus: "authorization_pending",
          },
        });

        // Simulate polling (complete after ~3 seconds)
        let pollCount = 0;
        const intervalId = setInterval(async () => {
          pollCount++;
          const currentState = get().microsoftLogin;

          if (!currentState.isActive) {
            clearInterval(intervalId);
            return;
          }

          if (pollCount >= 3) {
            // Simulate success
            clearInterval(intervalId);
            const account: MinecraftAccount = {
              uuid: generateUuid(),
              type: "microsoft",
              username: "EuoraPlayer",
              playerUuid: generateUuid(),
              accessToken: "mock_ms_access_" + Date.now(),
              refreshToken: "mock_ms_refresh_" + Date.now(),
              expiresAt: Date.now() + 86400000,
              isSelected: true,
              avatarUrl: "",
              lastLogin: Date.now(),
              isLoggedIn: true,
            };

            set((s) => ({
              accounts: s.accounts
                .map((a) => ({ ...a, isSelected: false }))
                .concat(account),
              selectedAccount: account,
              microsoftLogin: {
                isActive: false,
                step: "completed",
                account,
              },
            }));

            // Reset login state after a short delay
            setTimeout(() => {
              set({ microsoftLogin: createDefaultLoginState() });
            }, 2000);
          }
        }, 1000);

        set({
          microsoftLogin: {
            ...get().microsoftLogin,
            pollingIntervalId: intervalId,
          },
        });
        return;
      }

      // Real Microsoft login flow via backend
      const response = await transport.invoke<DeviceCodeResponse>("microsoft_login");

      if (!response.success || !response.data) {
        set({
          microsoftLogin: {
            isActive: true,
            step: "error",
            error: response.error ?? "Failed to initiate Microsoft login",
          },
        });
        return;
      }

      const deviceCode = response.data;
      set({
        microsoftLogin: {
          isActive: true,
          step: "polling",
          deviceCode,
          pollStatus: "authorization_pending",
        },
      });

      // Start polling
      const intervalId = setInterval(async () => {
        const currentState = get().microsoftLogin;

        if (!currentState.isActive || currentState.step !== "polling") {
          clearInterval(intervalId);
          return;
        }

        try {
          const pollResponse = await transport.invoke<MicrosoftPollResponse>(
            "microsoft_poll",
            { deviceCode: deviceCode.deviceCode },
          );

          if (!pollResponse.success || !pollResponse.data) {
            set({
              microsoftLogin: {
                ...currentState,
                step: "error",
                error: pollResponse.error ?? "Polling failed",
              },
            });
            clearInterval(intervalId);
            return;
          }

          const { status, account } = pollResponse.data;

          if (status === "success" && account) {
            clearInterval(intervalId);

            set((s) => ({
              accounts: s.accounts
                .map((a) => ({ ...a, isSelected: false }))
                .concat(account),
              selectedAccount: account,
              microsoftLogin: {
                isActive: false,
                step: "completed",
                account,
              },
            }));

            setTimeout(() => {
              set({ microsoftLogin: createDefaultLoginState() });
            }, 2000);
          } else if (status === "authorization_declined" || status === "expired_token") {
            clearInterval(intervalId);
            set({
              microsoftLogin: {
                isActive: true,
                step: "error",
                deviceCode,
                error:
                  status === "authorization_declined"
                    ? "User declined authorization"
                    : "Device code has expired",
              },
            });
          } else {
            set({
              microsoftLogin: {
                ...currentState,
                pollStatus: status,
              },
            });
          }
        } catch {
          // Polling error - keep trying
        }
      }, (deviceCode.interval || 5) * 1000);

      set({
        microsoftLogin: {
          ...get().microsoftLogin,
          pollingIntervalId: intervalId,
        },
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        microsoftLogin: {
          isActive: true,
          step: "error",
          error: message,
        },
      });
    }
  },

  cancelMicrosoftLogin: () => {
    const state = get().microsoftLogin;
    if (state.pollingIntervalId) {
      clearInterval(state.pollingIntervalId);
    }
    set({ microsoftLogin: createDefaultLoginState() });
  },

  loginOffline: async (username: string) => {
    set({ loading: true, error: null });

    try {
      const trimmedName = username.trim();
      if (!trimmedName) {
        set({ error: "Username cannot be empty", loading: false });
        return;
      }

      if (isShowcaseMode()) {
        await new Promise((r) => setTimeout(r, 300));

        const account: MinecraftAccount = {
          uuid: generateUuid(),
          type: "offline",
          username: trimmedName,
          playerUuid: offlinePlayerUuid(trimmedName),
          accessToken: "",
          refreshToken: "",
          expiresAt: 0,
          isSelected: true,
          avatarUrl: "",
          lastLogin: Date.now(),
          isLoggedIn: true,
        };

        set((s) => ({
          accounts: s.accounts
            .map((a) => ({ ...a, isSelected: false }))
            .concat(account),
          selectedAccount: account,
          loading: false,
        }));
        return;
      }

      const response = await transport.invoke<MinecraftAccount>("offline_login", {
        username: trimmedName,
      });

      if (response.success && response.data) {
        set((s) => ({
          accounts: s.accounts
            .map((a) => ({ ...a, isSelected: false }))
            .concat(response.data!),
          selectedAccount: response.data,
          loading: false,
        }));
      } else {
        set({ error: response.error ?? "Failed to create offline account", loading: false });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      set({ error: message, loading: false });
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));

// ===========================================================================
// Selectors
// ===========================================================================

/** Select only the accounts list */
export const selectAccounts = (state: AccountState) => state.accounts;

/** Select only the currently selected account */
export const selectSelectedAccount = (state: AccountState) => state.selectedAccount;

/** Select Microsoft login state */
export const selectMicrosoftLogin = (state: AccountState) => state.microsoftLogin;

/** Select account loading state */
export const selectAccountLoading = (state: AccountState) => ({
  loading: state.loading,
  error: state.error,
});

export default useAccountStore;