# astrbot_plugin_qqgal

GalGame 风格“选项生成 + 图片渲染”插件（AstrBot 框架，Napcat/OneBot11 测试通过）。

> 将聊天中的“引用消息”作为语境，调用 AstrBot 已配置的大模型生成 A/B/C… 选项，并以 GalGame UI 风格渲染为图片：
> - 顶部保留 CHAPTER 与三条选项（无毛玻璃）；
> - 底侧展示“被回复者”的头像与昵称/ID；
> - 引用内容置中加粗，并拥有自上而下延伸至底部的毛玻璃背景。

## 功能特性
- 生成 GalGame 风格的下一步选项（数量可自定义）。
- 自动识别“被回复者/第一个@对象”的头像与昵称。
- 双层背景：模糊铺底 + 等比居中，适配任意比例图片。
- 引用区域毛玻璃自引用顶端向下覆盖到底部，视觉层级更清晰。
- 可配置图片质量、画布大小、默认选项数、提示模板等。

提示：开发与验证基于 AstrBot，协议端以 Napcat(OneBot 11) 测试通过；其它实现未做适配验证。

## 指令
- `/选项 [数量]`
- 别名：`/gal`、`/gal选项`、`选项`

说明：
- 若指令后直接跟文本，优先使用该文本作为语境；
- 若为“引用消息”，会读取被回复消息文本作为语境；
- 未给出数量时使用默认值（见配置）。

## 安装与使用
1. 安装 AstrBot（参考官方文档）。
2. 将本项目放入 `AstrBot/data/plugins/astrbot_plugin_qqgal/` 目录。
3. 在 AstrBot WebUI → 插件管理 中启用插件并配置参数。
4. 协议端推荐 Napcat（OneBot 11）。
5. 在群聊/私聊中直接使用上述指令，或先引用消息再发送指令。

## 资源（背景图）
- 在插件目录下的 `background/` 放入图片（支持 `jpg/jpeg/png/webp`）。
- 渲染时随机选择一张：
  - 底层：`cover + blur` 铺满；
  - 顶层：`contain` 等比居中，不拉伸。

## 配置项（WebUI 或 `_conf_schema.json` 对应键）
- `render_image`（bool，默认 false）：是否启用图片渲染。
- `option_count`（int，默认 3）：默认生成的选项数量。
- `canvas_width`（int，默认 1280）：画布宽度。
- `canvas_height`（int，默认 720）：画布高度。
- `background_dir`（string，默认 `background`）：背景图目录（相对插件目录）。
- `provider_id`（string，可选）：固定使用的 LLM 提供商 ID；留空则使用当前会话配置。
- `model`（string，可选）：强制指定模型名。
- `prompt_template`（string，可选）：追加到系统提示后的自定义模板片段。
- `title`（string，默认 `🎮 GalGame 选项`）：纯文本模式标题。
- `show_quote`（bool，默认 true）：纯文本模式是否显示引用原文。
- `message_separator`（string，默认一串 `-`）：纯文本模式分隔线。
- `image_quality`（int，默认 85，范围 10–100）：导出 JPEG 质量（越大越清晰，体积越大）。

> 图片渲染使用 AstrBot 提供的 `html_render`，`image_quality` 仅在 JPEG 输出时生效。

## 工作流程
1. 提取语境（指令后文本 > 被引用消息 > 空）。
2. 调用 AstrBot Provider 生成 A/B/C… 选项并规范化输出。
3. 若开启图片渲染：渲染背景与 UI 元素，引用区域毛玻璃自顶端延伸到底部，并返回图片。

## 兼容性
- 框架：AstrBot
- 协议端：Napcat（OneBot 11）已测试
- 其它 OneBot 实现：未验证

## 许可
仅用于学习交流。放入的背景图片请确保拥有相应版权或授权。

## 致谢
- AstrBot 项目与社区
- Napcat / OneBot 生态
## astrbot_plugin_qqgal · Gal 风格选项生成

### 功能
- 引用或跟随一段文本，生成 GalGame 风格的多分支“下一步选项”
- LLM 供应商可选（配置 provider_id；留空使用当前会话默认）
- 选项数量可控（默认 3，可设最小/最大）
- 输出标题、分隔线、是否显示原文均可配置

### 指令
- `/选项 [数量]`（别名：`gal`、`gal选项`）
  - 在消息中“引用他人消息”或在指令后附上文本
  - 参数“数量”可选，不填使用默认

### 配置（_conf_schema.json）
- provider_id：首选 LLM 供应商ID（为空则用当前会话默认）
- model：可选模型名（为空用供应商默认）
- default_option_count / min_option_count / max_option_count：数量设置
- system_prompt：系统提示词模板
- style_hint：风格提示文本
- title：输出标题
- message_separator：分隔线
- show_quote：是否在输出中包含“原文”

### 说明
- 若引用消息存在（OneBot/Napcat），插件会通过 `get_msg` 拉取被回复消息的纯文本作为原文；否则使用指令后的文本；都没有则生成通用场景选项。

### 安装
- 将本插件文件夹放到 `AstrBot/data/plugins/astrbot_plugin_qqgal` 并在 WebUI 启用
- 在 WebUI 中调整配置，保存后即时生效
