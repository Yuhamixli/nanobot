# init_skill 设计与实现论述

## 一、init_skill 的优点

### 1.1 规范化与一致性

- **统一目录结构**：每个新 skill 都遵循 `SKILL.md` + 可选的 `scripts/`、`references/`、`assets/`，避免 agent 自由发挥导致结构混乱。
- **命名规范**：自动将用户输入（如 "Plan Mode"）规范为 hyphen-case（`plan-mode`），符合 nanobot 的 skill 命名约定。
- **Frontmatter 模板**：预填 `name`、`description` 占位，减少 YAML 语法错误和遗漏。

### 1.2 降低 LLM 出错率

- **模板驱动**：agent 无需从零生成完整 SKILL.md，只需在 TODO 处填空，大幅减少格式错误、遗漏必填字段等问题。
- **结构化引导**：模板内含「Structuring This Skill」等设计模式说明（Workflow-Based、Task-Based、Reference/Guidelines、Capabilities-Based），引导 agent 选择合适结构。
- **资源占位**：`--examples` 可生成 scripts/references/assets 的示例文件，agent 可替换而非凭空编写。

### 1.3 提高开发效率

- **一步生成骨架**：一条命令完成目录创建、SKILL.md 生成、资源目录初始化，agent 可立即进入「编辑内容」阶段。
- **可复用**：人类开发者也可直接使用 `init_skill.py` 快速 scaffolding，不依赖 agent。

### 1.4 可扩展性

- **按需资源**：`--resources scripts,references,assets` 可选择性创建，避免空目录 clutter。
- **示例开关**：`--examples` 仅在需要时生成占位文件，保持最小侵入。

---

## 二、OpenClaw 能力概览

### 2.1 技能体系

OpenClaw 的 skill 体系与 nanobot 类似：

- **SKILL.md**：YAML frontmatter + Markdown 指令，描述 skill 功能与触发条件。
- **scripts/**：可执行代码（Python/Bash 等），用于确定性操作。
- **references/**：参考文档，按需加载到 context。
- **assets/**：模板、图标等，不加载到 context，供输出使用。

### 2.2 创建方式

| 方式 | 说明 |
|------|------|
| **Natural Language** | `openclaw skills create weather-reporter --description "..."`，由 LLM 生成实现。 |
| **TypeScript/Full** | 使用 `@openclaw/sdk` 编写 TypeScript 模块，类型安全、可接入 npm。 |
| **skill-creator + init_skill** | Agent 按 skill-creator 指导，调用 `init_skill.py` 生成骨架，再编辑。 |

### 2.3 init_skill.py 功能（OpenClaw 版）

- 创建 skill 目录
- 生成带 TODO 的 SKILL.md 模板（含 4 种结构模式说明）
- 可选创建 `scripts/`、`references/`、`assets/`
- 可选 `--examples` 生成占位文件（example.py、api_reference.md、example_asset.txt）
- 名称规范化（lowercase hyphen-case）、长度校验（≤64 字符）

### 2.4 package_skill.py 功能

- 验证 skill 结构（frontmatter、命名、目录）
- 打包为 `.skill` 文件（zip 格式），便于分发
- 依赖 `quick_validate` 模块

### 2.5 其他能力

- **openclaw skills test**：用测试输入运行 skill
- **ClawHub**：skill 注册表，可搜索、安装社区 skill
- **Sandbox 模式**：测试时在沙箱中运行

---

## 三、nanobot 差异与设计思考

### 3.1 与 OpenClaw 的差异

| 维度 | OpenClaw | nanobot |
|------|----------|---------|
| 运行时 | Node.js | Python |
| 技能 CLI | `openclaw skills create/test/install` | 无独立 skills CLI |
| 技能加载 | workspace + managed + bundled | workspace + builtin |
| 分发 | .skill 文件 + ClawHub | 暂无，直接放 workspace/skills |
| init_skill | 存在于 skill-creator/scripts/ | **缺失**，需实现 |

### 3.2 设计决策

1. **只实现 init_skill，package_skill 可选**  
   nanobot 当前无 .skill 分发机制，用户 skill 直接放在 `workspace/skills/`。init_skill 是刚需（agent 创建 skill 时可用）；package_skill 可后续补充。

2. **路径适配**  
   agent 通过 `exec` 调用时，工作目录可能是项目根或 workspace。init_skill 的 `--path` 应支持：
   - 绝对路径：`~/.nanobot/workspace/skills`
   - 相对路径：`workspace/skills`（从项目根）或 `skills`（从 workspace）

3. **模板本地化**  
   - 保留 OpenClaw 模板的结构化引导（4 种模式），对 agent 有价值。
   - 将 "Codex" 等 OpenClaw 专有引用改为 "agent"。
   - 可选：增加中文注释，便于中文场景。

4. **脚本位置**  
   放在 `nanobot/skills/skill-creator/scripts/init_skill.py`，与 OpenClaw 一致。agent 调用示例：
   ```bash
   python nanobot/skills/skill-creator/scripts/init_skill.py my-skill --path ~/.nanobot/workspace/skills --resources scripts,references --examples
   ```
   或从 workspace 执行时：
   ```bash
   python /path/to/nanobot/nanobot/skills/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts
   ```

5. **CLI 入口（可选）**  
   可增加 `nanobot skill init <name> [--path] [--resources] [--examples]`，便于人类使用；agent 仍可直接 `exec` 调用 Python 脚本。

---

## 四、实现要点

- 复用 OpenClaw 的 init_skill 逻辑，适配 nanobot 路径与术语。
- 确保 `--path` 支持 `~` 展开和相对路径。
- 模板中 "Codex" → "agent"。
- 输出「Next steps」时，提示编辑 SKILL.md、运行 `nanobot agent` 测试。
- 不依赖 quick_validate，package_skill 若实现则内联简单校验（frontmatter、SKILL.md 存在性）。
