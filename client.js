window.__ModuleLoader__.load({
  id: '@local/douyin-kb',
  factory(require) {
    const React = require('react');
    const h = React.createElement;

    const NS = 'douyin-kb';
    const PANEL_ID = 'douyin-kb';

    const zh = {
      title: '抖音转OB（初学者适用）',
      panel: '抖音转OB',
      placeholder: '粘贴抖音分享链接或整段分享文案，例如 https://v.douyin.com/xxxxxx/',
      start: '开始抓取',
      starting: '正在抓取…',
      running: '正在抓取，请稍候（下载视频 + 离线语音转写，大约 1–3 分钟）…',
      empty: '请先粘贴一条抖音链接。',
      done: '已导入：',
      incomplete: '已在新会话草稿里填入抓取请求，请按回车开始。',
      missingCommand: '没有找到 /douyin 命令，请重启 DeepSeek Harness 后再试。',
      notesTitle: '注意事项',
      note1: '首次使用需扫码登录一次抖音：会弹出浏览器窗口，用手机抖音扫码确认即可，之后再使用无需重复登录。',
      note2: '受限于本地语音模型，转写结果会偶有错字，导入完成后需人工校对修正。',
      note3: '使用前需准备前置软件：Node.js、Git、Python，建议在安装本插件之前先自行安装好。',
    };

    const en = {
      title: 'Douyin to Obsidian (for beginners)',
      panel: 'Douyin to OB',
      placeholder: 'Paste a Douyin share link or share text, e.g. https://v.douyin.com/xxxxxx/',
      start: 'Start importing',
      starting: 'Importing…',
      running: 'Importing now. Downloading and transcribing offline takes about 1–3 minutes…',
      empty: 'Paste a Douyin link first.',
      done: 'Imported: ',
      incomplete: 'The request was placed in a new session draft. Press Enter to start.',
      missingCommand: 'The /douyin command is missing. Restart DeepSeek Harness and try again.',
      notesTitle: 'Before you start',
      note1: 'The first run needs a Douyin QR sign-in: a browser window opens, scan it with the Douyin app once, and later runs reuse that session.',
      note2: 'The local speech model is not perfect, so the transcript may contain typos that need a manual review after importing.',
      note3: 'Prerequisites are Node.js, Git and Python. Install them before installing this plugin.',
    };

    const colors = {
      text: 'var(--dsw-alias-label-primary)',
      muted: 'var(--dsw-alias-label-secondary)',
      faint: 'var(--dsw-alias-label-tertiary)',
      border: 'var(--dsw-alias-border-l2)',
      error: 'var(--dsw-alias-state-error-primary)',
      ok: 'var(--dsw-alias-state-business-primary)',
      warn: 'var(--dsw-alias-state-warn-label)',
    };

    function DouyinIcon(props) {
      const size = props && typeof props.size === 'number' ? props.size : 18;
      const active = Boolean(props && props.active);
      return h('svg', {
        viewBox: '0 0 24 24',
        width: size,
        height: size,
        'aria-hidden': true,
        style: { display: 'block', color: active ? colors.text : colors.faint },
      },
        h('path', {
          d: 'M13.5 3v9.2a3.2 3.2 0 1 1-2.6-3.14V6.6a5.6 5.6 0 1 0 5.2 5.58V8.9c1.05.62 2.2.98 3.4.99V7.3a3.9 3.9 0 0 1-3.6-2.2l-.3-.6z',
          fill: 'currentColor',
        }),
      );
    }

    function DouyinPanel(props) {
      const t = typeof props.t === 'function' ? props.t : (key) => key;
      const [value, setValue] = React.useState('');
      const [status, setStatus] = React.useState(null);
      const busy = status !== null && status.kind === 'busy';

      const submit = async () => {
        if (busy) return;
        const raw = value.trim();
        if (raw.length === 0) {
          setStatus({ kind: 'error', text: t('empty') });
          return;
        }
        setStatus({ kind: 'busy', text: t('running') });
        try {
          const outcome = await props.run(raw);
          setStatus({ kind: outcome.ok ? 'ok' : 'error', text: outcome.text });
        } catch (error) {
          setStatus({ kind: 'error', text: String((error && error.message) || error) });
        }
      };

      const statusColor = status === null ? colors.muted : status.kind === 'error' ? colors.error : status.kind === 'ok' ? colors.ok : colors.muted;

      return h('div', { style: { maxWidth: 720, padding: '28px 32px', color: colors.text, fontSize: 14, lineHeight: 1.6 } },
        h('h1', { style: { margin: '0 0 6px', fontSize: 20, fontWeight: 600 } }, t('title')),
        h('p', { style: { margin: '0 0 20px', color: colors.muted, fontSize: 13 } }, t('placeholder')),
        h('textarea', {
          value: value,
          onChange: (event) => setValue(event.target.value),
          rows: 3,
          spellCheck: false,
          placeholder: 'https://v.douyin.com/…',
          style: {
            width: '100%',
            boxSizing: 'border-box',
            padding: '10px 12px',
            fontSize: 14,
            lineHeight: 1.5,
            color: colors.text,
            background: 'var(--dsw-alias-bg-layer-1)',
            border: '1px solid ' + colors.border,
            borderRadius: 8,
            resize: 'vertical',
            outline: 'none',
            fontFamily: 'inherit',
          },
        }),
        h('div', { style: { margin: '14px 0 0' } },
          h('button', {
            type: 'button',
            onClick: submit,
            disabled: busy,
            style: {
              padding: '8px 18px',
              fontSize: 14,
              fontWeight: 500,
              borderRadius: 8,
              border: '1px solid ' + (busy ? colors.border : 'transparent'),
              background: busy ? 'var(--dsw-alias-interactive-bg-hover)' : 'var(--dsw-alias-label-primary)',
              color: busy ? colors.muted : 'var(--dsw-alias-label-primary-foreground)',
              cursor: busy ? 'progress' : 'pointer',
            },
          }, busy ? t('starting') : t('start')),
        ),
        status === null ? null : h('div', { style: { margin: '12px 0 0', color: statusColor, fontSize: 13, whiteSpace: 'pre-wrap' } }, status.text),
        h('div', {
          style: {
            margin: '26px 0 0',
            padding: '14px 16px',
            borderRadius: 8,
            background: 'var(--dsw-alias-bg-layer-1)',
            border: '1px solid ' + colors.border,
          },
        },
          h('div', { style: { margin: '0 0 8px', fontWeight: 600, fontSize: 13, color: colors.warn } }, t('notesTitle')),
          h('p', { style: { margin: '0 0 6px', fontSize: 13, color: colors.muted } }, '1. ' + t('note1')),
          h('p', { style: { margin: '0 0 6px', fontSize: 13, color: colors.muted } }, '2. ' + t('note2')),
          h('p', { style: { margin: 0, fontSize: 13, color: colors.muted } }, '3. ' + t('note3')),
        ),
      );
    }

    function service(ctx, name) {
      try {
        const value = ctx[name];
        if (value !== undefined) return value;
      } catch {
        // 未声明的服务会抛 "cannot get property ... without inject"，改用 ctx.get 兜底
      }
      try {
        return typeof ctx.get === 'function' ? ctx.get(name) : undefined;
      } catch {
        return undefined;
      }
    }

    function latestSessionId(ctx) {
      try {
        const sessions = service(ctx, 'sessions');
        const snapshot = sessions && sessions.list && typeof sessions.list.getSnapshot === 'function'
          ? sessions.list.getSnapshot()
          : undefined;
        if (snapshot === undefined || snapshot === null) return undefined;
        for (const key of ['activeId', 'currentId', 'selectedId', 'current', 'active', 'selected', 'lastSessionId']) {
          if (typeof snapshot[key] === 'string' && snapshot[key].length > 0) return snapshot[key];
        }
        if (Array.isArray(snapshot.order) && snapshot.order.length > 0) {
          for (let index = snapshot.order.length - 1; index >= 0; index -= 1) {
            const id = snapshot.order[index];
            if (typeof id === 'string' && id.length > 0) return id;
          }
        }
        const ids = Object.keys(snapshot.byId || {});
        return ids.length > 0 ? ids[ids.length - 1] : undefined;
      } catch {
        return undefined;
      }
    }

    // remote.commands.execute 的真实返回（见内置 dsh-client-ui-commands）：
    // { ok, value: { commandId, result: { kind, text, ... } } }
    // 命令未注册时 value===undefined；refused 时 ok===false 并带 error。
    function unwrap(response) {
      if (!response || response.ok !== true || response.value == null) return null;
      const value = response.value;
      return value.result != null ? value.result : value;
    }

    function describe(response, t) {
      const outcome = unwrap(response);
      if (outcome === null) {
        const error = response && response.error;
        return error ? error.code + ': ' + error.message : t('missingCommand');
      }
      const text = typeof outcome.text === 'string' ? outcome.text.trim() : '';
      return text || (outcome.kind === 'success' ? t('done') : t('missingCommand'));
    }

    return {
      // 与内置 schedule 面板同样使用数组式注入（这些名字都是宿主真实服务）。
      // 面板需要 remote.commands 执行 /douyin，uiWorkspace/sessions 用于定位当前会话。
      inject: ['slots', 'locale', 'remote', 'remote.commands', 'sessions', 'uiWorkspace'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'douyin-kb: dictionaries');
        const t = ctx.locale.bind(NS);

        const run = async (url) => {
          const sessionId = latestSessionId(ctx);
          let commands;
          try {
            commands = ctx.remote && ctx.remote.commands ? ctx.remote.commands : undefined;
          } catch {
            commands = undefined;
          }
          let failure;
          if (sessionId !== undefined && commands !== undefined && typeof commands.execute === 'function') {
            try {
              const response = await commands.execute(sessionId, '/douyin ' + url, []);
              const outcome = unwrap(response);
              if (outcome !== null) return { ok: outcome.kind === 'success', text: describe(response, t) };
              failure = describe(response, t);
            } catch (error) {
              failure = error && error.message ? String(error.message) : t('missingCommand');
            }
          }
          const workspace = service(ctx, 'uiWorkspace');
          if (workspace !== undefined && typeof workspace.startSession === 'function') {
            workspace.startSession(undefined, {
              prompt: '请用 douyin_kb 工具（action=ingest）把这条抖音视频导入我的 Obsidian 知识库：\n' + url,
              whenDraftExists: 'append',
            });
            return { ok: true, text: t('incomplete') + (failure ? '（' + failure + '）' : '') };
          }
          return { ok: false, text: failure || t('missingCommand') };
        };

        ctx.slots.inject('main', () => ctx.slots.register({
          name: 'main',
          key: PANEL_ID,
          locale: NS,
          inject: () => ({ t, run }),
        }, DouyinPanel));

        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
          name: 'sidebar.panellist',
          id: PANEL_ID,
          order: 30,
          locale: NS,
          label: () => t('panel'),
        }, DouyinIcon));
      },
    };
  },
});
