# 端到端自动化: ClickUp 任务 -> GitHub Workflow

**目标**: 在 ClickUp 建任务、打个标签，GitHub Actions 里就自动出现对应的 workflow 文件。
中间不需要沙箱、不需要 SSH、不需要 Lightning、不需要人手动改文件。

## 为什么长这样

| 环节 | 能不能 | 原因 |
|---|---|---|
| Brain 沙箱直连网络 | 否 | 沙箱无出网 (DNS 挂 / TLS 零字节 EOF)，SSH 到 Lightning 永远不可能 |
| ClickUp GitHub 集成写普通路径 | 能 | `src/`、`scripts/`、`automation/` 都能写 |
| ClickUp GitHub 集成写 `.github/workflows/` | 不能 | `Insufficient scope: required "repo workflow"` |
| GitHub App (ClickUp-zzview-CI) 写 workflows | 能 | App 权限含 `Workflows: read & write` |
| GitHub Actions runner 出网 | 能 | 同时能访问 api.github.com 和 api.clickup.com |

所以真正的执行者是 **Actions runner**: 它用 App 私钥换 installation token，
再用 token 写 workflow 文件。Lightning Studio 在这个架构里已经不需要了。

## 一次性配置 (约 3 分钟，之后永久免手动)

### 1. 加 Repo Secrets
`Settings -> Secrets and variables -> Actions -> New repository secret`

| Name | Value |
|---|---|
| `APP_ID` | `4964810` |
| `APP_PRIVATE_KEY` | `clickup-zzview-ci.*.private-key.pem` 全文，含 BEGIN/END 行 |
| `INSTALLATION_ID` | `162184021` (可省略，脚本会自己查) |
| `CLICKUP_TOKEN` | ClickUp 个人 token，`Settings -> Apps -> API Token` 生成，`pk_` 开头 |
| `CLICKUP_LIST_ID` | 要监听的 List ID |

### 2. 建唯一需要手动的文件
把 `automation/factory.yml` 的内容原样贴到 `.github/workflows/factory.yml`。
提交那一刻 workflow 就会第一次运行。

### 3. 完事
之后所有 workflow (包括改 factory 自己的逻辑) 都走自动化通道。

## 用法

### 通道 A: ClickUp 任务 (主通道)

1. 在被监听的 List 里建任务
2. 打标签 `create-workflow`
3. 描述里写规格:

```
template: rust-release
file: release.yml
```

或者直接贴完整 YAML (fenced yaml 代码块)，factory 会原样写进去。

4. 最多 10 分钟内 (或下一次 push 时立刻) factory 会:
   创建/更新 workflow 文件 -> 在任务下评论 commit 和 Actions 链接 ->
   把 `create-workflow` 换成 `workflow-created`，保证不重复触发。

`file:` 省略时用任务名的 slug 当文件名。

### 通道 B: 仓库请求文件

往 `automation/requests/` 丢 json，push 即生效:

```json
{ "file": "deploy.yml", "template": "rust-ci", "message": "factory: deploy" }
```

内容一致时跳过，重复运行安全。

## 内置模板

| 名字 | 内容 |
|---|---|
| `rust-ci` | 三平台 `cargo build` + `cargo test`，Linux 装 X11/xkb 依赖，`generate-lockfile` 兜住无 Cargo.lock |
| `rust-release` | 三平台 release 构建 + 真机截图 (`scripts/demo.sh`, `ICED_BACKEND=tiny-skia`) + 上传产物 + 发 release，**tag 从 Cargo.toml 读**，不再硬编码 v0.1.0 |
| `node-ci` | `npm install` + `npm test` |

## 结果在哪看

- `automation/log/last-run.json` — 每次运行的完整结果，直接读文件，不需要 CI 日志权限
- 对应 ClickUp 任务下的评论
- <https://github.com/supercubegame/zzview/actions>

## 踩过的坑 (别再踩)

1. 提交信息里不要出现 skip-ci 之类字样，整个 run 会被 GitHub 跳过
2. `Cargo.toml` 的 `opt-level` 必须是整数或 `"s"`/`"z"`，写 `"2"` 会变成清单解析错误，
   表现是 1 秒内 exit 101，看着像编译错，其实根本没开始编译
3. 没有 `Cargo.lock` 时依赖会漂移，`iced = "0.12"` 拉到的 API 和 0.4 时代完全不同
4. CI 里跑 GUI: runner 无 GPU，必须 `ICED_BACKEND=tiny-skia` 走软件渲染，
   否则 Xvfb 抓到的是 240 字节空白帧；截图要 OCR 验证内容，别只看文件大小
5. workflow 里的 release tag 别硬编码版本号，用 Cargo.toml 里的真实版本
