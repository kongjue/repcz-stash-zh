# Repcz Stash 中文版

基于 [Repcz/Tool](https://github.com/Repcz/Tool/tree/X/Stash) 的 Stash 配置，仅汉化分组名称和对应引用；规则文件镜像到本仓库。保留原作者署名与 MIT 许可证。

## 下载与使用

- [中文版配置](https://raw.githubusercontent.com/kongjue/repcz-stash-zh/main/Stash/Stash.yaml)
- [查看配置](Stash/Stash.yaml)
- [规则目录](Stash/Rules)
- [自动同步运行记录](https://github.com/kongjue/repcz-stash-zh/actions/workflows/sync.yml)

下载配置后，在 Stash 的配置编辑器中，将 `proxy-providers.Subscribe.url` 的 `http://your-service-provider` 替换为自己的节点订阅。模板本身不包含任何私人节点、订阅地址或凭据。

原版的地区分组、自动测速方式、DNS 和分流顺序均保留；不会自动套用任何人的自用偏好。原版要求 Stash 2.6.0 或更高版本。这里只做结构校验，尚未在手机上实测。

## 自动更新

GitHub Actions 每 6 小时检查 `Repcz/Tool` 的 `X` 分支，也可以在 Actions 页面手动运行。定时任务按 GitHub 调度执行，可能延迟。

一次同步读取同一个上游提交：完整镜像 `Stash/Rules/`，保存英文模板到 `upstream/Stash.yaml`，生成中文 `Stash/Stash.yaml`，并把规则下载链接改成本仓库的 `main` 分支。远程规则仍保持原版的每日刷新间隔。

脚本验证文件校验和、汉化范围、规则文件存在性、分组引用和循环；验证成功且有变化才提交。上游出现未知分组或不兼容格式时，工作流失败并保留上一次发布结果，等待更新翻译映射。上游提交和规则摘要记录在 [upstream/state.json](upstream/state.json)。

本地操作：

```sh
python -m pip install -r requirements.txt
python scripts/sync_upstream.py --repository kongjue/repcz-stash-zh
python -m unittest discover -s tests -v
```

GitHub 公共仓库长期没有活动时可能暂停定时工作流，可在 Actions 页面重新启用。工作流不需要额外配置个人访问令牌，使用仓库自带的 `GITHUB_TOKEN` 提交生成文件。

## 来源

配置和规则来自 Repcz 及其引用的规则项目，规则内的来源说明保持原样。本项目只维护中文展示和镜像同步，不是 Repcz 官方发布。
