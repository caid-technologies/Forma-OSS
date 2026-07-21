use blueprint_edge::{
    linux_snapshot_event, parse_json_payload, stream_llama_cpp_chat_to_agents,
    stream_ollama_chat_to_agents, stream_stdin_as_events, write_event_jsonl, AgentStreamWriter,
    FormaEdgeEvent, EdgeConfig, EdgeError, EdgeRuntime, LiveTcpStreamHub,
    LlamaCppChatStreamRequest, LocalSpacebaseStream, OllamaChatStreamRequest, SourceDescriptor,
    SpacebaseAgentConfig,
};
use clap::{Parser, Subcommand};
use serde_json::json;
use std::fs::{self, File};
use std::io;
use std::path::PathBuf;
use std::time::Duration;

#[derive(Debug, Parser)]
#[command(name = "blueprint-edge")]
#[command(about = "Forma Rust integration process for source listeners and Linux edge events.")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Emit one JSONL event from an inline JSON payload.
    Emit {
        #[arg(long, default_value = "manual")]
        source_type: String,
        #[arg(long, default_value = "manual")]
        name: String,
        #[arg(long, default_value = "source.event")]
        kind: String,
        #[arg(long, default_value = "{}")]
        payload: String,
    },
    /// Read stdin line-by-line and emit one JSONL event per line.
    Stdin {
        #[arg(long, default_value = "stdin")]
        name: String,
        #[arg(long, default_value = "stdin.line")]
        kind: String,
    },
    /// Emit a Linux environment snapshot from /proc and /etc/os-release.
    LinuxSnapshot {
        #[arg(long, default_value = "local-linux")]
        name: String,
    },
    /// Run a long-lived MCP stdio server for agents and host processes.
    Mcp {
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Stream an Ollama chat response and fan out every chunk to agent outputs.
    OllamaStream {
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        model: Option<String>,
        #[arg(long)]
        base_url: Option<String>,
        #[arg(long)]
        system: Option<String>,
        #[arg(long)]
        prompt: String,
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        stdout: bool,
        #[arg(long)]
        listen_tcp: Option<String>,
        #[arg(long, default_value_t = 128)]
        live_replay: usize,
        #[arg(long, action = clap::ArgAction::SetTrue)]
        wait_for_live_listener: bool,
        #[arg(long, default_value_t = 30.0)]
        live_wait_seconds: f64,
        #[arg(long = "agent-output", value_parser = parse_agent_output)]
        agent_outputs: Vec<AgentOutputSpec>,
    },
    /// Stream llama.cpp OpenAI-compatible chat chunks into local agent streams.
    LlamaCppStream {
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        model: Option<String>,
        #[arg(long)]
        base_url: Option<String>,
        #[arg(long)]
        system: Option<String>,
        #[arg(long)]
        prompt: String,
        #[arg(long)]
        stream_id: Option<String>,
        #[arg(long = "agent")]
        agents: Vec<String>,
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        spacebase: bool,
        #[arg(long, default_value_t = false, action = clap::ArgAction::Set)]
        stdout: bool,
        #[arg(long)]
        listen_tcp: Option<String>,
        #[arg(long, default_value_t = 128)]
        live_replay: usize,
        #[arg(long, action = clap::ArgAction::SetTrue)]
        wait_for_live_listener: bool,
        #[arg(long, default_value_t = 30.0)]
        live_wait_seconds: f64,
        #[arg(long = "agent-output", value_parser = parse_agent_output)]
        agent_outputs: Vec<AgentOutputSpec>,
    },
    /// Read events from a local Spacebase stream or one agent stream file.
    SpacebaseRead {
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        stream_id: Option<String>,
        #[arg(long)]
        agent: Option<String>,
        #[arg(long)]
        limit: Option<usize>,
    },
}

fn main() -> Result<(), CliError> {
    let cli = Cli::parse();
    match cli.command {
        Command::Emit {
            source_type,
            name,
            kind,
            payload,
        } => {
            let payload = parse_json_payload(&payload)?;
            let source = SourceDescriptor::new("blueprint-edge", source_type, name);
            let event = FormaEdgeEvent::new(kind, source, payload);
            write_event_jsonl(io::stdout(), &event)?;
        }
        Command::Stdin { name, kind } => {
            let stdin = io::stdin();
            let source = SourceDescriptor::new("blueprint-edge", "stdin", name);
            let count = stream_stdin_as_events(stdin.lock(), io::stdout(), source, &kind)?;
            let _ = count;
        }
        Command::LinuxSnapshot { name } => {
            let event = linux_snapshot_event(&name).with_metadata(json!({
                "collection": "best_effort",
                "platform": "linux",
            }));
            write_event_jsonl(io::stdout(), &event)?;
        }
        Command::Mcp { config } => {
            let config = match config {
                Some(path) => EdgeConfig::load(path)?,
                None => EdgeConfig::default(),
            };
            if !config.mcp.enabled {
                return Err(
                    EdgeError::Protocol("MCP server is disabled by config".to_string()).into(),
                );
            }
            let stdin = io::stdin();
            EdgeRuntime::new(config).serve_mcp_stdio(stdin.lock(), io::stdout())?;
        }
        Command::OllamaStream {
            config,
            model,
            base_url,
            system,
            prompt,
            stdout,
            listen_tcp,
            live_replay,
            wait_for_live_listener,
            live_wait_seconds,
            agent_outputs,
        } => {
            let mut config = match config {
                Some(path) => EdgeConfig::load(path)?,
                None => EdgeConfig::default(),
            };
            if let Some(base_url) = base_url {
                config.sources.ollama.base_url = base_url;
            }
            let model = model.unwrap_or_else(|| config.sources.ollama.default_model.clone());
            let request = OllamaChatStreamRequest {
                model,
                prompt,
                system,
                ..OllamaChatStreamRequest::default()
            };
            let mut outputs = open_optional_agent_outputs(stdout, agent_outputs)?;
            let live_hub = add_live_tcp_output(&mut outputs, listen_tcp, live_replay)?;
            wait_for_live_listener_if_requested(
                &live_hub,
                wait_for_live_listener,
                live_wait_seconds,
            )?;
            ensure_outputs(
                &outputs,
                "ollama-stream needs stdout=true, --listen-tcp, or at least one --agent-output",
            )?;
            let _summary = stream_ollama_chat_to_agents(&config, request, &mut outputs)?;
        }
        Command::LlamaCppStream {
            config,
            model,
            base_url,
            system,
            prompt,
            stream_id,
            agents,
            spacebase,
            stdout,
            listen_tcp,
            live_replay,
            wait_for_live_listener,
            live_wait_seconds,
            agent_outputs,
        } => {
            let mut config = match config {
                Some(path) => EdgeConfig::load(path)?,
                None => EdgeConfig::default(),
            };
            if let Some(base_url) = base_url {
                config.sources.llama_cpp.base_url = base_url;
            }
            let model = model.unwrap_or_else(|| config.sources.llama_cpp.default_model.clone());
            let request = LlamaCppChatStreamRequest {
                model,
                prompt,
                system,
                ..LlamaCppChatStreamRequest::default()
            };
            let mut outputs = open_optional_agent_outputs(stdout, agent_outputs)?;
            let live_hub = add_live_tcp_output(&mut outputs, listen_tcp, live_replay)?;
            if spacebase {
                let stream =
                    LocalSpacebaseStream::from_config(&config.spacebase, stream_id.as_deref());
                let stream_agents = selected_spacebase_agents(&config, &agents);
                outputs.extend(stream.open_agent_outputs(&stream_agents, true)?);
            }
            if outputs.is_empty() {
                return Err(EdgeError::Provider(
                    "llama-cpp-stream needs --spacebase true, --stdout true, or --agent-output"
                        .to_string(),
                )
                .into());
            }
            wait_for_live_listener_if_requested(
                &live_hub,
                wait_for_live_listener,
                live_wait_seconds,
            )?;
            let _summary = stream_llama_cpp_chat_to_agents(&config, request, &mut outputs)?;
        }
        Command::SpacebaseRead {
            config,
            stream_id,
            agent,
            limit,
        } => {
            let config = match config {
                Some(path) => EdgeConfig::load(path)?,
                None => EdgeConfig::default(),
            };
            let stream = LocalSpacebaseStream::from_config(&config.spacebase, stream_id.as_deref());
            for event in stream.read_events(agent.as_deref(), limit)? {
                println!("{}", serde_json::to_string(&event)?);
            }
        }
    }
    Ok(())
}

#[derive(Debug, Clone)]
struct AgentOutputSpec {
    name: String,
    path: PathBuf,
}

fn parse_agent_output(raw: &str) -> Result<AgentOutputSpec, String> {
    let Some((name, path)) = raw.split_once('=') else {
        return Err("agent output must use name=path".to_string());
    };
    let name = name.trim();
    let path = path.trim();
    if name.is_empty() {
        return Err("agent output name cannot be empty".to_string());
    }
    if path.is_empty() {
        return Err("agent output path cannot be empty".to_string());
    }
    Ok(AgentOutputSpec {
        name: name.to_string(),
        path: PathBuf::from(path),
    })
}

fn open_optional_agent_outputs(
    stdout: bool,
    specs: Vec<AgentOutputSpec>,
) -> Result<Vec<AgentStreamWriter<Box<dyn io::Write>>>, CliError> {
    let mut outputs: Vec<AgentStreamWriter<Box<dyn io::Write>>> = Vec::new();
    if stdout {
        outputs.push(AgentStreamWriter::new("stdout", Box::new(io::stdout())));
    }
    for spec in specs {
        if let Some(parent) = spec
            .path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            fs::create_dir_all(parent)?;
        }
        outputs.push(AgentStreamWriter::new(
            spec.name,
            Box::new(File::create(spec.path)?),
        ));
    }
    Ok(outputs)
}

fn add_live_tcp_output(
    outputs: &mut Vec<AgentStreamWriter<Box<dyn io::Write>>>,
    listen_tcp: Option<String>,
    replay_limit: usize,
) -> Result<Option<LiveTcpStreamHub>, CliError> {
    let Some(addr) = listen_tcp else {
        return Ok(None);
    };
    let (hub, local_addr) = LiveTcpStreamHub::bind(&addr, replay_limit)?;
    eprintln!("[blueprint-edge] live stream listening on tcp://{local_addr}");
    outputs.push(AgentStreamWriter::new("live.tcp", Box::new(hub.clone())));
    Ok(Some(hub))
}

fn wait_for_live_listener_if_requested(
    live_hub: &Option<LiveTcpStreamHub>,
    wait_for_live_listener: bool,
    live_wait_seconds: f64,
) -> Result<(), CliError> {
    if !wait_for_live_listener {
        return Ok(());
    }
    let Some(hub) = live_hub else {
        return Err(EdgeError::Provider(
            "--wait-for-live-listener requires --listen-tcp".to_string(),
        )
        .into());
    };
    let wait_seconds = live_wait_seconds.max(0.0);
    eprintln!(
        "[blueprint-edge] waiting up to {wait_seconds:.1}s for one live TCP listener before starting provider stream"
    );
    if hub.wait_for_clients(1, Duration::from_secs_f64(wait_seconds)) {
        eprintln!("[blueprint-edge] live TCP listener connected; starting provider stream");
        Ok(())
    } else {
        Err(EdgeError::Provider(format!(
            "timed out after {wait_seconds:.1}s waiting for a live TCP listener"
        ))
        .into())
    }
}

fn ensure_outputs(
    outputs: &[AgentStreamWriter<Box<dyn io::Write>>],
    message: &str,
) -> Result<(), CliError> {
    if outputs.is_empty() {
        return Err(EdgeError::Provider(message.to_string()).into());
    }
    Ok(())
}

fn selected_spacebase_agents(
    config: &EdgeConfig,
    requested: &[String],
) -> Vec<SpacebaseAgentConfig> {
    if requested.is_empty() {
        return config.spacebase.agents.clone();
    }
    requested
        .iter()
        .map(|name| {
            config
                .spacebase
                .agents
                .iter()
                .find(|agent| agent.name == *name)
                .cloned()
                .unwrap_or_else(|| SpacebaseAgentConfig {
                    name: name.clone(),
                    role: "consume streamed llama.cpp output".to_string(),
                    source: "contra-mcp".to_string(),
                    model: "unknown".to_string(),
                })
        })
        .collect()
}

#[derive(Debug)]
enum CliError {
    Edge(EdgeError),
    Json(serde_json::Error),
}

impl std::fmt::Display for CliError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CliError::Edge(error) => write!(formatter, "{error}"),
            CliError::Json(error) => write!(formatter, "invalid payload JSON: {error}"),
        }
    }
}

impl std::error::Error for CliError {}

impl From<EdgeError> for CliError {
    fn from(value: EdgeError) -> Self {
        CliError::Edge(value)
    }
}

impl From<io::Error> for CliError {
    fn from(value: io::Error) -> Self {
        CliError::Edge(EdgeError::Io(value))
    }
}

impl From<serde_json::Error> for CliError {
    fn from(value: serde_json::Error) -> Self {
        CliError::Json(value)
    }
}
