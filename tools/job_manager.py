# tools/job_manager.py
import psutil
import time
from pathlib import Path

class JobManager:
    def __init__(self):
        # 结构: {pid: {"cmd": str, "log": str, "start_time": float}}
        self.jobs = {}

    def add_job(self, pid: int | str, cmd: str, log_file: str):
        """注册一个后台任务"""
        # 【关键修复 1】: 无论传入的是 str 还是 int，统一转为 int 存储
        try:
            pid = int(pid)
        except ValueError:
            print(f"[JobManager Error] Invalid PID received: {pid}")
            return

        self.jobs[pid] = {
            "cmd": cmd,
            "log": log_file,
            "start_time": time.time(),
            "status": "running"
        }

    def check_jobs(self):
        """检查所有任务状态，返回摘要字符串"""
        if not self.jobs:
            return "No background jobs running."

        summary = []
        # 遍历副本以允许修改
        for pid, info in list(self.jobs.items()):
            # 【关键修复 2】: 从字典取出的 key 再次确保转为 int，防止 psutil 报错
            try:
                safe_pid = int(pid)
            except ValueError:
                summary.append(f"[Invalid PID] {pid}")
                continue

            # 检查进程是否存在 (传入 int)
            if psutil.pid_exists(safe_pid):
                # 进一步确认是不是僵尸进程或已结束
                try:
                    p = psutil.Process(safe_pid)
                    if p.status() == psutil.STATUS_ZOMBIE:
                        status = "zombie"
                    else:
                        status = "running"
                except psutil.NoSuchProcess:
                    status = "done"
            else:
                status = "done"
            
            # 计算耗时
            # 确保 start_time 也是数字
            start_time = float(info.get("start_time", time.time()))
            elapsed = int(time.time() - start_time)
            duration = f"{elapsed // 60}m {elapsed % 60}s"
            
            summary.append(f"[PID {safe_pid}] Status: {status.upper()} | Time: {duration} | Log: {info['log']} | Cmd: {info['cmd'][:30]}...")
            
            # 状态更新逻辑
            if status == "done" and info['status'] != "done":
                info['status'] = "done"

        return "\n".join(summary)

# 全局单例
JOBS = JobManager()