# 按需安装与调试应用

状态日期：2026-11-15。默认镜像包含硬件依赖、系统修复、中文字体、Angelfish 浏览器和 Snapshot 相机；游戏串流及专门调试工具由用户选择安装。下列脚本在手机的仓库副本中执行，不参与镜像构建。

## 硬件检查工具

```sh
sudo bash scripts/install-optional-apps.sh diagnostics
```

安装清单为 [optional-diagnostics.txt](../config/packages/optional-diagnostics.txt)：mpv 播放已知音视频、qpwgraph 查看 PipeWire 路由、System Monitor 观察负载与温度、Gwenview 查看拍摄结果。四个应用于 2026-11-14 已在手机安装，不能据安装成功推断各项硬件已验证。

如果调用者还没有自定义 System Monitor Overview，脚本为该用户安装 [overview.page](../config/optional/overview.page)。来源为 2026-11-14 手机改过的页面，已去掉磁盘 UUID 等实例颜色记录；GPU 面板改读 `gpu_top_thermal` / `gpu_bottom_thermal` 温度。ksystemstats 当前没有提供 Adreno 的 GPU 使用率，该改动没有实现 GPU 利用率采集；界面最终提示是否消失的对话没有完整验收，需在新安装后确认。已有自定义页面保留。

qpwgraph 先用于观察；手工改连线前阅读[音频](audio.md)，当前声卡曾因路由和 SoundWire 问题崩溃。相机、传感器、NFC 和定位的实际测试入口分别在对应硬件文档中，避免多个进程同时占用设备。

## KRDP 远程桌面（实机手工安装）

2026-11-17 在当前手机上通过 USB SSH 安装 Arch Linux ARM 的 `krdp 6.8.3-1` 及依赖，并启用 `app-org.kde.krdpserver.service` 用户服务。服务使用手机系统账号认证，生成的自签 TLS 证书与私钥只保存在手机的 `/home/oneplus/.local/share/krdpserver/`。用户服务覆盖配置把监听地址限定为 USB NCM 的 `10.55.0.1:3389`；Windows 侧 TCP 连接检查通过。`systemctl --user is-active` 为 `active`，`is-enabled` 为 `enabled`。KRDP 需要已登录的 Plasma 会话，不能远程操作 SDDM 登录界面。

首次从 Windows `mstsc` 连接时，证书提示后直接断开。14:31 手机日志有一次 `oneplus` 的 PAM 认证失败；`mstsc /prompt` 仍未显示账号输入框。Windows 凭据管理器为 `TERMSRV/10.55.0.1` 保存手机账号凭据后，14:35 的连接通过 PAM、进入软件 H.264 编码，用户确认已进入远程桌面。手机端桌面共享权限存储当时没有 `remote-desktop` 条目；随后按 KDE KRDP 设置模块的方式为 `org.kde.krdpserver` 写入 `kde-authorized/remote-desktop=yes`，读回正确，后续连接是否免确认未测。键鼠操作、熄屏后的连接、重新登录后的自启动和长期负载未单独验证。

Windows 可运行 `mstsc`，连接 `10.55.0.1:3389`，使用手机系统账号登录；若手机登录密码更改，Windows 保存的凭据也需要更新。当前只监听 USB 地址，Wi-Fi IP 不提供 RDP。手工安装、用户配置和证书尚未接进镜像打包；新镜像未构建、未刷入。未来若要经 Wi-Fi 使用，应先在 Plasma「系统设置 → 安全与隐私 → 远程桌面」设置独立的远程凭据并核对监听范围，不要把手机当前登录凭据或 TLS 私钥纳入 Git。

## Sunshine 串流服务

```sh
sudo bash scripts/install-optional-apps.sh sunshine
# 在已登录图形桌面的普通用户会话执行：
systemctl --user daemon-reload
systemctl --user enable --now negroni-sunshine.service
```

脚本固定安装 ARM64 AppImage `2026.914.233613`，来源为 Sunshine 官方发布路径，下载后核对 SHA-256 `d352134d9e6161ac1e3d7d1699fb0e5eff0a3460eee4d5cc131d52b04cb91152`。该哈希于 2026-11-15 从手机之前下载并运行的原始安装包只读核对。安装包和完整提取目录不入 Git；包内原有许可文件随提取目录保留。

新安装路径为 `/opt/negroni-sunshine/2026.914.233613`，由 root 所有。与 11-14 手动安装一样，启用 uinput/uhid，安装上游 udev 规则，并为程序设置 `cap_sys_admin,cap_sys_nice`。文件 capability 会让动态链接器忽略 `LD_LIBRARY_PATH`，历史服务因此启动失败；脚本用 patchelf 设置绝对 RUNPATH 后再设置 capability，保留这次修复。用户服务和桌面入口位于 [config/optional](../config/optional/)。新脚本没有在手机执行，新位置安装与启动未测；此前用户目录里的手动安装保留。

应用菜单中的 Sunshine 打开本机网页设置 `https://localhost:47990`；USB 连接电脑时是 `https://10.55.0.1:47990`。服务使用本地证书，浏览器会显示证书提示。首次自行设置管理账号并用 Moonlight 配对，仓库不预置凭据。

2026-11-14 手动安装已经启动、采集内屏，并选中软件 H.264 编码；手机使用 KWin Wayland、PipeWire、KDE portal。Iris 驱动列出 NV12 输入和 H.264/HEVC 输出，但当时 Sunshine 没有对应 V4L2/Iris 编码后端；Turnip 也没有提供所需 Vulkan Video 编码扩展。硬件编码、Moonlight 完整会话、手柄回传、音画同步、码率与延迟、长期温控均未测。

## 4:3 掌机的后续方向

目标是手机运行游戏，4:3 Linux 掌机显示和回传输入。内屏当前是 1080×2412，直接采集仍是竖长画面。建议建立独立的 4:3 虚拟显示，让游戏在目标分辨率下绘制，Sunshine 采集该输出；手机内屏预览另行处理。不能只修改客户端分辨率就推断服务器按 4:3 渲染。

此前讨论的起步目标为 1280×960、60 FPS、H.264、立体声和一个手柄，是待验证目标。优先核对编码和采集链路，再做输入、声音、重连及持续负载；原生 1440×3216 显示修复不必作为串流前提。虚拟输出、独立输入焦点及内屏拉伸预览尚未实现。
