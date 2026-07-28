/**
 * GameAccountCard Component
 *
 * Minecraft Block Brutalist account card.
 * border-2, block shadows, font-mono, sharp corners.
 * NO glass, NO blur, NO rounded-full, NO scale.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { User, Shield, Monitor, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AccountType } from "@/types/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AccountDisplayData {
  uuid: string;
  username: string;
  type: AccountType;
  avatarUrl?: string;
  isSelected: boolean;
  isLoggedIn: boolean;
}

interface GameAccountCardProps {
  account?: AccountDisplayData | null;
  onClick?: () => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Account Type Config
// ---------------------------------------------------------------------------

interface AccountTypeMeta {
  label: string;
  icon: LucideIcon;
  bgClass: string;
  textClass: string;
}

const accountTypeConfig: Record<string, AccountTypeMeta> = {
  microsoft: {
    label: "Microsoft",
    icon: Shield,
    bgClass: "bg-[#5B8731]",
    textClass: "text-[#E8E8E8]",
  },
  offline: {
    label: "Offline",
    icon: Monitor,
    bgClass: "bg-[#7F7F7F]",
    textClass: "text-[#E8E8E8]",
  },
  authlib: {
    label: "Authlib",
    icon: Shield,
    bgClass: "bg-[#3B6BD4]",
    textClass: "text-[#E8E8E8]",
  },
};

function getInitials(username: string): string {
  return username.charAt(0).toUpperCase();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GameAccountCard({
  account,
  onClick,
  className,
}: GameAccountCardProps) {
  const [isHovered, setIsHovered] = useState(false);

  const hasAccount = !!account;
  const typeMeta = account
    ? (accountTypeConfig[account.type] ?? accountTypeConfig.offline)
    : null;

  const snappyEase: [number, number, number, number] = [0.8, 0, 0.2, 1];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: snappyEase, delay: 0.05 }}
    >
      <div
        className={cn(
          "cursor-pointer border-2 border-[#7F7F7F26] bg-[#1A1A1A]",
          "transition-[transform,box-shadow] duration-[150ms]",
          "shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
          isHovered && "translate-y-[-1px] shadow-[6px_6px_0px_rgba(0,0,0,0.3)]",
          className
        )}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={onClick}
      >
        <div className="p-4">
          {hasAccount && account ? (
            /* ---- Account Info ---- */
            <div className="flex items-center gap-3">
              {/* Avatar - sharp square, NOT rounded */}
              <div className="relative flex size-10 items-center justify-center border-2 border-[#7F7F7F26] bg-[#0D0D0D] overflow-hidden">
                {account.avatarUrl ? (
                  <img
                    src={account.avatarUrl}
                    alt={account.username}
                    className="size-full object-cover"
                  />
                ) : (
                  <span className="font-mono text-sm font-bold text-[#E8E8E8]">
                    {getInitials(account.username)}
                  </span>
                )}
              </div>

              {/* Name & Badge */}
              <div className="flex-1 min-w-0">
                <p className="font-mono text-sm text-[#E8E8E8] truncate">
                  {account.username}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  {typeMeta && (
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px]",
                        typeMeta.bgClass,
                        typeMeta.textClass
                      )}
                    >
                      <typeMeta.icon className="size-2.5" />
                      {typeMeta.label}
                    </span>
                  )}
                  {account.isLoggedIn && (
                    <span className="flex items-center gap-1 font-mono text-[10px] text-[#50C878]">
                      <span className="size-1.5 bg-[#50C878]" />
                      Online
                    </span>
                  )}
                </div>
              </div>

              {/* Chevron */}
              <motion.div
                animate={{ x: isHovered ? 2 : 0 }}
                transition={{ duration: 0.15, ease: snappyEase }}
              >
                <ChevronRight className="size-4 text-[#555555]" />
              </motion.div>
            </div>
          ) : (
            /* ---- No Account State ---- */
            <div className="flex items-center gap-3 border-2 border-dashed border-[#7F7F7F26] p-3">
              <div className="flex size-10 items-center justify-center border-2 border-[#7F7F7F26] bg-[#0D0D0D]">
                <User className="size-5 text-[#555555]" />
              </div>
              <div className="flex-1">
                <p className="font-mono text-sm text-[#999999]">
                  Add Account
                </p>
                <p className="text-xs text-[#555555] mt-0.5">
                  Sign in to play Minecraft
                </p>
              </div>
              <motion.div
                animate={{ x: isHovered ? 2 : 0 }}
                transition={{ duration: 0.15, ease: snappyEase }}
              >
                <ChevronRight className="size-4 text-[#555555]" />
              </motion.div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Default mock account
// ---------------------------------------------------------------------------

export const MOCK_ACCOUNT: AccountDisplayData = {
  uuid: "mock-uuid-001",
  username: "Steve",
  type: "microsoft" as AccountType,
  avatarUrl: undefined,
  isSelected: true,
  isLoggedIn: true,
};

export default GameAccountCard;