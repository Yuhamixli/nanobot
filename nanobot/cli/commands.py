"""CLI commands for nanobot."""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nanobot import __version__, __logo__

# Use ASCII on Windows when console encoding is not UTF-8 (e.g. GBK) to avoid UnicodeEncodeError
def _enc_utf8():
    enc = getattr(sys.stdout, "encoding", None) or ""
    return enc.lower().startswith("utf")


def _check():
    return "✓" if _enc_utf8() else "OK"


def _cross():
    return "✗" if _enc_utf8() else "x"


def _logo():
    return __logo__ if _enc_utf8() else "[nanobot]"


app = typer.Typer(
    name="nanobot",
    help=f"{_logo()} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"{_logo()} nanobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """nanobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize nanobot configuration and workspace."""
    from nanobot.config.loader import get_config_path, save_config
    from nanobot.config.schema import Config
    from nanobot.utils.helpers import get_workspace_path
    
    config_path = get_config_path()
    
    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not typer.confirm("Overwrite?"):
            raise typer.Exit()
    
    # Create default config
    config = Config()
    save_config(config)
    console.print(f"[green]{_check()}[/green] Created config at {config_path}")
    
    # Create workspace
    workspace = get_workspace_path()
    console.print(f"[green]{_check()}[/green] Created workspace at {workspace}")
    
    # Create default bootstrap files
    _create_workspace_templates(workspace)
    
    console.print(f"\n{_logo()} nanobot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. Chat: [cyan]nanobot agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")




def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files
- For company policies or regulations: use knowledge_search to query the local knowledge base; use knowledge_ingest to import new documents
""",
        "SOUL.md": """# Soul

I am nanobot, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }
    
    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")
    
    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
        console.print("  [dim]Created memory/MEMORY.md[/dim]")

    # Create knowledge directory for RAG (place policy/docs here, then run nanobot knowledge ingest)
    knowledge_dir = workspace / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    knowledge_readme = knowledge_dir / "README.md"
    if not knowledge_readme.exists():
        knowledge_readme.write_text("""# Knowledge Base 知识库

将制度、规范、政策等文档放在此目录下，支持格式：TXT、MD、PDF、Word(.docx)、Excel(.xlsx)。

导入到知识库：
- 命令行：`nanobot knowledge ingest`
- 或让 agent 执行：knowledge_ingest 工具，path 填 `knowledge`

导入后，用户提问时 agent 会通过 knowledge_search 检索并基于检索结果回答。
""", encoding="utf-8")
        console.print("  [dim]Created knowledge/README.md[/dim]")

# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanobot gateway."""
    from nanobot.config.loader import load_config, get_data_dir
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.agent.loop import AgentLoop
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    console.print(f"{_logo()} Starting nanobot gateway on port {port}...")
    
    config = load_config()
    
    # Create components
    bus = MessageBus()
    
    # Create provider (supports OpenRouter, Anthropic, OpenAI, Bedrock)
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        from nanobot.config.loader import get_config_path
        config_path = get_config_path()
        console.print("[red]Error: No API key configured.[/red]")
        console.print(f"Config file: [cyan]{config_path}[/cyan]")
        console.print("Add one of: [cyan]providers.openrouter.apiKey[/cyan], [cyan]providers.openai.apiKey[/cyan], [cyan]providers.anthropic.apiKey[/cyan]")
        console.print("Example: [dim]{\"providers\": {\"openrouter\": {\"apiKey\": \"sk-or-v1-xxx\"}}}[/dim]")
        raise typer.Exit(1)

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )
    
    # Create agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        web_search_proxy=config.tools.web.search.proxy or None,
        exec_config=config.tools.exec,
        knowledge_config=config.tools.knowledge,
    )
    
    # Create cron service
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}"
        )
        # Optionally deliver to channel
        if job.payload.deliver and job.payload.to:
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "whatsapp",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path, on_job=on_cron_job)
    
    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")
    
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True
    )
    
    # Create channel manager
    channels = ChannelManager(config, bus)
    
    if channels.enabled_channels:
        console.print(f"[green]{_check()}[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")
    
    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]{_check()}[/green] Cron: {cron_status['jobs']} scheduled jobs")
    
    console.print(f"[green]{_check()}[/green] Heartbeat: every 30m")
    
    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()
    
    asyncio.run(run())




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
):
    """Interact with the agent directly."""
    from nanobot.config.loader import load_config, get_config_path
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.agent.loop import AgentLoop
    
    config = load_config()
    config_path = get_config_path()

    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_bedrock = model.startswith("bedrock/")

    if not api_key and not is_bedrock:
        console.print("[red]Error: No API key configured.[/red]")
        console.print(f"Config file: [cyan]{config_path}[/cyan]")
        console.print("Add one of: [cyan]providers.openrouter.apiKey[/cyan], [cyan]providers.openai.apiKey[/cyan], [cyan]providers.anthropic.apiKey[/cyan]")
        console.print("Example: [dim]{\"providers\": {\"openrouter\": {\"apiKey\": \"sk-or-v1-xxx\"}}}[/dim]")
        raise typer.Exit(1)

    bus = MessageBus()
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )
    
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        brave_api_key=config.tools.web.search.api_key or None,
        web_search_proxy=config.tools.web.search.proxy or None,
        exec_config=config.tools.exec,
        knowledge_config=config.tools.knowledge,
    )
    
    if message:
        # Single message mode
        async def run_once():
            response = await agent_loop.process_direct(message, session_id)
            console.print(f"\n{_logo()} {response}")
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        console.print(f"{_logo()} Interactive mode (Ctrl+C to exit)\n")
        
        async def run_interactive():
            while True:
                try:
                    user_input = console.input("[bold blue]You:[/bold blue] ")
                    if not user_input.strip():
                        continue
                    
                    response = await agent_loop.process_direct(user_input, session_id)
                    console.print(f"\n{_logo()} {response}\n")
                except KeyboardInterrupt:
                    console.print("\nGoodbye!")
                    break
        
        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanobot.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        _check() if wa.enabled else _cross(),
        wa.bridge_url
    )

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    if getattr(tg, "proxy_url", None) and tg.proxy_url:
        tg_config += f" proxy: {tg.proxy_url[:20]}..."
    table.add_row(
        "Telegram",
        _check() if tg.enabled else _cross(),
        tg_config
    )

    # WeCom
    wc = config.channels.wecom
    wc_config = f"corp_id: {wc.corp_id[:8]}..." if wc.corp_id else "[dim]not configured[/dim]"
    table.add_row(
        "WeCom",
        _check() if wc.enabled else _cross(),
        wc_config
    )

    # 商网 (Shangwang)
    sw = config.channels.shangwang
    table.add_row(
        "商网",
        _check() if sw.enabled else _cross(),
        sw.bridge_url
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess
    
    # User's bridge location
    user_bridge = Path.home() / ".nanobot" / "bridge"
    
    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge
    
    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)
    
    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)
    
    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge
    
    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanobot")
        raise typer.Exit(1)
    
    console.print(f"{_logo()} Setting up bridge...")
    
    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))
    
    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print(f"[green]{_check()}[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)
    
    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess
    
    bridge_dir = _get_bridge_dir()
    
    console.print(f"{_logo()} Starting bridge...")
    console.print("Scan the QR code to connect.\n")
    
    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Knowledge Base Commands
# ============================================================================

knowledge_app = typer.Typer(help="Local knowledge base (RAG)")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("ingest")
def knowledge_ingest_cmd(
    path: str = typer.Argument(
        "knowledge",
        help="Path to file or folder (relative to workspace); default: 'knowledge'",
    ),
):
    """Import documents into the knowledge base. Put files in workspace/knowledge then run this."""
    from nanobot.config.loader import load_config
    from nanobot.agent.knowledge.store import get_store, SUPPORTED_EXTENSIONS

    config = load_config()
    workspace = config.workspace_path
    kc = config.tools.knowledge
    store = get_store(
        workspace,
        chunk_size=kc.chunk_size,
        chunk_overlap=kc.chunk_overlap,
    )
    if store is None:
        from nanobot.agent.knowledge.store import get_rag_import_error
        err = get_rag_import_error()
        console.print("[red]RAG dependencies not installed.[/red]")
        if err:
            console.print(f"[dim]Missing: {err}[/dim]")
        console.print("[yellow]若已用 pip install nanobot-ai 安装，PyPI 版本可能不包含 [rag]，请任选其一：[/yellow]")
        console.print('  1. 从源码安装（推荐）：[cyan]pip install -e ".\\[rag\\]"[/cyan]（在项目根目录执行）')
        console.print("  2. 手动安装依赖：[cyan]pip install chromadb sentence-transformers pypdf python-docx openpyxl[/cyan]")
        raise typer.Exit(1)
    resolved = (workspace / path).resolve()
    if not resolved.exists():
        if path.strip() in ("knowledge", "knowledge/"):
            resolved.mkdir(parents=True, exist_ok=True)
            readme = resolved / "README.md"
            if not readme.exists():
                readme.write_text(
                    "# 知识库\n将制度/政策文档放于此目录，支持 TXT、MD、PDF、Word、Excel。\n然后执行: nanobot knowledge ingest\n",
                    encoding="utf-8",
                )
            console.print(f"[green]{_check()}[/green] 已创建知识库目录，请将文档放入后重新执行 ingest。")
            console.print(f"路径: [cyan]{resolved}[/cyan]")
            raise typer.Exit(0)
        console.print(f"[red]Path not found: {resolved}[/red]")
        console.print(f"Workspace: [cyan]{workspace}[/cyan]")
        console.print("[dim]请将知识文档放在 workspace 下的 knowledge 目录（见上），不是项目里的 workspace\\knowledge。[/dim]")
        raise typer.Exit(1)
    console.print(f"Ingesting [cyan]{resolved}[/cyan] ...")
    result = store.add_documents([resolved], skip_unsupported=True)
    console.print(f"[green]{_check()}[/green] Added {result['added']} chunk(s).")
    if result.get("errors"):
        for e in result["errors"][:10]:
            console.print(f"  [yellow]{e}[/yellow]")
        if len(result["errors"]) > 10:
            console.print(f"  ... and {len(result['errors']) - 10} more")
    if result.get("skipped"):
        console.print(f"[dim]Skipped (empty): {len(result['skipped'])} file(s)[/dim]")


@knowledge_app.command("status")
def knowledge_status_cmd():
    """Show knowledge base status (chunk count)."""
    from nanobot.config.loader import load_config
    from nanobot.agent.knowledge.store import get_store

    config = load_config()
    store = get_store(config.workspace_path)
    if store is None:
        from nanobot.agent.knowledge.store import get_rag_import_error
        err = get_rag_import_error()
        console.print("[yellow]RAG not installed.[/yellow]")
        if err:
            console.print(f"[dim]Missing: {err}[/dim]")
        console.print("  [cyan]pip install -e \".[rag]\"[/cyan] 或 [cyan]pip install chromadb sentence-transformers pypdf python-docx openpyxl[/cyan]")
        raise typer.Exit(0)
    n = store.count()
    console.print(f"Knowledge base chunks: [cyan]{n}[/cyan]")
    console.print(f"Workspace: [dim]{config.workspace_path}[/dim]")


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    jobs = service.list_jobs(include_disabled=all)
    
    if not jobs:
        console.print("No scheduled jobs.")
        return
    
    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")
    
    import time
    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"
        
        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000))
            next_run = next_time
        
        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"
        
        table.add_row(job.id, job.name, sched, status, next_run)
    
    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"),
):
    """Add a scheduled job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronSchedule
    
    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )
    
    console.print(f"[green]{_check()}[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    if service.remove_job(job_id):
        console.print(f"[green]{_check()}[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]{_check()}[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    async def run():
        return await service.run_job(job_id, force=force)
    
    if asyncio.run(run()):
        console.print(f"[green]{_check()}[/green] Job executed")
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanobot status."""
    from nanobot.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{_logo()} nanobot Status\n")

    console.print(f"Config: {config_path} {'[green]' + _check() + '[/green]' if config_path.exists() else '[red]' + _cross() + '[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]' + _check() + '[/green]' if workspace.exists() else '[red]' + _cross() + '[/red]'}")

    if config_path.exists():
        console.print(f"Model: {config.agents.defaults.model}")
        
        # Check API keys
        has_openrouter = bool(config.providers.openrouter.api_key)
        has_anthropic = bool(config.providers.anthropic.api_key)
        has_openai = bool(config.providers.openai.api_key)
        has_gemini = bool(config.providers.gemini.api_key)
        has_vllm = bool(config.providers.vllm.api_base)
        
        console.print(f"OpenRouter API: {'[green]' + _check() + '[/green]' if has_openrouter else '[dim]not set[/dim]'}")
        console.print(f"Anthropic API: {'[green]' + _check() + '[/green]' if has_anthropic else '[dim]not set[/dim]'}")
        console.print(f"OpenAI API: {'[green]' + _check() + '[/green]' if has_openai else '[dim]not set[/dim]'}")
        console.print(f"Gemini API: {'[green]' + _check() + '[/green]' if has_gemini else '[dim]not set[/dim]'}")
        vllm_status = f"[green]{_check()} {config.providers.vllm.api_base}[/green]" if has_vllm else "[dim]not set[/dim]"
        console.print(f"vLLM/Local: {vllm_status}")


if __name__ == "__main__":
    app()
