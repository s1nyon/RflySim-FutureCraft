# 决策：不安装 UE Editor（2026-08-07）

## 结论

**本工程不安装 UE Editor，也禁止在后续会话中反复询问“是否安装 UE”。**
赛道地图问题使用现有动态砖块 + SLAMScene 方案临时解决并已通过 live 验证
（地图加载成功、Mid360 可见）。UE 静态地图
（`PredictedNarrowCourseV1.umap`）方案搁置，除非用户明确重新提出。

## 背景

- `docs/prompts/2026-08-03-continue-stage8-static-map.md` 曾要求用 UE4
  Editor 生成自有静态地图；本机没有 UE4 Editor，用户明确表示不打算安装。
- RflySim3D 是 UE4 4.27 运行时工程，Cook 版本必须匹配，不能用 UE5 资源
  混用；在没有编辑器的情况下无法按原 prompt 流程 Cook 静态关卡。
- 地图问题的现状：SLAMScene + 动态砖块（`narrow_course_ue_loader.py`）
  方案可用，34 个赛道对象正常投放，Mid360 扫描正常；不再依赖静态 UE 地图。

## 约束（写进 AGENTS.md 硬性规则）

- 不得以“为了地图”为由建议或安装 UE Editor。
- 后续 live 启动直接走 `scripts\start_predicted_course_two_uav.bat`
  （SLAMScene + 动态赛道），不再评估 UE 静态地图。
- 若未来确需 UE 静态地图，必须由用户主动提出，并先确认 UE4 Editor
  可用性（注册表/安装路径/可复用 .uproject）再继续。
