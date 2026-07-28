/**
 * AboutTab Component
 *
 * About page showing app information:
 * - App name in font-mono text-grass, version in font-mono
 * - Tech stack badges: border-2 border-stone, font-mono
 * - Links: text-water
 * - Card: border-2, shadow-[4px_4px_0px]
 *
 * Minecraft Block Brutalist design system.
 * NO spring. NO glass. NO rounded corners.
 */

import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Globe, ExternalLink, BookOpen, Heart, Gamepad2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Tech Stack Data
// ---------------------------------------------------------------------------

const TECH_STACK = [
  { name: "React 19", variant: "info" as const },
  { name: "TypeScript", variant: "info" as const },
  { name: "Tauri 2", variant: "warning" as const },
  { name: "Tailwind CSS v4", variant: "default" as const },
  { name: "shadcn/ui", variant: "secondary" as const },
  { name: "Framer Motion", variant: "secondary" as const },
  { name: "Zustand", variant: "success" as const },
  { name: "Rust", variant: "destructive" as const },
];

// ---------------------------------------------------------------------------
// AboutTab Component
// ---------------------------------------------------------------------------

export function AboutTab() {
  return (
    <div className="flex flex-col gap-4">
      {/* ---- App Info Card ---- */}
      <motion.div
        className="flex flex-col items-center border-2 border-border-stone bg-bg-surface p-8 text-center shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        {/* Logo */}
        <motion.div
          className="mb-4 flex h-20 w-20 items-center justify-center border-2 border-grass bg-grass/10"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
        >
          <Gamepad2 className="h-10 w-10 text-grass" />
        </motion.div>

        {/* App Name */}
        <motion.h1
          className="font-mono text-2xl font-bold text-grass"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
        >
          EuoraCraft Launcher
        </motion.h1>

        {/* Version */}
        <motion.p
          className="mt-1 font-mono text-sm text-text-tertiary"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.16, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
        >
          Version 1.0.0-beta
        </motion.p>

        <motion.p
          className="mt-2 text-xs text-text-tertiary"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
        >
          一个现代化的 Minecraft 启动器，基于 Tauri 2 构建
        </motion.p>
      </motion.div>

      {/* ---- Tech Stack Card ---- */}
      <motion.div
        className="border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.03, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        <h3 className="mb-3 font-mono text-sm font-semibold text-text-primary">
          技术栈
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {TECH_STACK.map((tech) => (
            <Badge
              key={tech.name}
              variant={tech.variant}
              className="border-2 px-2 py-0.5 font-mono text-xs font-medium"
            >
              {tech.name}
            </Badge>
          ))}
        </div>
      </motion.div>

      {/* ---- Links Card ---- */}
      <motion.div
        className="border-2 border-border-stone bg-bg-surface p-4 shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.06, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        <h3 className="mb-3 font-mono text-sm font-semibold text-text-primary">
          链接
        </h3>
        <div className="flex flex-col gap-2">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 border-2 border-transparent px-3 py-2 font-mono text-sm text-water transition-[color,background-color,border-color] duration-[150ms] hover:border-border-stone hover:bg-bg-elevated hover:text-water-300"
          >
            <Globe className="h-4 w-4" />
            GitHub 仓库
            <ExternalLink className="ml-auto h-3 w-3 text-text-tertiary" />
          </a>
          <a
            href="#"
            className="flex items-center gap-2 border-2 border-transparent px-3 py-2 font-mono text-sm text-water transition-[color,background-color,border-color] duration-[150ms] hover:border-border-stone hover:bg-bg-elevated hover:text-water-300"
          >
            <BookOpen className="h-4 w-4" />
            开源许可证
            <ExternalLink className="ml-auto h-3 w-3 text-text-tertiary" />
          </a>
        </div>
      </motion.div>

      {/* ---- Credits Card ---- */}
      <motion.div
        className="border-2 border-border-stone bg-bg-surface p-4 text-center shadow-[4px_4px_0px_rgba(0,0,0,0.3)]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.09, duration: 0.15, ease: [0.8, 0, 0.2, 1] }}
      >
        <p className="flex items-center justify-center gap-1 font-mono text-xs text-text-tertiary">
          Made with <Heart className="h-3 w-3 text-lava" /> by EuoraCraft Team
        </p>
        <p className="mt-1 font-mono text-[10px] text-text-tertiary/60">
          Copyright 2026 EuoraCraft. All rights reserved.
        </p>
      </motion.div>
    </div>
  );
}