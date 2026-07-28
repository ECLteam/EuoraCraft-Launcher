/**
 * TaskPanel Component
 *
 * Slide-in panel displaying the task queue. Opens from the right side
 * with a bounce-in animation. Shows task status, progress, and type.
 *
 * Minecraft Block Brutalist design:
 * - border-l-2 border-stone, bg-deepslate, no glass, no rounded corners
 * - Blocky task items with status-colored left borders
 * - Progress bars with discrete block segments
 * - font-mono for all text
 */

import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Trash2,
  Download,
  PackageOpen,
  FileArchive,
  ShieldCheck,
  Play,
  Puzzle,
  RefreshCw,
  Trash,
  Circle,
  Loader,
  CheckCircle,
  XCircle,
  Ban,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import type { TaskInfo, TaskStatus, TaskType } from "@/types/api";

// ===========================================================================
// Constants
// ===========================================================================

const PANEL_WIDTH = 340;

/** Task type to icon mapping */
const TASK_TYPE_ICONS: Record<TaskType, React.ComponentType<{ className?: string }>> = {
  download: Download,
  install: PackageOpen,
  extract: FileArchive,
  verify: ShieldCheck,
  launch: Play,
  plugin_install: Puzzle,
  plugin_update: RefreshCw,
  plugin_remove: Trash,
  version_install: Download,
  version_delete: Trash,
};

/** Task type display name */
const TASK_TYPE_LABELS: Record<TaskType, string> = {
  download: "下载",
  install: "安装",
  extract: "解压",
  verify: "校验",
  launch: "启动",
  plugin_install: "安装插件",
  plugin_update: "更新插件",
  plugin_remove: "卸载插件",
  version_install: "安装版本",
  version_delete: "删除版本",
};

/** Status configuration */
const STATUS_CONFIG: Record<TaskStatus, {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
}> = {
  pending: {
    icon: Clock,
    label: "等待中",
    colorClass: "text-gold",
    bgClass: "bg-gold-500/10",
    borderClass: "border-l-gold",
  },
  running: {
    icon: Loader,
    label: "运行中",
    colorClass: "text-water",
    bgClass: "bg-water-500/10",
    borderClass: "border-l-water",
  },
  completed: {
    icon: CheckCircle,
    label: "已完成",
    colorClass: "text-emerald",
    bgClass: "bg-emerald-500/10",
    borderClass: "border-l-emerald",
  },
  failed: {
    icon: XCircle,
    label: "失败",
    colorClass: "text-lava",
    bgClass: "bg-lava-500/10",
    borderClass: "border-l-lava",
  },
  cancelled: {
    icon: Ban,
    label: "已取消",
    colorClass: "text-stone",
    bgClass: "bg-stone-500/10",
    borderClass: "border-l-stone",
  },
};

// ===========================================================================
// Panel Animation Variants
// ===========================================================================

const panelVariants = {
  hidden: {
    x: PANEL_WIDTH,
    opacity: 0,
  },
  visible: {
    x: 0,
    opacity: 1,
    transition: {
      type: "tween",
      ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
      duration: 0.4,
    },
  },
  exit: {
    x: PANEL_WIDTH,
    opacity: 0,
    transition: {
      type: "tween",
      ease: [0.4, 0, 1, 1] as [number, number, number, number],
      duration: 0.2,
    },
  },
};

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2 },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.15 },
  },
};

const taskItemVariants = {
  hidden: {
    opacity: 0,
    x: 40,
    scale: 0.9,
  },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    scale: 1,
    transition: {
      type: "tween",
      ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
      duration: 0.35,
      delay: i * 0.06,
    },
  }),
};

// ===========================================================================
// Helper: format time
// ===========================================================================

function formatTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  if (diff < 60000) return "刚刚";
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
  return new Date(timestamp).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ===========================================================================
// TaskItem Component
// ===========================================================================

interface TaskItemProps {
  task: TaskInfo;
  index: number;
  onCancel: (id: string) => void;
  onRemove: (id: string) => void;
}

function TaskItem({ task, index, onCancel, onRemove }: TaskItemProps) {
  const statusConfig = STATUS_CONFIG[task.status];
  const StatusIcon = statusConfig.icon;
  const TypeIcon = TASK_TYPE_ICONS[task.type];
  const isActive = task.status === "pending" || task.status === "running";
  const isFailed = task.status === "failed";

  return (
    <motion.div
      custom={index}
      variants={taskItemVariants}
      initial="hidden"
      animate="visible"
      className={cn(
        "relative border-2 border-stone-700",
        "bg-bg-elevated",
        "shadow-[3px_3px_0px_rgba(0,0,0,0.25)]",
        "transition-[transform,box-shadow] duration-[150ms]",
        "hover:-translate-y-[1px] hover:shadow-[4px_4px_0px_rgba(0,0,0,0.3)]",
      )}
    >
      {/* Left status border */}
      <div className={cn(
        "absolute left-0 top-0 bottom-0 w-1",
        statusConfig.borderClass.replace("border-l-", "bg-"),
      )} />

      {/* Task header */}
      <div className="flex items-start gap-2.5 p-3 pl-4">
        {/* Type icon */}
        <div className={cn(
          "flex items-center justify-center size-7 shrink-0 border-2 border-stone-600",
          statusConfig.bgClass,
        )}>
          <TypeIcon className={cn("size-3.5", statusConfig.colorClass)} />
        </div>

        {/* Task info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-mono text-xs font-medium text-text-primary truncate">
              {task.name}
            </p>
            <span className={cn(
              "font-mono text-[10px] font-semibold tracking-wider uppercase shrink-0 px-1.5 py-0.5 border",
              statusConfig.colorClass,
              isActive ? "border-water/30 bg-water-500/10" : "border-stone-600 bg-bg-surface",
            )}>
              {statusConfig.label}
            </span>
          </div>

          {/* Type label */}
          <p className="font-mono text-[10px] text-text-tertiary mt-0.5">
            {TASK_TYPE_LABELS[task.type]}
          </p>

          {/* Progress bar (for running tasks) */}
          {task.status === "running" && (
            <div className="mt-2">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[10px] text-text-secondary">
                  {task.message ?? "处理中..."}
                </span>
                <span className="font-mono text-[10px] font-semibold text-water tabular-nums">
                  {task.progress}%
                </span>
              </div>
              <div className="h-2 bg-bg-deepslate border border-stone-600 overflow-hidden">
                <div
                  className="h-full bg-water transition-[width] duration-300"
                  style={{ width: `${task.progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Completed message */}
          {task.status === "completed" && task.message && (
            <p className="font-mono text-[10px] text-emerald mt-1">{task.message}</p>
          )}

          {/* Error message */}
          {isFailed && task.error && (
            <div className="mt-1.5 px-2 py-1 bg-lava-500/10 border border-lava/30">
              <p className="font-mono text-[10px] text-lava leading-relaxed break-all">
                {task.error}
              </p>
            </div>
          )}

          {/* Time */}
          <p className="font-mono text-[10px] text-text-tertiary mt-1.5">
            {task.completedAt
              ? formatTime(task.completedAt)
              : formatTime(task.createdAt)}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex flex-col gap-1 shrink-0">
          {isActive && task.cancellable && (
            <button
              onClick={() => onCancel(task.id)}
              className={cn(
                "flex items-center justify-center size-6 border border-stone-600",
                "text-text-tertiary hover:text-lava hover:border-lava",
                "hover:bg-lava-500/10",
                "transition-[color,border-color,background-color] duration-[150ms]",
              )}
              title="取消任务"
            >
              <X className="size-3" />
            </button>
          )}
          {!isActive && (
            <button
              onClick={() => onRemove(task.id)}
              className={cn(
                "flex items-center justify-center size-6 border border-stone-600",
                "text-text-tertiary hover:text-text-primary hover:border-stone-500",
                "hover:bg-bg-surface",
                "transition-[color,border-color,background-color] duration-[150ms]",
              )}
              title="移除任务"
            >
              <Trash2 className="size-3" />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ===========================================================================
// Empty State
// ===========================================================================

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6">
      <div className="flex items-center justify-center size-16 border-2 border-stone-600 bg-bg-elevated mb-4">
        <Circle className="size-8 text-stone" />
      </div>
      <p className="font-mono text-sm font-semibold text-text-secondary mb-1">
        暂无任务
      </p>
      <p className="font-mono text-[11px] text-text-tertiary text-center leading-relaxed">
        下载版本、安装插件或启动游戏时
        <br />
        任务会显示在这里
      </p>
    </div>
  );
}

// ===========================================================================
// TaskPanel Component
// ===========================================================================

export function TaskPanel() {
  const {
    tasks,
    taskPanelOpen,
    setTaskPanelOpen,
    updateTask,
    removeTask,
    clearFinishedTasks,
  } = useAppStore();

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === "pending" || t.status === "running"),
    [tasks],
  );

  const hasFinishedTasks = useMemo(
    () => tasks.some((t) => t.status === "completed" || t.status === "failed" || t.status === "cancelled"),
    [tasks],
  );

  const handleCancel = (id: string) => {
    updateTask(id, { status: "cancelled", completedAt: Date.now(), message: "已取消" });
  };

  const handleRemove = (id: string) => {
    removeTask(id);
  };

  return (
    <AnimatePresence>
      {taskPanelOpen && (
        <>
          {/* Overlay */}
          <motion.div
            key="task-panel-overlay"
            className="fixed inset-0 z-40 bg-black/40"
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={() => setTaskPanelOpen(false)}
          />

          {/* Panel */}
          <motion.aside
            key="task-panel"
            className={cn(
              "fixed right-0 top-0 bottom-0 z-50",
              "flex flex-col",
              "bg-bg-deepslate border-l-2 border-stone-600",
              "shadow-[-8px_0px_0px_rgba(0,0,0,0.3)]",
            )}
            style={{ width: PANEL_WIDTH }}
            variants={panelVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b-2 border-stone-600">
              <div className="flex items-center gap-2">
                <h2 className="font-mono text-sm font-semibold text-text-primary tracking-wider uppercase">
                  任务队列
                </h2>
                {activeTasks.length > 0 && (
                  <span className="font-mono text-[10px] font-bold text-water bg-water-500/10 px-1.5 py-0.5 border border-water/30">
                    {activeTasks.length}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1">
                {hasFinishedTasks && (
                  <button
                    onClick={clearFinishedTasks}
                    className={cn(
                      "flex items-center gap-1 px-2 py-1",
                      "font-mono text-[10px] text-text-tertiary",
                      "border border-stone-600",
                      "hover:text-lava hover:border-lava",
                      "hover:bg-lava-500/10",
                      "transition-[color,border-color,background-color] duration-[150ms]",
                    )}
                  >
                    <Trash2 className="size-3" />
                    清除已完成
                  </button>
                )}
                <button
                  onClick={() => setTaskPanelOpen(false)}
                  className={cn(
                    "flex items-center justify-center size-7",
                    "text-text-tertiary hover:text-text-primary",
                    "border border-transparent hover:border-stone-600 hover:bg-bg-elevated",
                    "transition-[color,border-color,background-color] duration-[150ms]",
                  )}
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>

            {/* Task list */}
            <div className="flex-1 overflow-y-auto p-3">
              {tasks.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="flex flex-col gap-2.5">
                  {tasks.map((task, index) => (
                    <TaskItem
                      key={task.id}
                      task={task}
                      index={index}
                      onCancel={handleCancel}
                      onRemove={handleRemove}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2.5 border-t-2 border-stone-600">
              <p className="font-mono text-[10px] text-text-tertiary text-center">
                {tasks.length > 0
                  ? `${tasks.length} 个任务${hasFinishedTasks ? ` · ${tasks.filter((t) => t.status === "completed" || t.status === "failed" || t.status === "cancelled").length} 个已完成` : ""}`
                  : "任务队列为空"}
              </p>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}