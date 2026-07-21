use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::fs;
use std::io::{self, BufRead, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

static EVENT_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct EdgeConfig {
    pub system: EdgeSystemConfig,
    pub mcp: McpServerConfig,
    pub external_mcp: ExternalMcpConfig,
    pub spacebase: SpacebaseLocalConfig,
    pub sources: EdgeSourcesConfig,
}

impl Default for EdgeConfig {
    fn default() -> Self {
        Self {
            system: EdgeSystemConfig::default(),
            mcp: McpServerConfig::default(),
            external_mcp: ExternalMcpConfig::default(),
            spacebase: SpacebaseLocalConfig::default(),
            sources: EdgeSourcesConfig::default(),
        }
    }
}

impl EdgeConfig {
    pub fn load(path: impl AsRef<Path>) -> Result<Self, EdgeError> {
        let raw = fs::read_to_string(path)?;
        Ok(toml::from_str(&raw)?)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct EdgeSystemConfig {
    pub name: String,
    pub instance_id: String,
    pub environment: String,
}

impl Default for EdgeSystemConfig {
    fn default() -> Self {
        Self {
            name: "blueprint-edge".to_string(),
            instance_id: format!("local-{}", process::id()),
            environment: "development".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct McpServerConfig {
    pub enabled: bool,
    pub protocol_version: String,
    pub server_name: String,
    pub server_version: String,
}

impl Default for McpServerConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            protocol_version: "2024-11-05".to_string(),
            server_name: "blueprint-edge".to_string(),
            server_version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ExternalMcpConfig {
    pub contra: ContraMcpConfig,
}

impl Default for ExternalMcpConfig {
    fn default() -> Self {
        Self {
            contra: ContraMcpConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ContraMcpConfig {
    pub enabled: bool,
    pub name: String,
    pub endpoint: String,
    pub metadata_url: String,
    pub authorization_server: String,
    pub required_scope: String,
    pub token_env: String,
}

impl Default for ContraMcpConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            name: "contra-mcp".to_string(),
            endpoint: "https://contra.com/mcp".to_string(),
            metadata_url: "https://contra.com/.well-known/oauth-protected-resource/mcp".to_string(),
            authorization_server: "https://contra.com/api".to_string(),
            required_scope: "mcp:tools".to_string(),
            token_env: "CONTRA_MCP_TOKEN".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct SpacebaseLocalConfig {
    pub enabled: bool,
    pub root_dir: PathBuf,
    pub default_stream: String,
    pub events_file_name: String,
    pub agents_dir_name: String,
    pub agents: Vec<SpacebaseAgentConfig>,
}

impl Default for SpacebaseLocalConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            root_dir: PathBuf::from(".spacebase"),
            default_stream: "llm-stream".to_string(),
            events_file_name: "events.jsonl".to_string(),
            agents_dir_name: "agents".to_string(),
            agents: vec![
                SpacebaseAgentConfig {
                    name: "planner".to_string(),
                    role: "plan next useful action from streamed model output".to_string(),
                    source: "contra-mcp".to_string(),
                    model: "contra.com/mcp".to_string(),
                },
                SpacebaseAgentConfig {
                    name: "critic".to_string(),
                    role: "check streamed model output for failures and contradictions".to_string(),
                    source: "contra-mcp".to_string(),
                    model: "contra.com/mcp".to_string(),
                },
            ],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct SpacebaseAgentConfig {
    pub name: String,
    pub role: String,
    pub source: String,
    pub model: String,
}

impl Default for SpacebaseAgentConfig {
    fn default() -> Self {
        Self {
            name: "agent".to_string(),
            role: "consume streamed events".to_string(),
            source: "local".to_string(),
            model: "unknown".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct EdgeSourcesConfig {
    pub manual: ManualSourceConfig,
    pub stdin: StdinSourceConfig,
    pub linux: LinuxSourceConfig,
    pub ollama: OllamaSourceConfig,
    pub llama_cpp: LlamaCppSourceConfig,
}

impl Default for EdgeSourcesConfig {
    fn default() -> Self {
        Self {
            manual: ManualSourceConfig::default(),
            stdin: StdinSourceConfig::default(),
            linux: LinuxSourceConfig::default(),
            ollama: OllamaSourceConfig::default(),
            llama_cpp: LlamaCppSourceConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ManualSourceConfig {
    pub enabled: bool,
}

impl Default for ManualSourceConfig {
    fn default() -> Self {
        Self { enabled: true }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct StdinSourceConfig {
    pub enabled: bool,
    pub name: String,
}

impl Default for StdinSourceConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            name: "stdin".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct LinuxSourceConfig {
    pub enabled: bool,
    pub name: String,
    pub include_proc: bool,
    pub include_os_release: bool,
}

impl Default for LinuxSourceConfig {
    fn default() -> Self {
        Self {
            enabled: cfg!(target_os = "linux"),
            name: "local-linux".to_string(),
            include_proc: true,
            include_os_release: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct OllamaSourceConfig {
    pub enabled: bool,
    pub name: String,
    pub base_url: String,
    pub default_model: String,
}

impl Default for OllamaSourceConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            name: "local-ollama".to_string(),
            base_url: "http://127.0.0.1:11434".to_string(),
            default_model: "qwen3:0.6b".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct LlamaCppSourceConfig {
    pub enabled: bool,
    pub name: String,
    pub base_url: String,
    pub default_model: String,
}

impl Default for LlamaCppSourceConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            name: "local-llama-cpp".to_string(),
            base_url: "http://127.0.0.1:8080".to_string(),
            default_model: "local-model".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SourceRegistration {
    pub id: String,
    pub enabled: bool,
    pub source_type: String,
    pub name: String,
    pub description: String,
    pub pollable: bool,
    pub streaming: bool,
}

pub fn configured_sources(config: &EdgeConfig) -> Vec<SourceRegistration> {
    vec![
        SourceRegistration {
            id: "manual".to_string(),
            enabled: config.sources.manual.enabled,
            source_type: "manual".to_string(),
            name: "manual".to_string(),
            description: "Manual events submitted through CLI or MCP.".to_string(),
            pollable: false,
            streaming: false,
        },
        SourceRegistration {
            id: "stdin".to_string(),
            enabled: config.sources.stdin.enabled,
            source_type: "stdin".to_string(),
            name: config.sources.stdin.name.clone(),
            description: "Line-oriented stdin event stream.".to_string(),
            pollable: false,
            streaming: true,
        },
        SourceRegistration {
            id: "linux".to_string(),
            enabled: config.sources.linux.enabled,
            source_type: "linux".to_string(),
            name: config.sources.linux.name.clone(),
            description: "Linux host snapshot from /proc and /etc/os-release.".to_string(),
            pollable: true,
            streaming: false,
        },
        SourceRegistration {
            id: "ollama".to_string(),
            enabled: config.sources.ollama.enabled,
            source_type: "llm.stream".to_string(),
            name: config.sources.ollama.name.clone(),
            description: "Local Ollama streaming chat chunks.".to_string(),
            pollable: false,
            streaming: true,
        },
        SourceRegistration {
            id: "llama_cpp".to_string(),
            enabled: config.sources.llama_cpp.enabled,
            source_type: "llm.stream".to_string(),
            name: config.sources.llama_cpp.name.clone(),
            description: "Local llama.cpp OpenAI-compatible streaming chat chunks.".to_string(),
            pollable: false,
            streaming: true,
        },
        SourceRegistration {
            id: "spacebase.local".to_string(),
            enabled: config.spacebase.enabled,
            source_type: "stream.store".to_string(),
            name: config.spacebase.default_stream.clone(),
            description: "Local Spacebase-style JSONL stream store for agent outputs.".to_string(),
            pollable: true,
            streaming: true,
        },
    ]
}

#[derive(Debug, Clone)]
pub struct EdgeRuntime {
    config: EdgeConfig,
}

impl EdgeRuntime {
    pub fn new(config: EdgeConfig) -> Self {
        Self { config }
    }

    pub fn config(&self) -> &EdgeConfig {
        &self.config
    }

    pub fn sources(&self) -> Vec<SourceRegistration> {
        configured_sources(&self.config)
    }

    pub fn handle_mcp_request(&self, request: Value) -> Option<Value> {
        handle_mcp_request(&self.config, request)
    }

    pub fn serve_mcp_stdio(
        &self,
        reader: impl BufRead,
        writer: impl Write,
    ) -> Result<(), EdgeError> {
        serve_mcp_stdio(self.config.clone(), reader, writer)
    }
}

impl Default for EdgeRuntime {
    fn default() -> Self {
        Self::new(EdgeConfig::default())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SourceDescriptor {
    pub provider: String,
    pub source_type: String,
    pub name: String,
    pub uri: Option<String>,
}

impl SourceDescriptor {
    pub fn new(
        provider: impl Into<String>,
        source_type: impl Into<String>,
        name: impl Into<String>,
    ) -> Self {
        Self {
            provider: provider.into(),
            source_type: source_type.into(),
            name: name.into(),
            uri: None,
        }
    }

    pub fn with_uri(mut self, uri: impl Into<String>) -> Self {
        self.uri = Some(uri.into());
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FormaEdgeEvent {
    pub schema_version: u16,
    pub event_id: String,
    pub observed_at_unix_ms: u128,
    pub kind: String,
    pub source: SourceDescriptor,
    pub payload: Value,
    pub metadata: Value,
}

impl FormaEdgeEvent {
    pub fn new(kind: impl Into<String>, source: SourceDescriptor, payload: Value) -> Self {
        let observed_at_unix_ms = unix_time_millis();
        Self {
            schema_version: 1,
            event_id: next_event_id(observed_at_unix_ms),
            observed_at_unix_ms,
            kind: kind.into(),
            source,
            payload,
            metadata: json!({}),
        }
    }

    pub fn with_metadata(mut self, metadata: Value) -> Self {
        self.metadata = metadata;
        self
    }
}

pub fn parse_json_payload(raw: &str) -> Result<Value, serde_json::Error> {
    serde_json::from_str(raw)
}

pub fn event_to_json_line(event: &FormaEdgeEvent) -> Result<String, serde_json::Error> {
    serde_json::to_string(event)
}

pub fn write_event_jsonl(
    mut writer: impl Write,
    event: &FormaEdgeEvent,
) -> Result<(), EdgeError> {
    writeln!(writer, "{}", event_to_json_line(event)?)?;
    Ok(())
}

pub fn stream_stdin_as_events(
    reader: impl BufRead,
    mut writer: impl Write,
    source: SourceDescriptor,
    kind: &str,
) -> Result<u64, EdgeError> {
    let mut count = 0;
    for line in reader.lines() {
        let line = line?;
        let event = FormaEdgeEvent::new(kind, source.clone(), json!({ "line": line }));
        write_event_jsonl(&mut writer, &event)?;
        count += 1;
    }
    Ok(count)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct OllamaChatStreamRequest {
    pub model: String,
    pub prompt: String,
    pub system: Option<String>,
    pub options: Option<Value>,
    pub keep_alive: Option<Value>,
}

impl Default for OllamaChatStreamRequest {
    fn default() -> Self {
        Self {
            model: OllamaSourceConfig::default().default_model,
            prompt: "Say hello from Forma Edge.".to_string(),
            system: None,
            options: None,
            keep_alive: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OllamaStreamSummary {
    pub model: String,
    pub chunk_count: u64,
    pub done: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct LlamaCppChatStreamRequest {
    pub model: String,
    pub prompt: String,
    pub system: Option<String>,
    pub temperature: Option<f64>,
    pub max_tokens: Option<u64>,
}

impl Default for LlamaCppChatStreamRequest {
    fn default() -> Self {
        Self {
            model: LlamaCppSourceConfig::default().default_model,
            prompt: "Say hello from Forma Edge.".to_string(),
            system: None,
            temperature: None,
            max_tokens: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LlamaCppStreamSummary {
    pub model: String,
    pub chunk_count: u64,
    pub done: bool,
}

#[derive(Debug)]
pub struct AgentStreamWriter<W: Write> {
    pub agent_name: String,
    pub writer: W,
}

impl<W: Write> AgentStreamWriter<W> {
    pub fn new(agent_name: impl Into<String>, writer: W) -> Self {
        Self {
            agent_name: agent_name.into(),
            writer,
        }
    }
}

#[derive(Debug, Clone)]
pub struct LiveTcpStreamHub {
    inner: Arc<Mutex<LiveTcpStreamInner>>,
}

#[derive(Debug)]
struct LiveTcpStreamInner {
    clients: Vec<TcpStream>,
    replay: VecDeque<Vec<u8>>,
    replay_limit: usize,
}

impl LiveTcpStreamHub {
    pub fn bind(addr: &str, replay_limit: usize) -> Result<(Self, SocketAddr), EdgeError> {
        let listener = TcpListener::bind(addr)?;
        let local_addr = listener.local_addr()?;
        listener.set_nonblocking(true)?;
        let hub = Self {
            inner: Arc::new(Mutex::new(LiveTcpStreamInner {
                clients: Vec::new(),
                replay: VecDeque::new(),
                replay_limit,
            })),
        };
        let accept_hub = hub.clone();
        thread::spawn(move || accept_live_tcp_clients(listener, accept_hub));
        Ok((hub, local_addr))
    }

    pub fn client_count(&self) -> usize {
        self.inner
            .lock()
            .map(|inner| inner.clients.len())
            .unwrap_or_default()
    }

    pub fn wait_for_clients(&self, min_clients: usize, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        loop {
            if self.client_count() >= min_clients {
                return true;
            }
            if Instant::now() >= deadline {
                return false;
            }
            thread::sleep(Duration::from_millis(25));
        }
    }
}

impl Write for LiveTcpStreamHub {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        if buffer.is_empty() {
            return Ok(0);
        }
        let mut inner = lock_live_stream_inner(&self.inner)?;
        if inner.replay_limit > 0 {
            inner.replay.push_back(buffer.to_vec());
            while inner.replay.len() > inner.replay_limit {
                inner.replay.pop_front();
            }
        }

        let mut kept_clients = Vec::new();
        for mut client in inner.clients.drain(..) {
            match client.write_all(buffer).and_then(|_| client.flush()) {
                Ok(()) => kept_clients.push(client),
                Err(error) if is_disconnect_error(&error) => {}
                Err(error) => return Err(error),
            }
        }
        inner.clients = kept_clients;
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        let mut inner = lock_live_stream_inner(&self.inner)?;
        let mut kept_clients = Vec::new();
        for mut client in inner.clients.drain(..) {
            match client.flush() {
                Ok(()) => kept_clients.push(client),
                Err(error) if is_disconnect_error(&error) => {}
                Err(error) => return Err(error),
            }
        }
        inner.clients = kept_clients;
        Ok(())
    }
}

fn accept_live_tcp_clients(listener: TcpListener, hub: LiveTcpStreamHub) {
    loop {
        match listener.accept() {
            Ok((mut client, _addr)) => {
                let _ = client.set_nodelay(true);
                let _ = client.set_write_timeout(Some(Duration::from_millis(250)));
                let replay = match hub.inner.lock() {
                    Ok(inner) => inner.replay.iter().cloned().collect::<Vec<_>>(),
                    Err(_) => return,
                };
                if replay
                    .iter()
                    .try_for_each(|frame| client.write_all(frame))
                    .and_then(|_| client.flush())
                    .is_err()
                {
                    continue;
                }
                if let Ok(mut inner) = hub.inner.lock() {
                    inner.clients.push(client);
                } else {
                    return;
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(25));
            }
            Err(_) => return,
        }
    }
}

fn lock_live_stream_inner(
    inner: &Arc<Mutex<LiveTcpStreamInner>>,
) -> io::Result<std::sync::MutexGuard<'_, LiveTcpStreamInner>> {
    inner
        .lock()
        .map_err(|_| io::Error::other("live TCP stream hub lock poisoned"))
}

fn is_disconnect_error(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        io::ErrorKind::BrokenPipe
            | io::ErrorKind::ConnectionReset
            | io::ErrorKind::ConnectionAborted
            | io::ErrorKind::TimedOut
    )
}

#[derive(Debug, Clone)]
pub struct LocalSpacebaseStream {
    config: SpacebaseLocalConfig,
    stream_id: String,
}

impl LocalSpacebaseStream {
    pub fn new(config: SpacebaseLocalConfig, stream_id: impl Into<String>) -> Self {
        Self {
            config,
            stream_id: stream_id.into(),
        }
    }

    pub fn from_config(config: &SpacebaseLocalConfig, stream_id: Option<&str>) -> Self {
        Self::new(
            config.clone(),
            stream_id.unwrap_or(&config.default_stream).to_string(),
        )
    }

    pub fn stream_id(&self) -> &str {
        &self.stream_id
    }

    pub fn stream_dir(&self) -> PathBuf {
        self.config.root_dir.join("streams").join(&self.stream_id)
    }

    pub fn events_path(&self) -> PathBuf {
        self.stream_dir().join(&self.config.events_file_name)
    }

    pub fn agents_dir(&self) -> PathBuf {
        self.stream_dir().join(&self.config.agents_dir_name)
    }

    pub fn agent_path(&self, agent_name: &str) -> PathBuf {
        self.agents_dir().join(format!("{agent_name}.jsonl"))
    }

    pub fn manifest_path(&self) -> PathBuf {
        self.stream_dir().join("manifest.json")
    }

    pub fn ensure(&self, agents: &[SpacebaseAgentConfig]) -> Result<(), EdgeError> {
        fs::create_dir_all(self.agents_dir())?;
        let manifest = json!({
            "schema_version": 1,
            "stream_id": self.stream_id,
            "events_path": self.events_path(),
            "agents_dir": self.agents_dir(),
            "agents": agents,
        });
        fs::write(self.manifest_path(), serde_json::to_vec_pretty(&manifest)?)?;
        Ok(())
    }

    pub fn open_append_writer(path: impl AsRef<Path>) -> Result<Box<dyn Write>, EdgeError> {
        if let Some(parent) = path
            .as_ref()
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            fs::create_dir_all(parent)?;
        }
        let file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)?;
        Ok(Box::new(file))
    }

    pub fn open_agent_outputs(
        &self,
        agents: &[SpacebaseAgentConfig],
        include_event_log: bool,
    ) -> Result<Vec<AgentStreamWriter<Box<dyn Write>>>, EdgeError> {
        if !self.config.enabled {
            return Err(EdgeError::Provider(
                "local Spacebase stream store is disabled by config".to_string(),
            ));
        }
        self.ensure(agents)?;
        let mut outputs = Vec::new();
        for agent in agents {
            outputs.push(AgentStreamWriter::new(
                agent.name.clone(),
                Self::open_append_writer(self.agent_path(&agent.name))?,
            ));
        }
        if include_event_log {
            outputs.push(AgentStreamWriter::new(
                "spacebase.events",
                Self::open_append_writer(self.events_path())?,
            ));
        }
        Ok(outputs)
    }

    pub fn read_events(
        &self,
        agent_name: Option<&str>,
        limit: Option<usize>,
    ) -> Result<Vec<Value>, EdgeError> {
        let path = match agent_name {
            Some(agent_name) => self.agent_path(agent_name),
            None => self.events_path(),
        };
        let raw = match fs::read_to_string(&path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => return Err(error.into()),
        };
        let mut events = Vec::new();
        for line in raw.lines().filter(|line| !line.trim().is_empty()) {
            events.push(serde_json::from_str(line)?);
        }
        if let Some(limit) = limit {
            let start = events.len().saturating_sub(limit);
            Ok(events.split_off(start))
        } else {
            Ok(events)
        }
    }
}

pub fn stream_ollama_chat_to_agents<W: Write>(
    config: &EdgeConfig,
    request: OllamaChatStreamRequest,
    outputs: &mut [AgentStreamWriter<W>],
) -> Result<OllamaStreamSummary, EdgeError> {
    if !config.sources.ollama.enabled {
        return Err(EdgeError::Provider(
            "ollama source is disabled by config".to_string(),
        ));
    }
    if outputs.is_empty() {
        return Err(EdgeError::Provider(
            "ollama stream requires at least one agent output".to_string(),
        ));
    }

    let endpoint = ollama_chat_endpoint(&config.sources.ollama.base_url);
    let body = ollama_chat_request_body(&request);
    let response = reqwest::blocking::Client::new()
        .post(endpoint)
        .json(&body)
        .send()?;
    let status = response.status();
    if !status.is_success() {
        let message = response
            .text()
            .unwrap_or_else(|error| format!("failed to read provider error body: {error}"));
        return Err(EdgeError::Provider(format!(
            "ollama chat stream failed with HTTP {status}: {message}"
        )));
    }

    let mut chunk_count = 0;
    let mut done = false;
    let reader = io::BufReader::new(response);
    for line in reader.lines() {
        let line = line?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let chunk: Value = serde_json::from_str(trimmed)?;
        chunk_count += 1;
        done = chunk.get("done").and_then(Value::as_bool).unwrap_or(false);
        let event = ollama_stream_chunk_event(config, &request.model, chunk_count, chunk);
        fanout_event_to_agents(outputs, &event)?;
    }

    Ok(OllamaStreamSummary {
        model: request.model,
        chunk_count,
        done,
    })
}

pub fn stream_llama_cpp_chat_to_agents<W: Write>(
    config: &EdgeConfig,
    request: LlamaCppChatStreamRequest,
    outputs: &mut [AgentStreamWriter<W>],
) -> Result<LlamaCppStreamSummary, EdgeError> {
    if !config.sources.llama_cpp.enabled {
        return Err(EdgeError::Provider(
            "llama.cpp source is disabled by config".to_string(),
        ));
    }
    if outputs.is_empty() {
        return Err(EdgeError::Provider(
            "llama.cpp stream requires at least one agent output".to_string(),
        ));
    }

    let endpoint = llama_cpp_chat_endpoint(&config.sources.llama_cpp.base_url);
    let body = llama_cpp_chat_request_body(&request);
    let response = reqwest::blocking::Client::new()
        .post(endpoint)
        .json(&body)
        .send()?;
    let status = response.status();
    if !status.is_success() {
        let message = response
            .text()
            .unwrap_or_else(|error| format!("failed to read provider error body: {error}"));
        return Err(EdgeError::Provider(format!(
            "llama.cpp chat stream failed with HTTP {status}: {message}"
        )));
    }

    let mut chunk_count = 0;
    let mut done = false;
    let reader = io::BufReader::new(response);
    for line in reader.lines() {
        let line = line?;
        let Some(frame) = parse_sse_data_line(&line) else {
            continue;
        };
        if frame == "[DONE]" {
            done = true;
            let event = llama_cpp_stream_done_event(config, &request.model, chunk_count + 1);
            fanout_event_to_agents(outputs, &event)?;
            continue;
        }
        let chunk: Value = serde_json::from_str(frame)?;
        chunk_count += 1;
        let event = llama_cpp_stream_chunk_event(config, &request.model, chunk_count, chunk);
        done = event
            .payload
            .get("done")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        fanout_event_to_agents(outputs, &event)?;
    }

    Ok(LlamaCppStreamSummary {
        model: request.model,
        chunk_count,
        done,
    })
}

pub fn fanout_event_to_agents<W: Write>(
    outputs: &mut [AgentStreamWriter<W>],
    event: &FormaEdgeEvent,
) -> Result<(), EdgeError> {
    for output in outputs {
        let routed = event.clone().with_metadata(merge_metadata_field(
            &event.metadata,
            "agent_route",
            json!({
                "agent_name": output.agent_name,
            }),
        ));
        write_event_jsonl(&mut output.writer, &routed)?;
    }
    Ok(())
}

pub fn ollama_stream_chunk_event(
    config: &EdgeConfig,
    model: &str,
    sequence: u64,
    chunk: Value,
) -> FormaEdgeEvent {
    let content = chunk
        .pointer("/message/content")
        .or_else(|| chunk.get("response"))
        .cloned()
        .unwrap_or_else(|| json!(""));
    let done = chunk.get("done").and_then(Value::as_bool).unwrap_or(false);
    let source = SourceDescriptor::new("ollama", "llm.stream", &config.sources.ollama.name)
        .with_uri(ollama_chat_endpoint(&config.sources.ollama.base_url));

    FormaEdgeEvent::new(
        "llm.ollama.chat.chunk",
        source,
        json!({
            "model": model,
            "sequence": sequence,
            "content": content,
            "done": done,
            "done_reason": chunk.get("done_reason").cloned(),
            "raw": chunk,
        }),
    )
    .with_metadata(json!({
        "system": &config.system,
        "provider": "ollama",
        "stream": true,
    }))
}

pub fn llama_cpp_stream_chunk_event(
    config: &EdgeConfig,
    model: &str,
    sequence: u64,
    chunk: Value,
) -> FormaEdgeEvent {
    let content = chunk
        .pointer("/choices/0/delta/content")
        .or_else(|| chunk.pointer("/choices/0/message/content"))
        .or_else(|| chunk.pointer("/choices/0/text"))
        .cloned()
        .unwrap_or_else(|| json!(""));
    let finish_reason = chunk.pointer("/choices/0/finish_reason").cloned();
    let done = !finish_reason.as_ref().map(Value::is_null).unwrap_or(true);
    let source = SourceDescriptor::new("llama.cpp", "llm.stream", &config.sources.llama_cpp.name)
        .with_uri(llama_cpp_chat_endpoint(&config.sources.llama_cpp.base_url));

    FormaEdgeEvent::new(
        "llm.llama_cpp.chat.chunk",
        source,
        json!({
            "model": model,
            "sequence": sequence,
            "content": content,
            "done": done,
            "finish_reason": finish_reason,
            "raw": chunk,
        }),
    )
    .with_metadata(json!({
        "system": &config.system,
        "provider": "llama.cpp",
        "stream": true,
    }))
}

pub fn llama_cpp_stream_done_event(
    config: &EdgeConfig,
    model: &str,
    sequence: u64,
) -> FormaEdgeEvent {
    let source = SourceDescriptor::new("llama.cpp", "llm.stream", &config.sources.llama_cpp.name)
        .with_uri(llama_cpp_chat_endpoint(&config.sources.llama_cpp.base_url));
    FormaEdgeEvent::new(
        "llm.llama_cpp.chat.done",
        source,
        json!({
            "model": model,
            "sequence": sequence,
            "content": "",
            "done": true,
            "finish_reason": "done",
        }),
    )
    .with_metadata(json!({
        "system": &config.system,
        "provider": "llama.cpp",
        "stream": true,
    }))
}

fn ollama_chat_endpoint(base_url: &str) -> String {
    format!("{}/api/chat", base_url.trim_end_matches('/'))
}

fn llama_cpp_chat_endpoint(base_url: &str) -> String {
    format!("{}/v1/chat/completions", base_url.trim_end_matches('/'))
}

fn ollama_chat_request_body(request: &OllamaChatStreamRequest) -> Value {
    let mut messages = Vec::new();
    if let Some(system) = &request.system {
        messages.push(json!({
            "role": "system",
            "content": system,
        }));
    }
    messages.push(json!({
        "role": "user",
        "content": request.prompt,
    }));

    let mut body = serde_json::Map::new();
    body.insert("model".to_string(), json!(request.model));
    body.insert("messages".to_string(), Value::Array(messages));
    body.insert("stream".to_string(), json!(true));
    if let Some(options) = &request.options {
        body.insert("options".to_string(), options.clone());
    }
    if let Some(keep_alive) = &request.keep_alive {
        body.insert("keep_alive".to_string(), keep_alive.clone());
    }
    Value::Object(body)
}

fn llama_cpp_chat_request_body(request: &LlamaCppChatStreamRequest) -> Value {
    let mut messages = Vec::new();
    if let Some(system) = &request.system {
        messages.push(json!({
            "role": "system",
            "content": system,
        }));
    }
    messages.push(json!({
        "role": "user",
        "content": request.prompt,
    }));

    let mut body = serde_json::Map::new();
    body.insert("model".to_string(), json!(request.model));
    body.insert("messages".to_string(), Value::Array(messages));
    body.insert("stream".to_string(), json!(true));
    if let Some(temperature) = request.temperature {
        body.insert("temperature".to_string(), json!(temperature));
    }
    if let Some(max_tokens) = request.max_tokens {
        body.insert("max_tokens".to_string(), json!(max_tokens));
    }
    Value::Object(body)
}

fn parse_sse_data_line(line: &str) -> Option<&str> {
    let trimmed = line.trim();
    let data = trimmed.strip_prefix("data:")?;
    Some(data.trim())
}

fn merge_metadata_field(metadata: &Value, key: &str, value: Value) -> Value {
    let mut object = metadata.as_object().cloned().unwrap_or_default();
    object.insert(key.to_string(), value);
    Value::Object(object)
}

pub fn linux_snapshot_event(source_name: &str) -> FormaEdgeEvent {
    linux_snapshot_event_from_config(&LinuxSourceConfig {
        name: source_name.to_string(),
        ..LinuxSourceConfig::default()
    })
}

pub fn linux_snapshot_event_from_config(config: &LinuxSourceConfig) -> FormaEdgeEvent {
    let source =
        SourceDescriptor::new("blueprint-edge", "linux", &config.name).with_uri("linux://proc");
    let mut payload = serde_json::Map::new();

    if config.include_os_release {
        payload.insert("os_release".to_string(), read_os_release());
    }

    if config.include_proc {
        payload.insert(
            "kernel".to_string(),
            json!({
                "ostype": read_trimmed("/proc/sys/kernel/ostype"),
                "osrelease": read_trimmed("/proc/sys/kernel/osrelease"),
                "hostname": read_trimmed("/proc/sys/kernel/hostname"),
            }),
        );
        payload.insert(
            "proc".to_string(),
            json!({
                "uptime": read_trimmed("/proc/uptime"),
                "loadavg": read_trimmed("/proc/loadavg"),
            }),
        );
    }

    FormaEdgeEvent::new("linux.snapshot", source, Value::Object(payload))
}

#[derive(Debug, Deserialize)]
struct McpJsonRpcRequest {
    id: Option<Value>,
    method: String,
    params: Option<Value>,
}

pub fn handle_mcp_request(config: &EdgeConfig, request: Value) -> Option<Value> {
    let parsed: McpJsonRpcRequest = match serde_json::from_value(request) {
        Ok(parsed) => parsed,
        Err(error) => {
            return Some(jsonrpc_error(
                None,
                -32600,
                format!("invalid JSON-RPC request: {error}"),
            ));
        }
    };

    if parsed.id.is_none() && parsed.method.starts_with("notifications/") {
        return None;
    }

    let id = parsed.id.clone();
    let response = match parsed.method.as_str() {
        "initialize" => jsonrpc_result(
            id,
            json!({
                "protocolVersion": config.mcp.protocol_version,
                "serverInfo": {
                    "name": config.mcp.server_name,
                    "version": config.mcp.server_version,
                },
                "capabilities": {
                    "tools": {
                        "listChanged": false,
                    },
                },
            }),
        ),
        "ping" => jsonrpc_result(id, json!({})),
        "tools/list" => jsonrpc_result(id, json!({ "tools": mcp_tools() })),
        "tools/call" => handle_mcp_tool_call(config, id, parsed.params.as_ref()),
        method => jsonrpc_error(id, -32601, format!("method not found: {method}")),
    };

    Some(response)
}

pub fn serve_mcp_stdio(
    config: EdgeConfig,
    mut reader: impl BufRead,
    mut writer: impl Write,
) -> Result<(), EdgeError> {
    while let Some(request) = read_mcp_message(&mut reader)? {
        if let Some(response) = handle_mcp_request(&config, request) {
            write_mcp_message(&mut writer, &response)?;
        }
    }
    Ok(())
}

pub fn read_mcp_message(reader: &mut impl BufRead) -> Result<Option<Value>, EdgeError> {
    let mut content_length = None;

    loop {
        let mut line = String::new();
        let bytes_read = reader.read_line(&mut line)?;
        if bytes_read == 0 {
            if content_length.is_none() {
                return Ok(None);
            }
            return Err(EdgeError::Protocol(
                "unexpected EOF while reading MCP headers".to_string(),
            ));
        }

        let header = line.trim_end_matches(['\r', '\n']);
        if header.is_empty() {
            break;
        }

        let Some((name, value)) = header.split_once(':') else {
            continue;
        };
        if name.eq_ignore_ascii_case("content-length") {
            let parsed = value.trim().parse::<usize>().map_err(|error| {
                EdgeError::Protocol(format!("invalid Content-Length header: {error}"))
            })?;
            content_length = Some(parsed);
        }
    }

    let Some(content_length) = content_length else {
        return Err(EdgeError::Protocol(
            "missing Content-Length header".to_string(),
        ));
    };
    let mut body = vec![0; content_length];
    reader.read_exact(&mut body)?;
    Ok(Some(serde_json::from_slice(&body)?))
}

pub fn write_mcp_message(mut writer: impl Write, response: &Value) -> Result<(), EdgeError> {
    let body = serde_json::to_vec(response)?;
    write!(writer, "Content-Length: {}\r\n\r\n", body.len())?;
    writer.write_all(&body)?;
    writer.flush()?;
    Ok(())
}

fn handle_mcp_tool_call(config: &EdgeConfig, id: Option<Value>, params: Option<&Value>) -> Value {
    let Some(name) = params
        .and_then(|params| params.get("name"))
        .and_then(Value::as_str)
    else {
        return jsonrpc_error(id, -32602, "tools/call requires params.name");
    };

    let arguments = params
        .and_then(|params| params.get("arguments"))
        .cloned()
        .unwrap_or_else(|| json!({}));

    match name {
        "edge.config.get" => jsonrpc_result(
            id,
            mcp_tool_result(json!({
                "config": config,
                "sources": configured_sources(config),
            })),
        ),
        "edge.sources.list" => jsonrpc_result(
            id,
            mcp_tool_result(json!({
                "sources": configured_sources(config),
            })),
        ),
        "edge.emit" => jsonrpc_result(
            id,
            mcp_tool_result(json!(mcp_emit_event(config, &arguments))),
        ),
        "edge.linux.snapshot" => {
            if !config.sources.linux.enabled {
                return jsonrpc_error(id, -32000, "linux source is disabled by config");
            }
            jsonrpc_result(id, mcp_tool_result(json!(mcp_linux_snapshot_event(config))))
        }
        "edge.sources.poll" => match mcp_poll_sources(config, &arguments) {
            Ok(events) => jsonrpc_result(id, mcp_tool_result(json!({ "events": events }))),
            Err(message) => jsonrpc_error(id, -32602, message),
        },
        "edge.spacebase.agents.list" => jsonrpc_result(
            id,
            mcp_tool_result(json!({
                "agents": config.spacebase.agents,
            })),
        ),
        "edge.spacebase.stream.read" => match mcp_read_spacebase_stream(config, &arguments) {
            Ok(events) => jsonrpc_result(id, mcp_tool_result(json!({ "events": events }))),
            Err(error) => jsonrpc_error(id, -32602, error.to_string()),
        },
        "edge.spacebase.event.write" => match mcp_write_spacebase_event(config, &arguments) {
            Ok(event) => jsonrpc_result(id, mcp_tool_result(json!({ "event": event }))),
            Err(error) => jsonrpc_error(id, -32602, error.to_string()),
        },
        unknown => jsonrpc_error(id, -32602, format!("unknown tool: {unknown}")),
    }
}

fn mcp_emit_event(config: &EdgeConfig, arguments: &Value) -> FormaEdgeEvent {
    let source_type = string_argument(arguments, "source_type", "manual");
    let name = string_argument(arguments, "name", "manual");
    let kind = string_argument(arguments, "kind", "source.event");
    let provider = string_argument(arguments, "provider", "blueprint-edge");
    let payload = arguments
        .get("payload")
        .cloned()
        .unwrap_or_else(|| json!({}));

    FormaEdgeEvent::new(
        kind,
        SourceDescriptor::new(provider, source_type, name),
        payload,
    )
    .with_metadata(json!({
        "tool": "edge.emit",
        "system": &config.system,
        "input_metadata": arguments.get("metadata").cloned().unwrap_or_else(|| json!({})),
    }))
}

fn mcp_linux_snapshot_event(config: &EdgeConfig) -> FormaEdgeEvent {
    linux_snapshot_event_from_config(&config.sources.linux).with_metadata(json!({
        "tool": "edge.linux.snapshot",
        "collection": "best_effort",
        "platform": "linux",
        "system": &config.system,
    }))
}

fn mcp_poll_sources(
    config: &EdgeConfig,
    arguments: &Value,
) -> Result<Vec<FormaEdgeEvent>, String> {
    let source_id = arguments
        .get("source_id")
        .and_then(Value::as_str)
        .map(str::to_string);
    let limit = arguments
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(25)
        .max(1) as usize;

    let mut events = Vec::new();
    match source_id.as_deref() {
        None | Some("linux") => {
            if config.sources.linux.enabled {
                events.push(mcp_linux_snapshot_event(config));
            } else if source_id.as_deref() == Some("linux") {
                return Err("linux source is disabled by config".to_string());
            }
        }
        Some("manual" | "stdin") => {}
        Some(unknown) => return Err(format!("unknown source_id: {unknown}")),
    }

    events.truncate(limit);
    Ok(events)
}

fn mcp_read_spacebase_stream(
    config: &EdgeConfig,
    arguments: &Value,
) -> Result<Vec<Value>, EdgeError> {
    let stream_id = arguments
        .get("stream_id")
        .and_then(Value::as_str)
        .unwrap_or(&config.spacebase.default_stream);
    let agent = arguments.get("agent").and_then(Value::as_str);
    let limit = arguments
        .get("limit")
        .and_then(Value::as_u64)
        .map(|value| value as usize);
    LocalSpacebaseStream::from_config(&config.spacebase, Some(stream_id)).read_events(agent, limit)
}

fn mcp_write_spacebase_event(
    config: &EdgeConfig,
    arguments: &Value,
) -> Result<FormaEdgeEvent, EdgeError> {
    let stream_id = arguments
        .get("stream_id")
        .and_then(Value::as_str)
        .unwrap_or(&config.spacebase.default_stream);
    let agent = arguments.get("agent").and_then(Value::as_str);
    let kind = string_argument(arguments, "kind", "spacebase.event");
    let payload = arguments
        .get("payload")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let event = FormaEdgeEvent::new(
        kind,
        SourceDescriptor::new("spacebase.local", "stream.store", stream_id),
        payload,
    )
    .with_metadata(json!({
        "system": &config.system,
        "stream_id": stream_id,
        "agent": agent,
    }));

    let stream = LocalSpacebaseStream::from_config(&config.spacebase, Some(stream_id));
    stream.ensure(&config.spacebase.agents)?;
    let path = match agent {
        Some(agent) => stream.agent_path(agent),
        None => stream.events_path(),
    };
    let mut writer = LocalSpacebaseStream::open_append_writer(path)?;
    write_event_jsonl(&mut writer, &event)?;
    Ok(event)
}

fn string_argument(arguments: &Value, key: &str, default: &str) -> String {
    arguments
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or(default)
        .to_string()
}

fn mcp_tools() -> Value {
    json!([
        {
            "name": "edge.config.get",
            "description": "Return the loaded Forma Edge config and registered sources.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.sources.list",
            "description": "List configured source registrations.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.emit",
            "description": "Create one edge event from an MCP tool call.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": { "type": "string" },
                    "provider": { "type": "string" },
                    "source_type": { "type": "string" },
                    "name": { "type": "string" },
                    "payload": { "type": "object" },
                    "metadata": { "type": "object" },
                },
                "additionalProperties": true,
            },
        },
        {
            "name": "edge.linux.snapshot",
            "description": "Capture one Linux host snapshot event.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.sources.poll",
            "description": "Poll configured pollable sources once.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "string",
                        "enum": ["linux", "manual", "stdin"],
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.spacebase.agents.list",
            "description": "List local Spacebase stream agents configured for consuming provider output.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.spacebase.stream.read",
            "description": "Read JSONL events from a local Spacebase stream or one agent's stream file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "stream_id": { "type": "string" },
                    "agent": { "type": "string" },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "additionalProperties": false,
            },
        },
        {
            "name": "edge.spacebase.event.write",
            "description": "Append one event into a local Spacebase stream or one agent's stream file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "stream_id": { "type": "string" },
                    "agent": { "type": "string" },
                    "kind": { "type": "string" },
                    "payload": { "type": "object" },
                },
                "additionalProperties": true,
            },
        },
    ])
}

fn mcp_tool_result(result: Value) -> Value {
    let text = serde_json::to_string_pretty(&result).unwrap_or_else(|_| result.to_string());
    json!({
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "structuredContent": result,
    })
}

fn jsonrpc_result(id: Option<Value>, result: Value) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
    })
}

fn jsonrpc_error(id: Option<Value>, code: i64, message: impl Into<String>) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "error": {
            "code": code,
            "message": message.into(),
        },
    })
}

pub fn read_os_release() -> Value {
    let path = Path::new("/etc/os-release");
    let Ok(raw) = fs::read_to_string(path) else {
        return json!({});
    };
    let mut items = serde_json::Map::new();
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((key, value)) = trimmed.split_once('=') else {
            continue;
        };
        items.insert(
            key.to_string(),
            Value::String(unquote_os_release_value(value)),
        );
    }
    Value::Object(items)
}

pub fn read_trimmed(path: impl AsRef<Path>) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn unquote_os_release_value(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.len() >= 2 && trimmed.starts_with('"') && trimmed.ends_with('"') {
        trimmed[1..trimmed.len() - 1].replace("\\\"", "\"")
    } else {
        trimmed.to_string()
    }
}

fn unix_time_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

fn next_event_id(observed_at_unix_ms: u128) -> String {
    let sequence = EVENT_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("edge-{observed_at_unix_ms}-{}-{sequence}", process::id())
}

#[derive(Debug)]
pub enum EdgeError {
    Io(io::Error),
    Json(serde_json::Error),
    Http(reqwest::Error),
    Toml(toml::de::Error),
    Protocol(String),
    Provider(String),
}

impl std::fmt::Display for EdgeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EdgeError::Io(error) => write!(formatter, "io error: {error}"),
            EdgeError::Json(error) => write!(formatter, "json error: {error}"),
            EdgeError::Http(error) => write!(formatter, "http error: {error}"),
            EdgeError::Toml(error) => write!(formatter, "config TOML error: {error}"),
            EdgeError::Protocol(message) => write!(formatter, "protocol error: {message}"),
            EdgeError::Provider(message) => write!(formatter, "provider error: {message}"),
        }
    }
}

impl std::error::Error for EdgeError {}

impl From<io::Error> for EdgeError {
    fn from(value: io::Error) -> Self {
        EdgeError::Io(value)
    }
}

impl From<serde_json::Error> for EdgeError {
    fn from(value: serde_json::Error) -> Self {
        EdgeError::Json(value)
    }
}

impl From<reqwest::Error> for EdgeError {
    fn from(value: reqwest::Error) -> Self {
        EdgeError::Http(value)
    }
}

impl From<toml::de::Error> for EdgeError {
    fn from(value: toml::de::Error) -> Self {
        EdgeError::Toml(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn event_serializes_as_json_line() {
        let event = FormaEdgeEvent::new(
            "source.sample",
            SourceDescriptor::new("unit", "manual", "demo"),
            json!({"ok": true}),
        );

        let line = event_to_json_line(&event).expect("event should serialize");
        let parsed: Value = serde_json::from_str(&line).expect("jsonl line should parse");

        assert_eq!(parsed["schema_version"], 1);
        assert_eq!(parsed["kind"], "source.sample");
        assert_eq!(parsed["source"]["name"], "demo");
        assert_eq!(parsed["payload"]["ok"], true);
    }

    #[test]
    fn stdin_stream_creates_one_event_per_line() {
        let input = Cursor::new("alpha\nbeta\n");
        let mut output = Vec::new();

        let count = stream_stdin_as_events(
            input,
            &mut output,
            SourceDescriptor::new("unit", "stdin", "lines"),
            "stdin.line",
        )
        .expect("stdin stream should succeed");

        let text = String::from_utf8(output).expect("jsonl should be utf8");
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(count, 2);
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("\"line\":\"alpha\""));
        assert!(lines[1].contains("\"line\":\"beta\""));
    }

    #[test]
    fn config_loads_registered_sources() {
        let config: EdgeConfig = toml::from_str(
            r#"
            [system]
            name = "unit-edge"
            instance_id = "unit-1"
            environment = "test"

            [sources.manual]
            enabled = true

            [sources.stdin]
            enabled = false
            name = "disabled-stdin"

            [sources.linux]
            enabled = true
            name = "unit-linux"
            include_proc = false
            include_os_release = true
            "#,
        )
        .expect("config should parse");

        let sources = configured_sources(&config);
        assert_eq!(config.system.name, "unit-edge");
        assert_eq!(sources.len(), 6);
        assert_eq!(sources[1].id, "stdin");
        assert!(!sources[1].enabled);
        assert_eq!(sources[2].name, "unit-linux");
        assert_eq!(sources[3].id, "ollama");
        assert_eq!(sources[4].id, "llama_cpp");
        assert_eq!(sources[5].id, "spacebase.local");
    }

    #[test]
    fn runtime_owns_config_and_sources() {
        let runtime = EdgeRuntime::default();
        assert_eq!(runtime.config().mcp.server_name, "blueprint-edge");
        assert!(runtime
            .sources()
            .iter()
            .any(|source| source.id == "linux" && source.pollable));
    }

    #[test]
    fn mcp_lists_tools() {
        let response = handle_mcp_request(
            &EdgeConfig::default(),
            json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            }),
        )
        .expect("tools/list should produce a response");

        assert_eq!(response["jsonrpc"], "2.0");
        assert_eq!(response["id"], 1);
        assert!(response["result"]["tools"]
            .as_array()
            .expect("tools should be an array")
            .iter()
            .any(|tool| tool["name"] == "edge.sources.poll"));
    }

    #[test]
    fn mcp_stdio_handles_tool_call_frame() {
        let request = json!({
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "edge.emit",
                "arguments": {
                    "kind": "unit.event",
                    "source_type": "unit",
                    "name": "mcp-test",
                    "payload": {
                        "ok": true
                    }
                }
            }
        });
        let mut input = Vec::new();
        write_mcp_message(&mut input, &request).expect("request frame should serialize");

        let mut output = Vec::new();
        serve_mcp_stdio(EdgeConfig::default(), Cursor::new(input), &mut output)
            .expect("mcp server should handle one framed request");

        let mut cursor = Cursor::new(output);
        let response = read_mcp_message(&mut cursor)
            .expect("response frame should parse")
            .expect("response should be present");
        let event = &response["result"]["structuredContent"];

        assert_eq!(response["id"], "call-1");
        assert_eq!(event["kind"], "unit.event");
        assert_eq!(event["source"]["name"], "mcp-test");
        assert_eq!(event["payload"]["ok"], true);
    }

    #[test]
    fn ollama_chunk_becomes_edge_event() {
        let event = ollama_stream_chunk_event(
            &EdgeConfig::default(),
            "qwen3:0.6b",
            7,
            json!({
                "model": "qwen3:0.6b",
                "message": {
                    "role": "assistant",
                    "content": "blue"
                },
                "done": false
            }),
        );

        assert_eq!(event.kind, "llm.ollama.chat.chunk");
        assert_eq!(event.source.provider, "ollama");
        assert_eq!(event.payload["model"], "qwen3:0.6b");
        assert_eq!(event.payload["sequence"], 7);
        assert_eq!(event.payload["content"], "blue");
        assert_eq!(event.payload["done"], false);
    }

    #[test]
    fn fanout_routes_event_to_each_agent_writer() {
        let event = FormaEdgeEvent::new(
            "unit.chunk",
            SourceDescriptor::new("unit", "llm.stream", "demo"),
            json!({"content": "hello"}),
        );
        let mut outputs = vec![
            AgentStreamWriter::new("planner", Vec::new()),
            AgentStreamWriter::new("critic", Vec::new()),
        ];

        fanout_event_to_agents(&mut outputs, &event).expect("fanout should write both outputs");

        let planner_text = String::from_utf8(outputs[0].writer.clone()).expect("utf8 jsonl");
        let critic_text = String::from_utf8(outputs[1].writer.clone()).expect("utf8 jsonl");
        let planner_event: Value =
            serde_json::from_str(planner_text.trim()).expect("planner event should parse");
        let critic_event: Value =
            serde_json::from_str(critic_text.trim()).expect("critic event should parse");

        assert_eq!(
            planner_event["metadata"]["agent_route"]["agent_name"],
            "planner"
        );
        assert_eq!(
            critic_event["metadata"]["agent_route"]["agent_name"],
            "critic"
        );
        assert_eq!(planner_event["payload"]["content"], "hello");
        assert_eq!(critic_event["payload"]["content"], "hello");
    }

    #[test]
    fn live_tcp_hub_replays_memory_events_to_listener() {
        let (hub, addr) = LiveTcpStreamHub::bind("127.0.0.1:0", 8).expect("live hub should bind");
        let event = FormaEdgeEvent::new(
            "unit.live",
            SourceDescriptor::new("unit", "live", "tcp"),
            json!({"content": "instant"}),
        );
        let mut outputs = vec![AgentStreamWriter::new("live.tcp", hub)];

        fanout_event_to_agents(&mut outputs, &event).expect("fanout should write to live hub");

        let client = TcpStream::connect(addr).expect("listener should connect");
        client
            .set_read_timeout(Some(Duration::from_secs(2)))
            .expect("read timeout should set");
        let mut reader = io::BufReader::new(client);
        let mut line = String::new();
        reader
            .read_line(&mut line)
            .expect("listener should receive replayed event");
        let received: Value = serde_json::from_str(line.trim()).expect("event should parse");

        assert_eq!(received["kind"], "unit.live");
        assert_eq!(received["payload"]["content"], "instant");
        assert_eq!(
            received["metadata"]["agent_route"]["agent_name"],
            "live.tcp"
        );
    }

    #[test]
    fn llama_cpp_sse_chunk_becomes_edge_event() {
        let sse = r#"data: {"choices":[{"delta":{"content":"blue"},"finish_reason":null}]}"#;
        let frame = parse_sse_data_line(sse).expect("sse frame should parse");
        let chunk: Value = serde_json::from_str(frame).expect("chunk should parse");
        let event = llama_cpp_stream_chunk_event(&EdgeConfig::default(), "local-model", 3, chunk);

        assert_eq!(event.kind, "llm.llama_cpp.chat.chunk");
        assert_eq!(event.source.provider, "llama.cpp");
        assert_eq!(event.payload["model"], "local-model");
        assert_eq!(event.payload["sequence"], 3);
        assert_eq!(event.payload["content"], "blue");
        assert_eq!(event.payload["done"], false);
    }

    #[test]
    fn local_spacebase_stream_writes_and_reads_agent_events() {
        let root = std::env::temp_dir().join(format!(
            "blueprint-edge-spacebase-test-{}",
            next_event_id(unix_time_millis())
        ));
        let config = SpacebaseLocalConfig {
            root_dir: root.clone(),
            default_stream: "unit-stream".to_string(),
            agents: vec![SpacebaseAgentConfig {
                name: "planner".to_string(),
                role: "plan".to_string(),
                source: "contra-mcp".to_string(),
                model: "unit-model".to_string(),
            }],
            ..SpacebaseLocalConfig::default()
        };
        let stream = LocalSpacebaseStream::from_config(&config, None);
        let mut outputs = stream
            .open_agent_outputs(&config.agents, true)
            .expect("spacebase outputs should open");
        let event = FormaEdgeEvent::new(
            "unit.stream",
            SourceDescriptor::new("unit", "stream", "spacebase"),
            json!({"content": "hello"}),
        );

        fanout_event_to_agents(&mut outputs, &event).expect("fanout should write");
        drop(outputs);

        let planner_events = stream
            .read_events(Some("planner"), Some(1))
            .expect("planner events should read");
        let log_events = stream
            .read_events(None, Some(1))
            .expect("event log should read");

        assert_eq!(planner_events.len(), 1);
        assert_eq!(log_events.len(), 1);
        assert_eq!(
            planner_events[0]["metadata"]["agent_route"]["agent_name"],
            "planner"
        );
        assert_eq!(
            log_events[0]["metadata"]["agent_route"]["agent_name"],
            "spacebase.events"
        );

        let _ = fs::remove_dir_all(root);
    }
}
