# 2026-11-17 通话音频服务等待声卡

## 现象与原因

15:02–15:18 那次启动没有注册 OnePlus10Pro 声卡，因此也没有 MultiMedia5/6 Voice PCM。内核在开机约 20.772 秒依次报告 `wcd9380-codec ... Initialization not complete`、`snd_soc_component_probe() on audio-codec` 返回 `-110`、`snd-sc8280xp sound: failed to instantiate card -110`。服务在 `main()` 中立即调用 `find_pcms()`，异常退出后由 systemd 每 5 秒重启；该次启动到 15:18:33 已重启 234 次。缺少 PCM 是声卡探测失败的结果，重复启动是服务的错误处理缺陷。

## 修正与验证

- 服务启动时每 5 秒检查语音 PCM。缺失时保持进程运行，只在错误信息变化时记日志；PCM 出现后继续初始化并监听通话。收到停止信号可立即退出。
- 通话期间如果 PCM 消失，创建语音会话失败后恢复桌面声卡 profile，并在通话仍在进行时重试，不让异常杀死服务。语音图打开失败同样恢复桌面 profile。
- 主机通话服务测试 20 项通过，包括缺 PCM 后恢复、停止等待和通话期间缺 PCM 的重试。`bash scripts/check.sh` 在 WSL 发行版 `NegroniBuild-Ubuntu-26.04` 中通过。
- 15:58 在手机确认没有通话后，仅安装新的 Python 脚本并重启该服务，未重启手机或刷写。手机文件 SHA-256 与仓库文件一致（`8c7c3990db0122d0ce2992c94cb31c061f338267543133d697a9ffdc7d585548`）。当前启动已注册 8 个 PCM；更新后服务为 `active/running`，`NRestarts=0`，日志为 `waiting for calls`。

没有为了模拟缺 PCM 而卸载、重新绑定声卡或重启手机；手机上的缺 PCM → 恢复路径及更新后的实际通话尚未实测。等待逻辑阻止服务反复重启，但不修复 WCD9380 偶发初始化超时；当声卡整个启动都未注册时，通话音频仍不可用，需要继续排查 SoundWire / 编解码器初始化。
