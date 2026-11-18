# GitHub Actions 镜像发布

发布镜像中的 `oneplus` 使用[项目默认初始密码](../scripts/image_credentials.py)，适用于桌面登录、SSH 和 `sudo`。root 密码由每次构建随机生成。

修改根目录的 [`IMAGE_VERSION`](../IMAGE_VERSION) 并随本次发布内容推送到 `main`。版本使用 `主版本.次版本.修订号`，例如 `0.1.1`，每次发布使用尚未发布的版本号。只有版本值发生变化的推送才会开始打包。也可以在 Actions 的 **Build and publish image** 中选择 `main` 后手动运行。

新版本进入构建队列时，GitHub 会取消旧的构建任务。发布前会重新查询 `main` 上的版本，草稿上传结束后再查一次。已被替代的草稿会留在 Releases 草稿列表中。上传失败时，可以重跑原 workflow，继续发布同一提交的草稿。

构建任务使用 `ubuntu-26.04`，清理预装的 Android SDK、.NET SDK 和 GHCup 目录，再运行 `build.sh 7.3` 及产物校验。Actions 日志包含可用磁盘和构建用时。打包产物通过保留一天的 Actions artifact 传给单独的发布任务。

发布任务以构建使用的源码提交创建 `image-v<版本>` 标签。Release 页面列出从最近的前序镜像标签到本次构建的提交标题、短哈希和正文。首次发布会列出当前提交的历史记录。

## 下载和校验

从同一个 Release 下载 `boot.img`、`vendor_boot.img`、`recovery.img`、`vbmeta.img`、`sparse_root.img.zst`、`build-result.json` 和 `SHA256SUMS`。在下载目录运行：

```sh
sha256sum -c SHA256SUMS
zstd -d sparse_root.img.zst
```

解压得到的 `sparse_root.img` 与同批次启动镜像配套使用。刷机前核对[刷机说明](flashing.md)中的机型、分区和固件条件。
