# Live startup 期间 Windows 蓝屏：0x1E（2026-08-25）

> 状态：**HISTORICAL / NOT REPRODUCED IN CLOSURE RUNS**
> 影响：Infrastructure Iteration 的第 3 次 pre-change startup timing、后续 startup optimization live 验证和 full flight regression
> 不影响结论：Phase 1 TF / Frame Contract 仍为 CLOSED；本事故尚未证明由 ROS、PX4、Faster-LIO、EGO 或本轮代码引起

> 2026-08-25 后续状态：用户恢复 live 工作后，3 次正式 fresh startup 与 2 次 fresh
> 完整双机路线均通过，未再发生宿主机崩溃。因此该单次事件不再阻塞当前 infrastructure
> baseline；驱动级根因仍未由符号化 dump 证明，保留为宿主机历史风险。闭环证据见
> [`2026-08-25-infrastructure-recovery-closure.md`](../evidence/2026-08-25-infrastructure-recovery-closure.md)。

## 1. 事件

2026-08-25 15:23:08（Asia/Shanghai）启动第 3 次 pre-change fresh stack：

```text
stack_id: stack-20260825T072308Z-997bbdde
git_commit: cd90478beb44bdec8e5010c2f761f0f221fb23f5
```

约 15:24:13 Windows 蓝屏并自动重启。该 run 不能计入成功 timing sample，也没有执行
arming、mission 或 flight。重启后 manifest 中所有已登记进程均已退出，端口已释放；
manifest 没有标准 stop 记录，因为宿主机在 run 中崩溃。

崩溃前 manifest 已登记双 PX4、roscore、双 MAVROS、双 sensor bridge 和 Faster-LIO；
尚未记录整体 READY。

## 2. Windows 证据

Kernel-Power Event 41（2026-08-25 15:25:23）记录：

```text
BugcheckCode=30                         # decimal 30 = 0x1E
BugcheckParameter1=0xffffffffc0000005  # access violation
BugcheckParameter2=0xfffff80362ef64f1
BugcheckParameter3=0xfffff888cd8cebf8
BugcheckParameter4=0xffffe08102c59920
LongPowerButtonPressDetected=false
```

Windows minidump：

```text
C:\Windows\Minidump\082526-6296-01.dmp
size: 2,554,244 bytes
last write: 2026-08-25 15:25:25
```

崩溃窗口内没有发现 WHEA provider 事件。当前机器没有可用的 WinDbg/dumpchk，
因此本轮没有得到符号化 call stack 或 `MODULE_NAME`，不能判定故障驱动。

## 3. 同时发生的异常

System log 显示 NVIDIA LocalSystem Container 在崩溃前已持续反复异常终止，
Service Control Manager 7023/7031 事件约每 6–10 秒重复一次，且一直持续到
15:24:06。当前显示设备/驱动包括：

```text
NVIDIA GeForce RTX 4060
driver: 32.0.15.6094
driver date: 2024-08-14

Todesk Virtual Display Adapter
driver: 16.44.2.509
driver date: 2023-04-24
```

这是一条强时间相关线索，**不是根因证明**。没有 dump 符号分析前，不应把事故直接归因于
NVIDIA、Todesk、RflySim3D、VcXsrv 或本轮 launcher 改动。

## 4. 本轮处理

- 立即停止所有后续 live startup、RViz live 和 flight regression。
- 不使用 `taskkill`、`pkill`、`wsl --shutdown` 或名称扫杀做恢复。
- 保留 minidump、Windows event 和 run-scoped manifest 作为证据。
- 仅继续离线开发、静态审计和 focused tests。
- Infrastructure Iteration 在 live 验证层保持 BLOCKED；不得报告 3/3 startup 或 2/2 flight PASS。

## 5. 恢复 live 前置条件

1. 使用 WinDbg（匹配 Microsoft symbols）分析该 minidump，至少获得
   `!analyze -v`、`MODULE_NAME`、`IMAGE_NAME` 和 faulting stack。
2. 根据 dump 结果处理对应宿主机驱动/服务；如果仍指向图形链，优先验证 NVIDIA 与
   virtual display 驱动，而不是修改飞行栈参数。
3. 运行一次 no-stack 宿主机稳定性观察，确认 NVIDIA container 不再持续 crash-loop。
4. 再次 live 前先执行标准 doctor/status/ownership 检查；不得把 crash run 当作 clean stop。
5. 恢复后先进行一次 no-arm、RViz OFF 的受控 startup，再决定是否恢复 timing/regression。
