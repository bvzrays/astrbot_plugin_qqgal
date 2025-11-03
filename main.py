from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

from typing import Dict, Any, List
import base64
import mimetypes
import os
import random


@register("astrbot_plugin_qqgal", "bvzrays", "引用文本生成 GalGame 风格选项", "1.0.0")
class QQGalPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._cfg_obj = config or {}
        # 背景目录就绪
        try:
            base_dir = os.path.dirname(__file__)
            bg_dir = os.path.join(base_dir, str(self.cfg().get("background_dir", "background")))
            os.makedirs(bg_dir, exist_ok=True)
        except Exception:
            pass

    def cfg(self) -> Dict[str, Any]:
        try:
            return self._cfg_obj if self._cfg_obj is not None else {}
        except Exception:
            return {}

    async def _extract_quoted_text(self, event: AstrMessageEvent) -> str:
        """获取作为选项依据的原文：
        1) 若消息携带文本参数，优先使用参数文本（指令词后内容）。
        2) 若为引用消息（OneBot v11/Napcat），尝试通过 get_msg 拉取被回复消息的纯文本。
        3) 否则返回空串。
        """
        # 1) 文本参数
        try:
            text = event.message_str or ""
            for tok in ["/选项", "选项", "/gal", "gal", "/gal选项", "gal选项"]:
                if text.startswith(tok):
                    text = text[len(tok):].strip()
                    break
            if text:
                logger.debug(f"[qqgal] using inline text as base_text, len={len(text)}")
                return text
        except Exception:
            pass

        # 2) 引用消息（OneBot v11）
        try:
            raw = event.message_obj.raw_message
            if isinstance(raw, dict):
                # 从消息链中找 reply 组件
                reply_id = None
                for seg in raw.get("message", []) or []:
                    if isinstance(seg, dict) and seg.get("type") == "reply":
                        data = seg.get("data", {}) or {}
                        reply_id = data.get("id") or data.get("message_id")
                        break
                if reply_id and event.get_platform_name() == "aiocqhttp":
                    logger.debug(f"[qqgal] detected reply id={reply_id}, try get_msg")
                    # 调 OneBot get_msg
                    try:
                        client = getattr(event, "bot", None)
                        if client is not None:
                            ret = await client.api.call_action("get_msg", message_id=int(reply_id))
                            # ret 结构兼容 OneBot：{"message": [ {type,text...} ] } 或 "message": "..."
                            msg = ret.get("message") if isinstance(ret, dict) else None
                            if isinstance(msg, list):
                                # 拼接纯文本
                                parts = []
                                for seg in msg:
                                    if seg.get("type") == "text":
                                        parts.append(seg.get("data", {}).get("text", ""))
                                txt = "".join(parts).strip()
                                if txt:
                                    logger.debug(f"[qqgal] got quoted text from get_msg, len={len(txt)}")
                                    return txt
                            elif isinstance(msg, str):
                                txt = msg.strip()
                                if txt:
                                    logger.debug(f"[qqgal] got quoted string from get_msg, len={len(txt)}")
                                    return txt
                    except Exception:
                        logger.debug("[qqgal] get_msg failed", exc_info=True)
                        pass
        except Exception:
            pass
        return ""

    def _letters(self, n: int) -> List[str]:
        base = ord('A')
        return [chr(base + i) for i in range(max(0, n))][:26]

    async def _gen_options(self, event: AstrMessageEvent, base_text: str, option_count: int) -> str:
        cfg = self.cfg()
        provider_id = cfg.get("provider_id", "")
        # 内置系统与风格提示
        system_prompt = "你是一个擅长生成互动小说选项的编剧，输出必须简洁、中文、具代入感。"
        style_hint = "中文表达；强情感；生动但简洁；不含命令/系统语。"

        # 选择供应商：优先ID，否则使用当前会话绑定的供应商
        provider = None
        try:
            if provider_id:
                provider = self.context.get_provider_by_id(provider_id)
        except Exception:
            provider = None
        if provider is None:
            provider = self.context.get_using_provider(umo=event.unified_msg_origin)
        if provider is None:
            return "未找到可用的 LLM 供应商，请在 WebUI 选择或在配置中指定 provider_id。"
        try:
            pid = getattr(provider, "provider_id", None) or getattr(provider, "id", None) or "unknown"
            logger.info(f"[qqgal] generating {option_count} options via provider={pid}")
        except Exception:
            logger.info(f"[qqgal] generating {option_count} options via provider=<unknown>")

        letters = ", ".join(self._letters(option_count))
        first_line = f"请基于这段原文所描述的情境，生成 {option_count} 个极具 GalGame 风格 的下一步选项。"
        tmpl = cfg.get("prompt_template", "")
        prompt = (
            first_line + "\n" + (tmpl.rstrip() + "\n\n" if tmpl else "\n")
            + f"触发选项的对方所说的话：【{base_text if base_text else '（无原文，生成一个遇到重要角色的通用浪漫场景）'}】\n"
            + f"你必须遵循的风格/提示：【{style_hint}】\n"
            + f"需要的选项代号：{letters}。\n"
        )

        try:
            resp = await provider.text_chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                model=cfg.get("model", None)
            )
            # 统一抽取文本
            content = getattr(resp, "text", None) or getattr(resp, "content", None)
            if not content:
                rc = getattr(resp, "result_chain", None)
                if rc and getattr(rc, "chain", None):
                    try:
                        from astrbot.api.message_components import Plain
                    except Exception:
                        Plain = None
                    parts = []
                    for seg in rc.chain:
                        if hasattr(seg, "text"):
                            parts.append(str(seg.text))
                    content = "\n".join(parts)
            if not content:
                content = str(resp)
            content = str(content).strip()
            logger.debug(f"[qqgal] raw llm content len={len(content)}")
            return content
        except Exception as e:
            logger.error(f"调用 LLM 失败: {e}")
            return "LLM 调用失败，请稍后重试。"

    def _normalize_options(self, raw: str, n: int) -> str:
        """规范化 LLM 输出：
        - 优先提取以 大写字母. 开头的行（A./B./C.）。
        - 不足 n 行时，从其余非空行补齐并自动加前缀；超过则截断。
        - 始终输出恰好 n 行。
        """
        lines = [ln.strip() for ln in (raw or "").splitlines()]
        letter_lines = []
        other = []
        for ln in lines:
            if not ln:
                continue
            if len(ln) >= 3 and ln[0].isalpha() and ln[1] == '.' and ln[2] == ' ':
                # 形如 A. 文本
                letter_lines.append(ln)
            else:
                other.append(ln)
        result = []
        # 先取正确格式的
        for ln in letter_lines:
            if len(result) >= n:
                break
            result.append(ln)
        # 不足则从其它行补齐并加前缀
        idx = 0
        letters = self._letters(n)
        while len(result) < n and idx < len(other):
            result.append(f"{letters[len(result)]}. {other[idx]}")
            idx += 1
        # 若仍不足，填充占位
        while len(result) < n:
            result.append(f"{letters[len(result)]}. ……")
        # 只保留 n 行
        return "\n".join(result[:n])

    async def _get_display_and_avatar(self, event: AstrMessageEvent) -> tuple[str, str]:
        """优先返回被回复对象（或第一个@对象）的昵称/ID 与头像。

        回退顺序：被回复的人 -> 第一个@的 QQ -> 触发者自身。
        头像采用 qlogo 服务。
        """
        target_id = None
        target_name = None

        try:
            raw = event.message_obj.raw_message
            if isinstance(raw, dict):
                # 1) 被回复对象
                reply_id = None
                for seg in raw.get("message", []) or []:
                    if isinstance(seg, dict) and seg.get("type") == "reply":
                        data = seg.get("data", {}) or {}
                        reply_id = data.get("id") or data.get("message_id")
                        break
                if reply_id and event.get_platform_name() == "aiocqhttp":
                    try:
                        client = getattr(event, "bot", None)
                        if client is not None:
                            ret = await client.api.call_action("get_msg", message_id=int(reply_id))
                            snd = (ret or {}).get("sender", {}) if isinstance(ret, dict) else {}
                            uid = snd.get("user_id") or snd.get("uid") or snd.get("uin")
                            nick = snd.get("card") or snd.get("nickname") or snd.get("nick")
                            if uid:
                                target_id = str(uid)
                                target_name = str(nick or uid)
                    except Exception:
                        logger.debug("[qqgal] get_msg for avatar failed", exc_info=True)

                # 2) 第一个 @ 对象
                if not target_id:
                    for seg in raw.get("message", []) or []:
                        if isinstance(seg, dict) and seg.get("type") == "at":
                            qq = (seg.get("data", {}) or {}).get("qq")
                            if qq and qq != "all":
                                target_id = str(qq)
                                break

        except Exception:
            pass

        # 3) 触发者自身
        if not target_id:
            target_id = event.get_sender_id()
        if not target_name:
            target_name = event.get_sender_name() or target_id

        avatar = f"https://q1.qlogo.cn/g?b=qq&nk={target_id}&s=640"
        display = f"{target_name} ({target_id})"
        return display, avatar

    def _pick_background(self) -> str:
        base_dir = os.path.dirname(__file__)
        rel = str(self.cfg().get("background_dir", "background"))
        dirp = os.path.join(base_dir, rel)
        try:
            files = [f for f in os.listdir(dirp) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            if not files:
                return ""
            choice = random.choice(files)
            return os.path.join(dirp, choice)
        except Exception:
            return ""

    def _data_url(self, path: str) -> str:
        try:
            mime, _ = mimetypes.guess_type(path)
            mime = mime or "image/jpeg"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return ""

    async def _render_image(self, event: AstrMessageEvent, quote: str, options: List[str]) -> str:
        cfg = self.cfg()
        width = int(cfg.get("canvas_width", 1280))
        height = int(cfg.get("canvas_height", 720))
        bg = self._pick_background()
        name, avatar = await self._get_display_and_avatar(event)
        # 嵌入为 data URL，避免 file:// 在某些环境不可读/中文路径问题
        bg_url = self._data_url(bg) if bg else ""

        # 选项纵向位置（保持既有结构）
        opt1_top = int(height * 0.20)
        opt2_top = int(height * 0.34)
        opt3_top = int(height * 0.48)
        opt4_top = int(height * 0.62)

        # 引用框宽度（用于与头像/名字关联），以及引用块顶端位置
        quote_w = int(width * 0.86)
        quote_top = max(opt3_top + 110, int(height * 0.68))
        # 仅用于引用区域的延伸毛玻璃（从引用块顶端到底部），覆盖整幅画面的下半部分
        glass_left = 24
        glass_w = max(0, width - 48)
        glass_top = quote_top
        glass_h = max(120, height - glass_top)

        # 构建 HTML 模板
        html = f"""
<html>
<head>
<meta charset='utf-8'/>
<style>
  body {{ margin:0; width:{width}px; height:{height}px; font-family: 'Microsoft Yahei', sans-serif; }}
  .root {{ position:relative; width:{width}px; height:{height}px; background:#000; overflow:hidden; }}
  /* 两层背景：底层模糊铺满，顶层等比完整展示，保证任意比例都好看 */
  .bg-blur {{ position:absolute; inset:0; background-image:url('{bg_url}'); background-size:cover; background-position:center; filter:blur(18px) brightness(0.7); transform:scale(1.06); }}
  .bg-main {{ position:absolute; inset:0; background-image:url('{bg_url}'); background-repeat:no-repeat; background-size:contain; background-position:center; }}
  .topbar {{ position:absolute; left:24px; top:18px; color:#fff; font-weight:700; letter-spacing:1px; text-shadow:0 2px 6px rgba(0,0,0,.6); }}
  :root {{ --quote-width: {quote_w}px; }}
  /* 引用内容容器：自身不加毛玻璃，由下方 .glass 提供延伸到底部的模糊背景 */
  .quote {{ position:absolute; left:50%; transform:translateX(-50%); top:{quote_top}px; width:var(--quote-width); padding:18px 22px 22px 22px; color:#fff; font-size:28px; font-weight:800; line-height:1.5; border-radius:16px; background:transparent; text-align:center; }}
  .glass {{ position:absolute; left:{glass_left}px; top:{glass_top}px; width:{glass_w}px; height:{glass_h}px; background:rgba(0,0,0,.25); backdrop-filter: blur(10px); border-radius:18px; box-shadow:0 10px 30px rgba(0,0,0,.35); }}
  .q-avatar {{ position:absolute; left:16px; top:16px; width:56px; height:56px; border-radius:50%; border:2px solid rgba(255,255,255,.8); background-image:url('{avatar}'); background-size:cover; background-position:center; box-shadow:0 4px 12px rgba(0,0,0,.4); }}
  .q-user {{ position:absolute; left:88px; top:22px; font-size:22px; font-weight:800; text-shadow:0 2px 6px rgba(0,0,0,.6); }}
  .q-text {{ margin-top:88px; font-size:32px; font-weight:900; text-align:center; line-height:1.6; }}
  .option {{ position:absolute; left:50%; transform:translateX(-50%); width:{int(width*0.7)}px; padding:14px 18px; background:rgba(0,0,0,.55); color:#f0f0f0; border-radius:28px; text-align:center; font-size:26px; font-weight:800; letter-spacing:1px; box-shadow:0 8px 20px rgba(0,0,0,.35); border:1px solid rgba(255,255,255,.15); }}
  /* 将选项整体上移，集中在画面上 2/5 区域附近 */
  .opt1 {{ top:{opt1_top}px; }}
  .opt2 {{ top:{opt2_top}px; }}
  .opt3 {{ top:{opt3_top}px; }}
  .opt4 {{ top:{opt4_top}px; }}
</style>
</head>
<body>
  <div class='root'>
    <div class='bg-blur'></div>
    <div class='bg-main'></div>
    <div class='topbar'>CHAPTER</div>
    <div class='glass'></div>
    <div class='quote'>
      <div class='q-avatar'></div>
      <div class='q-user'>{name}</div>
      <div class='q-text'>{quote}</div>
    </div>
    {''.join([f"<div class='option opt{i+1}'>"+opt+"</div>" for i,opt in enumerate(options)])}
  </div>
</body>
</html>
"""
        # 输出图片质量（仅 jpeg 生效）
        quality = int(cfg.get("image_quality", 85))
        if quality < 10:
            quality = 10
        if quality > 100:
            quality = 100
        options_dict = {"type": "jpeg", "quality": quality}
        url = await self.html_render(html, data={}, options=options_dict)
        return url

    def _parse_count_from_text(self, text: str, default_n: int, min_n: int, max_n: int) -> int:
        try:
            nums = []
            cur = ""
            for ch in text:
                if ch.isdigit():
                    cur += ch
                else:
                    if cur:
                        nums.append(int(cur))
                        cur = ""
            if cur:
                nums.append(int(cur))
            if nums:
                n = nums[-1]
                return max(min_n, min(max_n, n))
        except Exception:
            pass
        return max(min_n, min(max_n, default_n))

    @filter.command("选项", alias={"gal", "gal选项"})
    async def make_gal_options(self, event: AstrMessageEvent):
        """引用或跟随文本，生成 GalGame 风格选项。数量可选，默认 3。"""
        try:
            cfg = self.cfg()
            default_n = int(cfg.get("option_count", 3))
            # 从文本中解析数量（最后一个整数）；无则用默认；限制 1~26
            n = self._parse_count_from_text(event.message_str or "", default_n, 1, 26)
            logger.debug(f"[qqgal] parsed option count n={n}")

            base_text = await self._extract_quoted_text(event)
            sep = cfg.get("message_separator", "-------------------------")
            title = cfg.get("title", "🎮 GalGame 选项")
            show_quote = bool(cfg.get("show_quote", True))

            options_raw = await self._gen_options(event, base_text, n)
            options_text = self._normalize_options(options_raw, n)
            logger.debug(f"[qqgal] normalized options:\n{options_text}")

            if bool(cfg.get("render_image", False)):
                options_list = [ln.strip() for ln in options_text.splitlines() if ln.strip()]
                img_url = await self._render_image(event, base_text or "（无原文）", options_list)
                yield event.image_result(img_url)
            else:
                lines = [title, sep]
                if show_quote and base_text:
                    lines.append(f"📝 原文：{base_text}")
                    lines.append(sep)
                lines.append(options_text)
                yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"生成选项失败: {e}")
            yield event.plain_result("生成选项失败，请稍后重试。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def _fallback_any(self, event: AstrMessageEvent):
        """兼容某些平台在消息前插入 reply 等组件导致命令未命中的情况。
        当文本中以 /选项、选项、/gal、gal 起始时，触发与命令相同的逻辑。
        """
        try:
            text = (event.message_str or "").strip()
            raw = text.lstrip('*').lstrip()
            prefixes = ("/选项", "选项", "/gal", "gal")
            if not any(raw.startswith(p) for p in prefixes):
                return
            # 调用与指令一致的处理
            logger.debug("[qqgal] fallback trigger matched, dispatch to make_gal_options")
            await self.make_gal_options(event)
            # 阻断默认 LLM 回复
            event.stop_event()
        except Exception:
            pass

    async def terminate(self):
        pass
