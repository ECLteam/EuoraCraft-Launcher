/**
 * External URLs Configuration
 *
 * Centralized external URL constants for documentation, APIs,
 * and various external resources used by the launcher.
 */

// ---------------------------------------------------------------------------
// Official / Project URLs
// ---------------------------------------------------------------------------
export const PROJECT_URLS = {
  /** Project homepage */
  HOMEPAGE: "https://euoracraft.com",
  /** GitHub repository */
  GITHUB: "https://github.com/EuoraCraft/EuoraCraft-Launcher",
  /** GitHub issues page */
  GITHUB_ISSUES: "https://github.com/EuoraCraft/EuoraCraft-Launcher/issues",
  /** GitHub releases page */
  GITHUB_RELEASES: "https://github.com/EuoraCraft/EuoraCraft-Launcher/releases",
  /** User documentation */
  DOCS: "https://docs.euoracraft.com",
  /** FAQ page */
  FAQ: "https://docs.euoracraft.com/faq",
  /** Changelog */
  CHANGELOG: "https://docs.euoracraft.com/changelog",
} as const;

// ---------------------------------------------------------------------------
// User Agreement / Legal
// ---------------------------------------------------------------------------
export const LEGAL_URLS = {
  /** User agreement / Terms of Service */
  USER_AGREEMENT: "https://euoracraft.com/terms",
  /** Privacy policy */
  PRIVACY_POLICY: "https://euoracraft.com/privacy",
  /** EULA */
  EULA: "https://www.minecraft.net/en-us/eula",
} as const;

// ---------------------------------------------------------------------------
// API & Service URLs
// ---------------------------------------------------------------------------
export const API_URLS = {
  /** Minecraft version manifest */
  MC_VERSION_MANIFEST: "https://launchermeta.mojang.com/mc/game/version_manifest.json",
  /** Mojang auth server */
  MOJANG_AUTH: "https://authserver.mojang.com",
  /** Microsoft OAuth authorize endpoint */
  MICROSOFT_AUTH: "https://login.live.com/oauth20_authorize.srf",
  /** Microsoft OAuth token endpoint */
  MICROSOFT_TOKEN: "https://login.live.com/oauth20_token.srf",
  /** Xbox Live auth endpoint */
  XBOX_AUTH: "https://user.auth.xboxlive.com/user/authenticate",
  /** Xbox Live XSTS endpoint */
  XBOX_XSTS: "https://xsts.auth.xboxlive.com/xsts/authorize",
  /** Minecraft auth with XBOX */
  MC_AUTH_XBOX: "https://api.minecraftservices.com/authentication/login_with_xbox",
  /** Minecraft profile API */
  MC_PROFILE: "https://api.minecraftservices.com/minecraft/profile",
  /** Minecraft player attributes */
  MC_ATTRIBUTES: "https://api.minecraftservices.com/player/attributes",
  /** Player avatar API (Crafatar) */
  AVATAR_API: "https://crafatar.com",
  /** Player avatar fallback (Minotar) */
  AVATAR_API_FALLBACK: "https://minotar.net",
  /** Launcher update check endpoint */
  LAUNCHER_UPDATE: "https://api.euoracraft.com/launcher/update",
  /** Plugin repository API */
  PLUGIN_REPO: "https://api.euoracraft.com/plugins",
  /** Online mod repository API */
  MOD_REPO: "https://api.euoracraft.com/mods",
} as const;

// ---------------------------------------------------------------------------
// Mirror / CDN URLs
// ---------------------------------------------------------------------------
export const MIRROR_URLS = {
  /** BMCLAPI mirror base */
  BMCLAPI: "https://bmclapi2.bangbang93.com",
  /** BMCLAPI assets mirror */
  BMCLAPI_ASSETS: "https://bmclapi2.bangbang93.com/assets",
  /** BMCLAPI libraries mirror */
  BMCLAPI_LIBRARIES: "https://bmclapi2.bangbang93.com/maven",
  /** MCBBS mirror */
  MCBBS: "https://download.mcbbs.net",
  /** MCBBS assets mirror */
  MCBBS_ASSETS: "https://download.mcbbs.net/assets",
  /** MCBBS libraries mirror */
  MCBBS_LIBRARIES: "https://download.mcbbs.net/maven",
} as const;

// ---------------------------------------------------------------------------
// Avatar URL Builders
// ---------------------------------------------------------------------------
/**
 * Build a player avatar URL from a UUID.
 * @param uuid - Player UUID (with or without dashes)
 * @param size - Avatar size in pixels (default: 64)
 * @param source - Avatar source ("crafatar" or "minotar")
 */
export function buildAvatarUrl(
  uuid: string,
  size: number = 64,
  source: "crafatar" | "minotar" = "crafatar"
): string {
  const cleanUuid = uuid.replace(/-/g, "");
  if (source === "crafatar") {
    return `${API_URLS.AVATAR_API}/avatars/${cleanUuid}?size=${size}&overlay`;
  }
  return `${API_URLS.AVATAR_API_FALLBACK}/avatar/${cleanUuid}/${size}`;
}

/**
 * Build a player head render URL (3D isometric).
 */
export function buildHeadRenderUrl(
  uuid: string,
  size: number = 128,
  source: "crafatar" | "minotar" = "crafatar"
): string {
  const cleanUuid = uuid.replace(/-/g, "");
  if (source === "crafatar") {
    return `${API_URLS.AVATAR_API}/renders/head/${cleanUuid}?size=${size}&overlay`;
  }
  return `${API_URLS.AVATAR_API_FALLBACK}/helm/${cleanUuid}/${size}`;
}