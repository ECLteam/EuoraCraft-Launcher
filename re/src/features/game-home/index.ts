/**
 * Game Home Feature - Barrel Export
 *
 * Minecraft Block Brutalist design system.
 * Central export point for the game-home feature module.
 * Exports the main GamePage component and all sub-components.
 */

export { GamePage } from "./GamePage";
export { GameAccountCard, MOCK_ACCOUNT } from "./GameAccountCard";
export type { AccountDisplayData } from "./GameAccountCard";
export { GameInfoCard } from "./GameInfoCard";
export type { TipItem } from "./GameInfoCard";
export { GameLaunchBar } from "./GameLaunchBar";
export type { VersionOption } from "./GameLaunchBar";
export { LaunchProgressCard, useDemoLaunchProgress } from "./LaunchProgressCard";

// ---------------------------------------------------------------------------
// Backward-compatible alias for App.tsx lazy import
// ---------------------------------------------------------------------------

import { GamePage } from "./GamePage";
export const GameHome = GamePage;