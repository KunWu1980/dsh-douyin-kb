#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音视频 -> Obsidian 知识库（本机离线全链路）。

原理：用一个专用的 Edge 浏览器配置（首次会弹窗，可扫码登录，之后一直复用），
打开抖音页面时截获它自己发出的 /aweme/v1/web/aweme/detail/ 接口数据，
拿到文案/作者/时长/无水印播放地址；再下载视频、PyAV 解码音轨、
sherpa-onnx SenseVoice 离线转写成中文，最后写成 Obsidian 的 Markdown 笔记。

子命令:
  ingest      单条视频入库
  probe       只解析元数据，不下载不写库
  batch       博主主页批量入库
  transcribe  转写本地音视频文件
  login       打开浏览器窗口（扫码登录 / 刷新 cookies）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("DOUYIN_KB_HOME") or Path(__file__).resolve().parent.parent)
MODELS = ROOT / "models"
WORK = ROOT / "work"
PROFILE = ROOT / "browser-profile"
CONFIG_FILE = ROOT / "config.json"


def _config_value(name: str) -> str | None:
    """读取 ~/.dsh/douyin-kb/config.json 里的本机设置（不进代码仓库）。"""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get(name) if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


DEFAULT_VAULT = Path(
    os.environ.get("OBSIDIAN_VAULT")
    or _config_value("vault")
    or str(Path.home() / "Documents" / "Obsidian Vault")
)
NOTE_SUBDIR = "抖音收藏"
ATTACH_SUBDIR = "抖音收藏/_附件"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)

URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff\"'<>）)】]+", re.I)
VIDEO_ID_RE = re.compile(r"(?:/video/|/note/|/share/video/)(\d{6,})")
HEADLESS = os.environ.get("DOUYIN_HEADLESS", "0") == "1"


# ---------------------------------------------------------------- utilities
def log(msg: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(msg, flush=True)


def sanitize(name: str, limit: int = 80) -> str:
    name = unicodedata.normalize("NFC", name or "")
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:limit].strip() or "untitled"


def pick_url(text: str) -> str:
    text = (text or "").strip()
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip("，。,.；;）)")
    m = re.search(r"(v\.douyin\.com/[A-Za-z0-9_-]+)", text)
    if m:
        return "https://" + m.group(1)
    if re.fullmatch(r"https?://\S+", text):
        return text
    raise SystemExit("没有在输入里找到抖音链接。请粘贴完整分享文案或 https://v.douyin.com/xxx 短链。")


def resolve_short(url: str) -> tuple[str, str]:
    """跟随短链跳转，返回 (最终URL, 视频ID)。"""
    import urllib.request

    final = url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA_MOBILE})
        with urllib.request.urlopen(req, timeout=30) as resp:
            final = resp.geturl()
            html = resp.read(200_000).decode("utf-8", "ignore")
    except Exception as exc:
        log(f"  ! 短链解析失败：{type(exc).__name__}: {exc}")
        html = ""
    m = VIDEO_ID_RE.search(final) or VIDEO_ID_RE.search(url)
    vid = m.group(1) if m else ""
    if not vid and html:
        m2 = re.search(r'"aweme_id":"(\d+)"', html) or re.search(r"itemId[\"\s:]+[\"']?(\d{10,})", html)
        if m2:
            vid = m2.group(1)
    return final, vid


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ------------------------------------------------------------------ browser
class Browser:
    """复用同一个 Edge 用户配置，截获抖音前端自己请求的接口数据。"""

    def __init__(self) -> None:
        self._pw = None
        self.ctx = None
        self.page = None

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright

        PROFILE.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            str(PROFILE),
            channel="msedge",
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--mute-audio",
                "--autoplay-policy=no-user-gesture-required",
            ],
            user_agent=UA,
            locale="zh-CN",
            viewport={"width": 1280, "height": 860},
        )
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def cookie_header(self) -> str:
        try:
            return "; ".join(f"{c['name']}={c['value']}" for c in self.ctx.cookies())
        except Exception:
            return ""

    def _capture(self, url: str, needle: str, wait_s: float = 20.0, key=None) -> dict | None:
        """打开页面，等待包含 needle 的接口响应并解析 JSON。"""
        hits: list[str] = []

        def on_resp(resp):
            try:
                if needle in resp.url:
                    hits.append(resp.text())
            except Exception:
                pass

        self.page.on("response", on_resp)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + wait_s
            while time.time() < deadline:
                for raw in hits:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if key is None or key(data):
                        return data
                self.page.wait_for_timeout(800)
            return None
        finally:
            self.page.remove_listener("response", on_resp)

    def video_detail(self, vid: str) -> dict | None:
        data = self._capture(
            f"https://www.douyin.com/video/{vid}",
            "/aweme/v1/web/aweme/detail/",
            wait_s=25,
            key=lambda d: bool(d.get("aweme_detail")),
        )
        if data:
            return data["aweme_detail"]
        # 兜底：页面上的 <video> 元素
        for _ in range(8):
            src = self.page.evaluate(
                "() => { const v=document.querySelector('video'); return v? (v.currentSrc||v.src||'') : '' }"
            )
            if src and src.startswith("http") and "uuu_" not in src:
                return {"_fallback_src": src, "desc": self.page.title().split(" - 抖音")[0]}
            self.page.wait_for_timeout(1200)
        return None

    def user_posts(self, sec_uid: str, limit: int = 20) -> list[dict]:
        url = f"https://www.douyin.com/user/{sec_uid}"
        found: list[dict] = []

        def on_resp(resp):
            if "/aweme/v1/web/aweme/post/" in resp.url:
                try:
                    data = resp.json()
                except Exception:
                    return
                for item in (data.get("aweme_list") or []):
                    if item.get("aweme_id"):
                        found.append(item)
                self._no_more = bool(data.get("has_more") is False)

        self.page.on("response", on_resp)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            last = -1
            stale = 0
            while len(found) < limit and stale < 6:
                self.page.wait_for_timeout(2000)
                self.page.mouse.wheel(0, 2400)
                if len(found) == last:
                    stale += 1
                else:
                    stale = 0
                last = len(found)
            # 去重保序
            uniq, seen = [], set()
            for it in found:
                if it["aweme_id"] not in seen:
                    seen.add(it["aweme_id"])
                    uniq.append(it)
            return uniq[:limit]
        finally:
            self.page.remove_listener("response", on_resp)


# ------------------------------------------------------------ meta helpers
def best_play_url(detail: dict) -> str:
    video = detail.get("video") or {}
    rates = video.get("bit_rate") or []
    if isinstance(rates, list) and rates:
        rates = sorted(
            [r for r in rates if (r.get("play_addr") or {}).get("url_list")],
            key=lambda r: r.get("bit_rate") or 0,
            reverse=True,
        )
        if rates:
            return rates[0]["play_addr"]["url_list"][0]
    for key in ("play_addr", "play_addr_h264", "download_addr"):
        urls = ((video.get(key) or {}).get("url_list") or [])
        if urls:
            return urls[0]
    return detail.get("_fallback_src") or ""


def collect_meta(detail: dict, vid: str) -> dict:
    author = detail.get("author") or {}
    stats = detail.get("statistics") or {}
    video = detail.get("video") or {}
    desc = (detail.get("desc") or "").strip()
    title = re.split(r"[#＃]", desc)[0].strip() or desc or "抖音视频"
    ts = detail.get("create_time") or 0
    published = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
    dur_ms = video.get("duration") or detail.get("duration") or 0
    cover = ((video.get("origin_cover") or video.get("cover") or {}).get("url_list") or [""])[0]
    tags = re.findall(r"[#＃]([^\s#＃]{1,20})", desc)
    return {
        "id": vid,
        "title": title,
        "description": desc,
        "uploader": author.get("nickname") or "",
        "webpage_url": f"https://www.douyin.com/video/{vid}",
        "duration": int(dur_ms // 1000) if dur_ms else 0,
        "thumbnail": cover,
        "published": published,
        "like_count": stats.get("digg_count") or 0,
        "comment_count": stats.get("comment_count") or 0,
        "share_count": stats.get("share_count") or 0,
        "collect_count": stats.get("collect_count") or 0,
        "tags": tags[:12],
    }


def download_media(url: str, dest: Path, cookie: str = "") -> Path:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and got % (10 << 20) < (1 << 20):
                log(f"  下载 {got / 1048576:.1f}/{total / 1048576:.1f} MiB")
    tmp.replace(dest)
    return dest


# ------------------------------------------------------------------- audio
def decode_audio(path: Path, sample_rate: int = 16000):
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise SystemExit("这个文件里没有音轨（可能是纯图文作品）。")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        chunks = []
        for frame in container.decode(stream):
            frame.pts = None
            for out in resampler.resample(frame):
                chunks.append(np.asarray(out.to_ndarray()).reshape(-1))
        for out in resampler.resample(None):
            chunks.append(np.asarray(out.to_ndarray()).reshape(-1))
    if not chunks:
        raise SystemExit("音轨解码为空。")
    import numpy as np

    return np.concatenate(chunks).astype(np.float32) / 32768.0


def _vad_config():
    import sherpa_onnx

    silero = MODELS / "silero_vad.onnx"
    if not silero.exists():
        return None
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = str(silero)
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.4
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = 20.0
    cfg.sample_rate = 16000
    cfg.num_threads = 1
    return cfg


def transcribe(audio, enable_vad: bool = True) -> list[dict]:
    import numpy as np
    import sherpa_onnx

    model = MODELS / "model.int8.onnx"
    tokens = MODELS / "tokens.txt"
    if not model.exists() or not tokens.exists():
        raise SystemExit(
            f"缺少语音模型。请把 model.int8.onnx 与 tokens.txt 放到 {MODELS}。\n"
            "下载：https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
        )
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model), tokens=str(tokens), num_threads=os.cpu_count() or 4,
        use_itn=True, language="zh", debug=False,
    )

    cfg = _vad_config() if enable_vad else None
    if cfg is not None:
        vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=180)
        window = 1600
        speech: list[tuple[float, "np.ndarray"]] = []
        for i in range(0, max(0, len(audio) - window), window):
            vad.accept_waveform(audio[i : i + window])
            while not vad.empty():
                seg = vad.front
                speech.append((seg.start / 16000, np.asarray(seg.samples, dtype=np.float32)))
                vad.pop()
        vad.flush()
        while not vad.empty():
            seg = vad.front
            speech.append((seg.start / 16000, np.asarray(seg.samples, dtype=np.float32)))
            vad.pop()
        if not speech:
            speech = [(0.0, audio)]
    else:
        speech = [(i / 16000.0, audio[i : i + 16000 * 25]) for i in range(0, len(audio), 16000 * 25)]

    segments: list[dict] = []
    for idx, (start, samples) in enumerate(speech, 1):
        st = rec.create_stream()
        st.accept_waveform(16000, samples)
        rec.decode_stream(st)
        text = (st.result.text or "").strip()
        if text:
            segments.append({"start": round(start, 2), "text": text})
        if idx % 10 == 0:
            log(f"  转写 {idx}/{len(speech)} 段")
    return segments


# -------------------------------------------------------------------- note
def write_note(meta: dict, transcript: list[dict], vault: Path, cover_path: Path | None,
               force: bool = False) -> Path:
    note_dir = vault / NOTE_SUBDIR
    attach_dir = vault / ATTACH_SUBDIR
    note_dir.mkdir(parents=True, exist_ok=True)

    index_path = note_dir / ".index.json"
    index = {}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text("utf-8"))
        except Exception:
            index = {}
    if meta["id"] in index and Path(index[meta["id"]]).exists() and not force:
        log(f"  已存在笔记，跳过：{index[meta['id']]}")
        return Path(index[meta["id"]])

    stem = sanitize(f"{meta['title'][:50]} {meta['id']}".strip(), 90)
    note_path = note_dir / f"{stem}.md"

    cover_link = ""
    if cover_path and cover_path.exists():
        attach_dir.mkdir(parents=True, exist_ok=True)
        target = attach_dir / f"douyin-{meta['id']}{cover_path.suffix or '.jpg'}"
        shutil.copy2(cover_path, target)
        cover_link = f"![[{target.relative_to(vault).as_posix()}]]"

    safe_title = meta["title"].replace('"', "'")
    lines = [
        "---",
        f'title: "{safe_title}"',
        "platform: 抖音",
        f'author: "{meta["uploader"]}"',
        f"source: {meta['webpage_url']}",
        f'video_id: "{meta["id"]}"',
    ]
    if meta["published"]:
        lines.append(f"published: {meta['published']}")
    lines += [
        f"duration: {meta['duration']}",
        f"likes: {meta['like_count']}",
        f"comments: {meta['comment_count']}",
        f"captured: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "tags:",
        "  - 抖音",
        "  - 视频笔记",
    ]
    for t in meta["tags"][:8]:
        lines.append(f"  - {sanitize(t, 20).replace(' ', '-')}")
    lines += ["---", "", f"# {meta['title']}", ""]
    lines.append(
        f"> 作者：@{meta['uploader']}　·　时长 {fmt_ts(meta['duration'])}　·　[原视频]({meta['webpage_url']})"
    )
    lines.append("")
    if cover_link:
        lines += [cover_link, ""]
    if meta["description"] and meta["description"] != meta["title"]:
        lines += ["## 视频文案", "", meta["description"], ""]
    lines += ["## 语音转写", ""]
    if transcript:
        for seg in transcript:
            lines.append(f"- `{fmt_ts(seg['start'])}` {seg['text']}")
    else:
        lines.append("_（该视频没有可转写的人声，或转写失败）_")
    lines += ["", "## 要点整理", "", "- [ ] 待整理", ""]
    note_path.write_text("\n".join(lines), "utf-8")

    index[meta["id"]] = str(note_path)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), "utf-8")
    return note_path


# -------------------------------------------------------------------- flow
def fetch_detail(browser: Browser, vid: str) -> dict:
    detail = browser.video_detail(vid)
    if not detail:
        raise SystemExit(
            "抓不到视频数据。可能是：视频已删除/仅App可见，或需要重新登录。\n"
            "试试先运行：python douyin_kb.py login"
        )
    return detail


def save_cover(browser: Browser, meta: dict) -> Path | None:
    if not meta["thumbnail"]:
        return None
    import urllib.request

    try:
        req = urllib.request.Request(
            meta["thumbnail"],
            headers={
                "User-Agent": UA,
                "Referer": "https://www.douyin.com/",
                "Cookie": browser.cookie_header(),
            },
        )
        data = urllib.request.urlopen(req, timeout=60).read()
        path = WORK / f"cover-{meta['id']}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path
    except Exception as exc:
        log(f"  ! 封面下载失败：{type(exc).__name__}: {exc}")
        return None


def do_ingest(target: str, vault: Path, force: bool, no_transcribe: bool) -> None:
    url = pick_url(target)
    log(f"→ 解析链接：{url}")
    _, vid = resolve_short(url)
    if not vid:
        raise SystemExit("没能从链接里解析出视频 ID。请确认是单条视频的分享链接。")
    log(f"  视频 ID：{vid}")

    with Browser() as browser:
        log("→ 打开页面并截获接口数据")
        detail = fetch_detail(browser, vid)
        if detail.get("desc") is None and detail.get("_fallback_src"):
            meta = {
                "id": vid, "title": "抖音视频", "description": "", "uploader": "",
                "webpage_url": f"https://www.douyin.com/video/{vid}", "duration": 0,
                "thumbnail": "", "published": "", "like_count": 0, "comment_count": 0,
                "share_count": 0, "collect_count": 0, "tags": [],
            }
        else:
            meta = collect_meta(detail, vid)
        log(f"  标题：{meta['title']}")
        log(f"  作者：@{meta['uploader']}　时长 {fmt_ts(meta['duration'])}　点赞 {meta['like_count']}")

        cover = save_cover(browser, meta)
        play = best_play_url(detail) if not detail.get("_fallback_src") else detail["_fallback_src"]
        cookie = browser.cookie_header()

    media = None
    if play:
        try:
            log("→ 下载视频")
            media = download_media(play, WORK / vid / f"{vid}.mp4", cookie)
            log(f"  落盘：{media} ({media.stat().st_size / 1048576:.1f} MiB)")
        except Exception as exc:
            log(f"  ! 下载失败：{type(exc).__name__}: {exc}")
    else:
        log("  ! 没有拿到播放地址")

    transcript: list[dict] = []
    if media and not no_transcribe:
        log("→ 解码音轨")
        audio = decode_audio(media)
        log(f"  音频 {len(audio) / 16000:.1f}s，开始离线转写（SenseVoice）")
        t0 = time.time()
        transcript = transcribe(audio)
        log(f"  转写完成：{len(transcript)} 段，用时 {time.time() - t0:.1f}s")

    note = write_note(meta, transcript, vault, cover, force)
    log(f"✔ 已写入笔记：{note}")
    result = {
        "note": str(note),
        "video_id": vid,
        "title": meta["title"],
        "author": meta["uploader"],
        "duration": meta["duration"],
        "segments": len(transcript),
        "transcript_chars": sum(len(s["text"]) for s in transcript),
        "media_size": media.stat().st_size if media else 0,
    }
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def do_batch(home: str, vault: Path, limit: int, force: bool, no_transcribe: bool) -> None:
    url = pick_url(home)
    m = re.search(r"/user/([A-Za-z0-9_\-]+)", url)
    if not m:
        raise SystemExit("批量模式需要博主主页链接，形如 https://www.douyin.com/user/MS4wLjABAAAA...")
    sec_uid = m.group(1)

    with Browser() as browser:
        log(f"→ 打开主页并滚动加载（最多 {limit} 条）")
        posts = browser.user_posts(sec_uid, limit)
        ids = [p["aweme_id"] for p in posts]
    log(f"  找到 {len(ids)} 条视频")
    done: list[dict] = []
    failed: list[str] = []
    for i, vid in enumerate(ids, 1):
        log(f"[{i}/{len(ids)}] {vid}")
        try:
            done.append(do_ingest(f"https://www.douyin.com/video/{vid}", vault, force, no_transcribe))
        except SystemExit as exc:
            failed.append(vid)
            log(f"  ! 跳过：{exc}")
        except Exception as exc:
            failed.append(vid)
            log(f"  ! 失败：{type(exc).__name__}: {exc}")
    log(f"完成：成功 {len(done)}/{len(ids)}")
    result = {
        "sec_uid": sec_uid,
        "found": len(ids),
        "succeeded": len(done),
        "failed": failed,
        "notes": [d.get("note") for d in done],
    }
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)


def do_login(timeout: int = 240) -> None:
    """打开抖音首页，等用户扫码登录；检测到登录 cookie 后自动关闭。"""
    log("→ 打开抖音首页，请在窗口里扫码登录（登录态会保存到本机浏览器配置）")
    with Browser() as browser:
        browser.page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + timeout
        logged = False
        while time.time() < deadline:
            names = {c["name"] for c in browser.ctx.cookies()}
            if names & {"sessionid", "sessionid_ss", "sid_tt"}:
                logged = True
                break
            browser.page.wait_for_timeout(2000)
        if logged:
            log("  已检测到登录状态")
        else:
            log(f"  ! {timeout}s 内未检测到登录，当前 cookies 仍会保存，可稍后重试")
    log("✔ 已保存浏览器配置")
    print("RESULT " + json.dumps({"logged_in": logged}, ensure_ascii=False), flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="抖音视频 → Obsidian 知识库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("ingest", "probe"):
        p = sub.add_parser(name)
        p.add_argument("target", help="分享文案或链接")
        p.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", str(DEFAULT_VAULT)))
        p.add_argument("--force", action="store_true", help="已存在时覆盖")
        p.add_argument("--no-transcribe", action="store_true", help="只抓文案不转写")

    b = sub.add_parser("batch")
    b.add_argument("home", help="博主主页链接")
    b.add_argument("--limit", type=int, default=20)
    b.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", str(DEFAULT_VAULT)))
    b.add_argument("--force", action="store_true")
    b.add_argument("--no-transcribe", action="store_true")

    t = sub.add_parser("transcribe")
    t.add_argument("file")

    sub.add_parser("login")

    args = ap.parse_args()

    if args.cmd == "login":
        do_login()
        return

    if args.cmd == "probe":
        url = pick_url(args.target)
        _, vid = resolve_short(url)
        with Browser() as browser:
            detail = fetch_detail(browser, vid)
            meta = collect_meta(detail, vid) if detail.get("desc") is not None else {"id": vid}
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print("RESULT " + json.dumps(meta, ensure_ascii=False), flush=True)
        return

    if args.cmd == "ingest":
        do_ingest(args.target, Path(args.vault), args.force, args.no_transcribe)
        return

    if args.cmd == "batch":
        do_batch(args.home, Path(args.vault), args.limit, args.force, args.no_transcribe)
        return

    if args.cmd == "transcribe":
        audio = decode_audio(Path(args.file))
        for seg in transcribe(audio):
            print(f"[{fmt_ts(seg['start'])}] {seg['text']}")
        return


if __name__ == "__main__":
    main()
