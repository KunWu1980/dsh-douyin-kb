# 抖音转OB（douyin-kb）：四项能力测试与评估

测试时间：2026-11-10（v1.1.0 更新）｜ 环境：DSH 桌面版（profile `desktop`）、Windows、Node 24.x、Python 3.12。

结论速览：

| # | 问题 | 结论 | 现状 |
| --- | --- | --- | --- |
| 1 | 能被 DeepSeek Harness 安装？ | ✅ 可以 | 本地目录（link）、本地 tarball 两种来源实测安装成功 |
| 2 | 安装后能提供 UI 界面？ | ✅ 已实现 | 左侧栏「抖音转OB」图标 + 主面板（录入框 / 开始抓取 / 注意事项） |
| 3 | 能发布到 GitHub 并被下载安装？ | ✅ 协议支持，⚠️ 部分网络受限 | 发布文件已备好，尚未建远端仓库 |
| 4 | 能上架 DSH 插件市场？ | ✅ 可行，需人工提 PR | 条目模板已备好，未提交 |

---

## 1. 可被 DSH 安装 —— 实测通过

`plugin_manager install_bundle` 的 spec 解析器（`@deepseek-ai/dsh-plugin-manager/lib/types/install-spec.js` 的 `parseInstallSpec`）支持四类来源，用官方解析器逐条验证：

```
"<plugin-dir>"                                    -> {"kind":"path", ...}
"<dist>/local-douyin-kb-1.0.0.tgz"                -> {"kind":"tarball", ...}
"github:<owner>/douyin-kb"                        -> {"kind":"git","host":"github.com"}
"https://github.com/<owner>/douyin-kb"            -> {"kind":"git","host":"github.com"}
"git+https://github.com/<owner>/douyin-kb.git"    -> {"kind":"git","host":"github.com"}
"douyin-kb"                                       -> {"kind":"registry","name":"douyin-kb"}
"douyin-kb@1.2.3"                                 -> {"kind":"registry","range":"1.2.3"}
"https://example.com/p.tgz"                       -> {"kind":"tarball","host":"example.com"}
"..\rel"                                          -> ERR a local path must be absolute
```

实装结果：

- **本地目录（link）**：`applied`，`douyin_kb` 工具立刻可用，`probe` / `ingest` 实测成功；源码目录放在工作区内，改代码后 `set_bundle` 关→开即可重载。
- **本地 tarball**：`npm pack` → 约 15.9 KB / 9 个文件（含 README、LICENSE、`assets/douyin_kb.py`），`install_bundle` 传绝对路径 → `applied`。
- **卸载**：用无关的探针插件 `@local/probe-rm` 做了对照实验——`remove_bundle` 后源目录文件完好，说明卸载本身不会删用户源码目录（曾观察到源码被清空发生在 `link:` → `file:` 的依赖替换过程中，属 pnpm 重新解析 side effect，建议源码纳入 git）。

注意事项：

- `application: applied` 只代表 profile 写入 + 版本登记成功；**替换已安装 bundle 的 JS 模块需要重启应用**才会加载新代际（实测旧模块实例仍按旧路径找脚本，报 `can't open file ...\assets\douyin_kb.py`）。
- 开发期改代码后要么重启，要么对 bundle 做 `set_bundle` 关→开触发重载。
- 依赖安装会重新解析 profile 的 pnpm 依赖树，可能顺带升级别的插件（本次 `billion-context` 0.1.212 → 0.1.213）。

## 2. UI 界面 —— 已实现（左侧栏面板）

DSH 的 UI 插件协议（`cordis-plugin-development/references/ui-plugin.md` + `templates/decoration`）：

```jsonc
// package.json
"exports": { ".": "./index.js", "./client": "./client.js" },
"dsh": {
  "bundle": { "patch": "./cordis.patch.yml" },
  "client": { "platform": "web", "immediately": true, "inject": ["@deepseek-ai/dsh-client-ui-sidebar"] }
}
```

```js
// client.js —— 浏览器侧懒加载工厂，id 必须等于包名
window.__ModuleLoader__.load({
  id: '@local/douyin-kb',
  factory(require) {
    const React = require('react');
    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: 'douyin-kb' }, Panel));
        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({ name: 'sidebar.panellist', id: 'douyin-kb', order: 30 }, Icon));
      },
    };
  },
});
```

槽位要点：`sidebar.panellist` 是左侧栏图标列表（注册 `{ id, order, label }`，组件收到 `{ size, active }`），`main` 是按 key 分发的主面板（注册 `{ key }`，**key 与 panellist 的 id 相同**即点图标切面板）。`main` 作用域是 root、拿不到会话绑定，所以面板动作通过 `ctx.remote.commands.execute(sessionId, '/douyin <链接>')` 调用宿主命令，没有会话时退回 `ctx.uiWorkspace.startSession(undefined, { prompt })` 预填草稿。

> 模板里给的 `conversation.composer.dock` 在本构建的 `@deepseek-ai/dsh-client-ui-conversation/lib/client.js` 中**不存在**（命中 0），照抄模板会静默不渲染。选槽位前先用运行时槽位清单核对。

`dshmarket` 1.66.35 同时声明 `dsh.bundle` 与 `dsh.client` 并在设置页正常渲染，是"UI 插件在本构建可用"的直接证据；本插件 v1.1.0 起同样具备。

## 3. 发布到 GitHub —— 协议支持，部分网络受限

- DSH 侧：`github:<owner>/<repo>`、`https://github.com/<owner>/<repo>`、`git+https://...` 都被识别为 `kind: git`；安装前会用 `git ls-remote` 预检（默认 5s 超时）。
- 仓库形态：根目录即插件目录（`package.json` + `cordis.patch.yml` 在根），无构建步骤、零 npm 依赖，`dsh plugin add github:<owner>/<repo>` 直接可用源码安装。
- 已补齐发布用文件：`README.md`（含模型下载、配置、排错）、`LICENSE`（MIT）、`.gitignore`、`docs/market-entry.yml`。
- ⚠️ 测试网络实测：`git ls-remote https://github.com/...` 挂起 >2 分钟未返回；`raw.githubusercontent.com` 与 `awesome-dsh-plugin.com` 直连超时；仅 `cdn.jsdelivr.net` 通畅。**在该网络下从 GitHub 安装会卡在预检**，需要代理或镜像。
- 未做实机验证的部分：没有可用的 GitHub 账号凭据，未创建远端仓库、未跑通真实的 `github:` 安装。

## 4. 上架 DSH 插件市场 —— 可行，需 PR

市场数据流：`dshmarket` 每次打开实时拉取 `https://awesome-dsh-plugin.com/plugins.json`（实测约 11.9 MB、`count: 9959`、`updated: 2026-11-10`），数据源是精选仓库 `awesome-dsh-plugin/awesome-dsh-plugin` 的 `data/plugins/*.yml`（一插件一文件，README 由脚本生成，不要手改）。

收录硬条件：

1. `package.json` 声明 **`dsh.bundle`**（本插件满足；只有 `dsh.client` 不行，CI 自动检查）；
2. 仓库创建满 **1 天**；
3. 仓库带 **`dsh-plugin`** topic；
4. 提交 `data/plugins/<owner>__<repo>.yml`：`url` 与仓库完全一致、`name: owner/repo`、`category` 取固定集合（`agi ui usage theme model identity session memory tools wsl browser vision voice docs skill workflow git notify dev security remote market fun`）、`description.en` 必填且含 `": "` 时要加引号；
5. 发 npm 是可选的，但发了的话 `package.json` 的 `repository` 必须指回被收录的仓库；条目 YAML 里不要手写 `npm:`。

本插件选的分类是 `tools`，条目模板已写在 `docs/market-entry.yml`（含校验要点注释）。合并后市场即可一键安装，安装走 `github:` 源码，不强制发 npm。

未做：真实建仓、PR、合并后的一键安装验证（都依赖 GitHub 账号与可用网络）。
