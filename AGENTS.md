# AGENTS.md — AI 代理工作指南

本文件写给在本仓库工作的 AI 代理（Claude Code、Codex 等）。人类读者请从 [README.md](README.md) 开始。

---

## ⚠️ 第一件事：用 USB SSH 连接手机调试

**需要在手机上查看日志、运行命令、部署或验证时，首选 USB 网络 SSH，不要依赖 Wi-Fi。**

```sh
ssh -o BatchMode=yes -o ConnectTimeout=6 oneplus@10.55.0.1 'uname -r; uptime'
```

- 手机通过 USB 线接电脑的 **USB3 口**（USB2 口不可用）。手机侧 IP `10.55.0.1`，电脑侧 NCM 网卡静态 IP `10.55.0.2/24`。
- 电脑公钥已经授权，可以直接用 `BatchMode` 非交互执行命令，或用 `scp` 传文件。
- 用户 `oneplus`；`sudo` 需要密码（等于登录密码）。这台开发机的初始密码是 `3401778728`，**当前密码是 `123321`**（用户 2026-11-12 提供并要求记录在此）。密码不对时再向用户索要，不要自行搜索凭据文件。

### 禁止把 sudo 密码和脚本接到同一条标准输入

**禁止**把 `sudo -S` 的密码管道和 heredoc、`bash -s` 或其它脚本正文接到同一条标准输入。`sudo -S` 从标准输入读密码；后面的 heredoc 会盖掉这条管道，sudo 读到的是脚本正文（例如 `set -e`），不是密码。2026-11-14 17:20 的这次误用连错三次，`pam_faillock` 把 `oneplus` 临时锁定约 10 分钟。锁定期间正确密码也会被拒绝，日志是 `3 incorrect password attempts`，随后 `account temporarily locked`。

不要使用这种写法，也不要使用任何等价形式：

```bash
echo 123321 | sudo -S -p "" bash -s << "EOS"
set -e
...
EOS
```

密码被拒时先看 `faillock`，等解锁后再用当前密码。不要改试旧密码，不要反复重试把锁定延长，也不要据此判断密码已经改掉。

密码只交给 `sudo -S`，脚本另存为 LF 文件再执行，例如 `echo 123321 | sudo -S -p "" bash /tmp/script.sh`。也可以用 `SUDO_ASKPASS`。单独的 `echo 123321 | sudo -S -p "" 命令` 可以用，条件是这条命令不再从同一条标准输入读脚本。

- 连不上时依次尝试：
  1. 换到 USB3 口；
  2. 请用户检查 Windows NCM 网卡是否仍为 `10.55.0.2/24`（需要管理员，代理通常做不了）；
  3. 串口 `COM3`，115200 8N1，网络全挂时的救援通道；
  4. Wi-Fi SSH（IP 会变，最近为 `192.168.137.143`）。
- 全新刷入的镜像**还不包含**这条通道（手动安装，尚未接入构建），补装方法见 [docs/usb-debug.md](docs/usb-debug.md)。

完整说明、排错和手机侧组成：**[docs/usb-debug.md](docs/usb-debug.md)**。

### 手机操作的安全规则

- **刷写任何分区（`boot_*`、`vendor_boot_*` 等）或重启手机前，必须先征得用户同意。** 刷写前先备份原分区并记录 sha256。
- 先确认当前槽位和成功标记，避免 A/B 重试次数耗尽进入 recovery，见 [docs/boot-success.md](docs/boot-success.md)。
- 多个会话可能同时在用手机（音频、相机、基带、GPU）：不要随手 `systemctl reboot`，不要写 `usb_role`，不要重新绑定 UDC，否则会断掉所有人的连接。
- 音频：**不要 unbind/bind `qcom-apm`**（会丢失 GPR port 1）。声卡探测失败后再重新绑定，会出现 DSP mem-map error 1。
- qmicli 以 `oneplus` 身份调用时不要加 `-p`。

---

## 构建环境

- 真正的构建树在 WSL 发行版 **`NegroniBuild-Ubuntu-26.04`** 的 `/opt/negroni-build` 中。Windows 检出的 `linux/` 子模块是空的，内核源码在 `/opt/negroni-build/linux`（浅克隆，分支 `7.3`）。
- 从 Git Bash 调用 WSL 时，先把命令写成脚本，再这样执行：
  `MSYS_NO_PATHCONV=1 wsl -d NegroniBuild-Ubuntu-26.04 -- bash /mnt/c/...`。
  直接内联的 `$变量` 会被 Git Bash 改写。
- WSL 里的内核树可能有其他会话未提交的改动（例如相机的 DT 修改）。提交内核改动前先 `git diff` 并拆分 hunk，只提交自己的部分。
- 内核改动的流程：先在内核树中提交，再更新父仓库的 gitlink 和 `patches/linux/local-7.3.bundle`。浅克隆下重建 bundle 需要 `GIT_SHALLOW_FILE`，见 [patches/linux/README.md](patches/linux/README.md)。
- Windows 上用 Python 的 `write_text` 会写出 CRLF。复制到手机的 shell 脚本必须是 LF。
- 工作区里 `artifacts/**/oplus_battery_sm8450.[ch]` 显示为已修改，只是 CRLF/LF 差异，不要提交它们。

## 原厂驱动模块参考归档

- 用户已于 2026-11-13 明确授权将本机原厂模块纳入 Git 并推送；固定目录为 [`downloads/stock-drivers-20261113/`](downloads/stock-drivers-20261113/README.md)。此目录是下载产物忽略规则的精确例外，不要扩大到其他 `downloads/` 内容。
- 模块位于 `vendor_dlkm_b/lib/modules/`：**373 个 `.ko`**，连同原厂加载清单、依赖和分区元数据共 **382 个原厂文件、160,304,370 字节**。来源为本机 `super` 的 slot 1 `vendor_dlkm_b`，同槽 `my_manifest_b` 记录 `NE2210_15.0.0.401(CN01)`。
- `README.md` 记录来源和适用边界；`inventory.csv`、`inventory.json` 与 `SHA256SUMS` 记录全部路径、大小和哈希。更改或补充归档时必须核对来源、更新清单，并在归档目录执行 `sha256sum -c SHA256SUMS`。
- 原厂系统为 ColorOS 15 / Android 15；原厂模块面向 **Linux 5.10.209 内核**（5.10 不是 Android 系统版本），仅用于离线符号、反汇编和驱动逻辑对照；**不要直接加载到当前主线 7.3 内核，也不要将其接入镜像模块安装流程**。移植需对照板级版本、接口、时钟、电源与初始化顺序，再按子系统验证。
- 保留模块内嵌的 license / scmversion、原厂 NOTICE 和配套文件，不根据整机版本推断所有文件精确匹配同一公开源码提交。归档没有改变分区备份、镜像、固件、校准负载、凭据及原始日志不纳入 Git 的规则。

## 检查与提交

### 分支与提交规范（当前阶段）

- **暂不新建分支。所有功能、修复和文档都直接在 `main` 上进行**，不要创建 `feat/*`、`fix/*` 等本地分支或 worktree 分支。
- **一个功能对应一个提交**：同一功能的代码、配置、测试和文档放进同一个提交，不同功能分开提交；不要把无关改动混进去，也不要把一个功能拆成多个零碎提交。
- 只 `git add` 本功能涉及的文件，不要用 `git add -A`。
- 推送到远端前先征得用户同意。

```sh
bash scripts/check.sh
git diff --check
```

- 提交规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。没做过的实机验证要明确写“未测”，不能从模拟测试推断实机结果。
- 不要提交凭据、私钥、分区备份、镜像产物，也不要提交 `logs/` 下的原始日志。

## 文档与记录

- 当前状态汇总：[docs/status.md](docs/status.md)。各子系统：[音频](docs/audio.md)、[通话语音](docs/call-audio.md)、[基带/SIM/VoLTE](docs/modem.md)、[蓝牙](docs/bluetooth.md)、[GPU](docs/gpu.md)、[USB 调试](docs/usb-debug.md)。
- 完成一次实机调试后，更新对应子系统文档和 `docs/status.md`，写清日期、验证了什么、还没验证什么。原始日志放在 `logs/<主题>-<日期>/`（不纳入 Git），整理后的依据放在 `artifacts/`。
- 未提交的进行中工作：S5KJN1 超广角相机的 DT 修正（MCLK 24 MHz、reset 改为 gpio24 低有效）目前只存在于 WSL 内核树中，未提交，也未在手机上验证。USB2 gadget 的 LPM 补丁也只在 `logs/usb-debug-20261112/`，未应用。
