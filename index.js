import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(here, "assets", "douyin_kb.py");
const DEFAULT_KB_HOME = path.join(homedir(), ".dsh", "douyin-kb");
const CONFIG_FILE = path.join(DEFAULT_KB_HOME, "config.json");
const DEFAULT_VAULT = path.join(homedir(), "Documents", "Obsidian Vault");
const OBSIDIAN_CONFIG =
	process.platform === "win32"
		? path.join(process.env.APPDATA || path.join(homedir(), "AppData", "Roaming"), "obsidian", "obsidian.json")
		: process.platform === "darwin"
			? path.join(homedir(), "Library", "Application Support", "obsidian", "obsidian.json")
			: path.join(homedir(), ".config", "obsidian", "obsidian.json");

/** Local machine settings live outside the repo, in ~/.dsh/douyin-kb/config.json. */
function readLocalConfig() {
	try {
		const value = JSON.parse(readFileSync(CONFIG_FILE, "utf8"));
		return typeof value === "object" && value !== null ? value : {};
	} catch {
		return {};
	}
}

/** Ask Obsidian itself which vault is open, so no path has to be stored anywhere. */
function detectObsidianVault() {
	try {
		const config = JSON.parse(readFileSync(OBSIDIAN_CONFIG, "utf8"));
		const vaults = Object.values(config?.vaults ?? {}).filter(
			(vault) => vault !== null && typeof vault === "object" && typeof vault.path === "string" && vault.path.length > 0,
		);
		if (vaults.length === 0) return undefined;
		const opened = vaults.find((vault) => vault.open === true);
		if (opened !== undefined) return opened.path;
		vaults.sort((left, right) => Number(right.ts ?? 0) - Number(left.ts ?? 0));
		return vaults[0].path;
	} catch {
		return undefined;
	}
}

function resolveVault(configured) {
	return (
		configured ||
		process.env.OBSIDIAN_VAULT ||
		readLocalConfig().vault ||
		detectObsidianVault() ||
		DEFAULT_VAULT
	);
}

const PARAMETERS = {
	type: "object",
	additionalProperties: false,
	properties: {
		action: {
			type: "string",
			enum: ["ingest", "batch", "probe", "transcribe", "login"],
			description: "Operation to run.",
		},
		target: {
			type: "string",
			description: "Share link or share text for ingest/probe, creator homepage for batch, local file path for transcribe. Omit for login.",
		},
		limit: {
			type: "integer",
			description: "How many videos to import in batch mode. Defaults to 10.",
		},
		transcribe: {
			type: "boolean",
			description: "Set false to skip speech transcription and only capture metadata. Defaults to true.",
		},
		force: {
			type: "boolean",
			description: "Overwrite an existing note for the same video. Defaults to false.",
		},
	},
	required: ["action"],
};

const OUTPUT_SCHEMA = {
	type: "object",
	additionalProperties: false,
	properties: {
		ok: { type: "boolean" },
		action: { type: "string" },
		result: { type: "object", additionalProperties: true },
		log: { type: "string" },
	},
	required: ["ok", "action", "result", "log"],
};

function findPython(configured) {
	const candidates = [
		configured,
		process.env.DOUYIN_KB_PYTHON,
		path.join(DEFAULT_KB_HOME, "..", "dsh-runtimes", "dsh-primary-runtime", "dependencies", "python", "python.exe"),
		"python",
	].filter((item) => typeof item === "string" && item.length > 0);
	for (const candidate of candidates) {
		if (candidate === "python" || existsSync(candidate)) return candidate;
	}
	return "python";
}

function buildArgs(settings, args) {
	const argv = ["-u", SCRIPT, args.action];
	if (args.action !== "login") argv.push(String(args.target ?? ""));
	if (args.action === "batch") argv.push("--limit", String(args.limit ?? 10));
	if (args.action === "ingest" || args.action === "batch") argv.push("--vault", settings.vault);
	if (args.force === true) argv.push("--force");
	if (args.transcribe === false) argv.push("--no-transcribe");
	return argv;
}

function parseResult(stdout) {
	const line = stdout.split(/\r?\n/).reverse().find((item) => item.startsWith("RESULT "));
	if (line === undefined) return {};
	try {
		const value = JSON.parse(line.slice("RESULT ".length));
		return typeof value === "object" && value !== null ? value : { value };
	} catch {
		return {};
	}
}

/** Run the Python engine once and collect its stdout, stderr and RESULT payload. */
async function runScript(settings, args, signal) {
	const argv = buildArgs(settings, args);
	const env = {
		...process.env,
		DOUYIN_KB_HOME: settings.kbHome,
		OBSIDIAN_VAULT: settings.vault,
		PYTHONIOENCODING: "utf-8",
		PYTHONUTF8: "1",
	};
	const child = spawn(settings.python, argv, { env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
	let stdout = "";
	let stderr = "";
	child.stdout.setEncoding("utf8");
	child.stderr.setEncoding("utf8");
	child.stdout.on("data", (chunk) => { stdout += chunk; });
	child.stderr.on("data", (chunk) => { stderr += chunk; });
	const onAbort = () => { child.kill(); };
	signal.addEventListener("abort", onAbort, { once: true });
	let code;
	try {
		code = await new Promise((resolve, reject) => {
			child.on("error", reject);
			child.on("close", resolve);
		});
	} finally {
		signal.removeEventListener("abort", onAbort);
	}
	const log = [stdout.trim(), stderr.trim()].filter((item) => item.length > 0).join("\n");
	return {
		ok: code === 0,
		action: args.action,
		result: parseResult(stdout),
		log: log.length > 0 ? log : `[douyin_kb] exited with code ${String(code)}`,
	};
}

/** One human-readable line describing a finished ingest. */
function describeIngest(outcome) {
	const result = outcome.result ?? {};
	if (outcome.ok !== true) {
		const tail = String(outcome.log ?? "").split(/\r?\n/).filter((line) => line.trim().length > 0).slice(-4).join("\n");
		return tail.length > 0 ? `抓取失败：\n${tail}` : "抓取失败，请查看日志。";
	}
	const title = String(result.title ?? "").trim();
	const author = String(result.author ?? "").trim();
	const note = String(result.note ?? "").trim();
	const parts = [];
	if (title.length > 0) parts.push(`《${title}》`);
	if (author.length > 0) parts.push(`作者：${author}`);
	if (result.duration !== undefined) parts.push(`时长：${String(result.duration)} 秒`);
	if (result.segments !== undefined) parts.push(`转写 ${String(result.segments)} 段`);
	const head = parts.length > 0 ? `已导入${parts.join("，")}。` : "已导入。";
	return note.length > 0 ? `${head}\n笔记：${note}` : head;
}

function apply(ctx, config) {
	const settings = {
		vault: resolveVault(config && config.vault),
		kbHome: (config && config.kbHome) || DEFAULT_KB_HOME,
		python: findPython(config && config.python),
		timeoutSeconds: (config && Number(config.timeoutSeconds)) || 900,
	};

	ctx.tools.register({
		name: "douyin_kb",
		description: [
			"Import Douyin (抖音) videos into the user's local Obsidian knowledge base: downloads the video with a dedicated Edge profile, transcribes the speech offline in Chinese with timestamps, and writes a Markdown note into the vault's 抖音收藏 folder.",
			"Use action=ingest with a v.douyin.com share link or share text; action=batch with a creator homepage (https://www.douyin.com/user/MS4wLjABAAAA...) to import several videos; action=probe to preview metadata only; action=transcribe for a local audio/video file; action=login when Douyin rejects the session (opens a browser window for QR sign-in).",
			"Notes are indexed in 抖音收藏/.index.json and repeated videos are skipped unless force is true.",
		].join(" "),
		parameters: PARAMETERS,
		output: {
			schema: OUTPUT_SCHEMA,
			render: (_args, value) => [{ type: "text", text: String(value.log ?? "").trim() || "[douyin_kb] done" }],
		},
		timeoutMs: Math.max(30, settings.timeoutSeconds) * 1000,
		isConcurrencySafe: () => false,
		async execute(args, exec) {
			const action = String(args.action);
			if (action === "ingest" || action === "batch" || action === "probe" || action === "transcribe") {
				if (String(args.target ?? "").trim().length === 0) {
					throw new Error(`douyin_kb action=${action} requires a non-empty target`);
				}
			}
			const outcome = await runScript(settings, args, exec.signal);
			if (exec.signal.aborted) throw new Error("douyin_kb aborted");
			return outcome;
		},
	});

	ctx.effect(() => ctx.commands.register({
		name: "douyin",
		description: "把一条抖音视频下载、离线转写并写入本机 Obsidian 知识库",
		input: { hint: "<抖音分享链接或整段分享文案>" },
		handler: async ({ rawInput }) => {
			const target = String(rawInput ?? "").trim();
			if (target.length === 0) {
				return { kind: "error", text: "请在 /douyin 后面粘贴一条抖音分享链接。" };
			}
			const controller = new AbortController();
			const timer = setTimeout(() => controller.abort(), Math.max(30, settings.timeoutSeconds) * 1000);
			try {
				const outcome = await runScript(settings, { action: "ingest", target, force: true }, controller.signal);
				return { kind: outcome.ok ? "success" : "error", text: describeIngest(outcome) };
			} catch (error) {
				return { kind: "error", text: `抓取失败：${String((error && error.message) || error)}` };
			} finally {
				clearTimeout(timer);
			}
		},
	}), "douyin-kb /douyin command");
}

const inject = ["tools", "commands"];

export { apply, inject };
