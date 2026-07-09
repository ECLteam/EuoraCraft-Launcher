import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from ...common.logger import get_logger

logger = get_logger("instances")


class InstancesManager:
    def __init__(self):
        self.instances: dict[str, dict] = {}
        self._lock = threading.Lock()

        self.output_log: Callable[[str], None] = print  # 默认输出到控制台
        self._exit_callback: Callable[[int], None] = print

    def set_output_log(self, callback: Callable[[str], None]) -> None:
        self.output_log = callback

    def set_exit_callback(self, callback: Callable[[int], None]) -> None:
        self._exit_callback = callback

    def _read_stream(
        self,
        stream,
        callback: Callable[[str], None],
        proc: subprocess.Popen | None = None,
        exit_callback: Callable[[int], None] | None = None,
        instance_id: str = "",
    ) -> None:
        try:
            for line in iter(stream.readline, ""):
                if line:
                    callback(line.rstrip("\n"))
        finally:
            stream.close()
            # 子进程已退出，管道关闭，获取返回码并回调
            if proc and exit_callback:
                return_code = proc.wait()  # 此时 wait 会立即返回
                with self._lock:
                    self.instances.pop(instance_id, None)
                exit_callback(return_code)

    def create_instance(
        self,
        instance_name: str,
        instance_type: str,
        args: str | list[str],
        cwd: str | Path | None = None,
        new_session: bool = True,
        only_stdout: bool = False,
        std_in: bool = False,
        log_callback: Callable[[str], None] | None = None,
        exit_callback: Callable[[int], None] | None = None,
    ) -> str:
        """
        创建一个新的实例（子进程），并自动启动日志读取线程
        :param instance_name: 实例名称
        :param instance_type: 实例类型（如 "MinecraftClient", "MinecraftServer"）
        :param args: 命令行参数（字符串或列表）
        :param cwd: 工作目录
        :param new_session: 是否以新会话启动
        :param only_stdout: 是否将 stderr 合并到 stdout
        :param std_in: 是否启用 stdin 管道（可通过 send_stdin 发送输入）
        :param log_callback: 可选，专门为此实例设置日志回调
        :param exit_callback: 进程退出时回调，参数为退出码
        :return: 实例 ID（uuid4.hex）
        """
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if not only_stdout else subprocess.STDOUT,
            stdin=subprocess.PIPE if std_in else None,
            bufsize=1,
            start_new_session=new_session,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        # DEBUG: 输出实际传给 Popen 的 args
        logger.debug(f"[DEBUG Popen] args type: {type(args).__name__}")
        if isinstance(args, str):
            cp_idx = args.find("-cp ")
            if cp_idx >= 0:
                logger.debug(f"[DEBUG Popen] args around -cp (+250): {args[cp_idx:cp_idx+250]}")
            else:
                logger.debug(f"[DEBUG Popen] args NO -cp! first 300: {args[:300]}")
        else:
            logger.debug(f"[DEBUG Popen] args list len: {len(args)}, first 5: {args[:5]}")
        logger.debug(f"[DEBUG Popen] cwd: {cwd}")

        callback = log_callback or self.output_log
        exit_callback = exit_callback or self._exit_callback

        instance_id = uuid4().hex
        # stdout 线程：负责读取日志 + 监控进程退出
        t_out = threading.Thread(
            target=self._read_stream, args=(proc.stdout, callback, proc, exit_callback, instance_id), daemon=True
        )
        t_out.start()

        # stderr 线程（若未合并）：仅读取日志
        t_err = None
        if not only_stdout and proc.stderr:
            t_err = threading.Thread(target=self._read_stream, args=(proc.stderr, callback), daemon=True)
            t_err.start()

        with self._lock:
            self.instances.update(
                {
                    instance_id: {
                        "Name": instance_name,
                        "ID": instance_id,
                        "Type": instance_type,
                        "StdIn": std_in,
                        "Instance": proc,
                        "Threads": [t_out, t_err],
                        "ExitCallback": exit_callback,
                    }
                }
            )
        return instance_id

    def send_stdin(self, instance_id: str, data: str) -> None:
        """向指定实例的 stdin 写入数据（仅当 std_in=True 时有效）"""
        with self._lock:
            inst = self.instances.get(instance_id)
            if not inst or not inst["StdIn"]:
                return
            proc: subprocess.Popen = inst["Instance"]
        if proc.stdin:
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def stop_instance(self, instance_id: str, terminate: bool = True) -> None:
        """
        停止指定实例
        :param instance_id: 实例ID
        :param terminate: True 使用 terminate()，False 使用 kill()
        """
        with self._lock:
            inst = self.instances.get(instance_id)
            if not inst:
                return
            proc: subprocess.Popen = inst["Instance"]
        if proc.poll() is None:  # 进程仍在运行
            if terminate:
                proc.terminate()
            else:
                proc.kill()

    def get_instances_info(self) -> list:
        return list(self.instances.values())

    def shutdown_all(self, kill: bool = True) -> None:
        """终止所有正在运行的实例"""
        with self._lock:
            instances_copy = list(self.instances.items())  # 锁内获取副本
        for inst_id, inst in instances_copy:  # 锁外执行 kill/wait，避免阻塞其他线程
            proc: subprocess.Popen = inst["Instance"]
            if proc.poll() is None:
                if kill:
                    proc.kill()
                else:
                    proc.terminate()
                # 等待进程结束，避免僵尸进程阻塞退出
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"实例 {inst['ID']} 进程未在5秒内退出")
            with self._lock:
                self.instances.pop(inst_id, None)
