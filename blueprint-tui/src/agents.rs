use crate::blueprint::fetch_agent_mcp_context;
use crate::storage::{AgentMemoryStore, StoredMemoryTurn};
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const FILE_PREVIEW_LIMIT: usize = 16_000;
const AGENT_MEMORY_LIMIT: usize = 8;
pub const MASTER_AGENT_ID: &str = "blueprint.architect";
pub const MASTER_AGENT_NAME: &str = "Forma Architect";

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct LatticeCapability {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub description: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct AgentCard {
    pub agent_id: String,
    pub name: String,
    #[serde(default)]
    pub namespace: Option<String>,
    #[serde(default)]
    pub domain: String,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub capabilities: Vec<LatticeCapability>,
}

impl AgentCard {
    pub fn namespace_label(&self) -> &str {
        self.namespace.as_deref().unwrap_or(&self.agent_id)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputKind {
    Text,
    File { path: PathBuf, byte_len: usize },
}

#[derive(Debug, Clone)]
pub struct ChatInput {
    pub user_name: String,
    pub body: String,
    pub kind: InputKind,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OpenAiConfig {
    pub enabled: bool,
    pub api_key: Option<String>,
    pub model: String,
    pub fallback_model: String,
    pub base_url: String,
}

impl OpenAiConfig {
    pub fn offline() -> Self {
        Self {
            enabled: false,
            api_key: None,
            model: "gpt-4o-mini".to_string(),
            fallback_model: "gpt-4o-mini".to_string(),
            base_url: "https://api.openai.com/v1".to_string(),
        }
    }

    pub fn is_ready(&self) -> bool {
        self.enabled
            && self
                .api_key
                .as_ref()
                .is_some_and(|value| !value.trim().is_empty())
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FormaMcpConfig {
    pub url: Option<String>,
}

impl FormaMcpConfig {
    pub fn disabled() -> Self {
        Self { url: None }
    }

    pub fn is_enabled(&self) -> bool {
        self.url
            .as_ref()
            .is_some_and(|value| !value.trim().is_empty())
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct FormaMcpTool {
    pub name: String,
    #[serde(default)]
    pub description: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FormaMcpContext {
    pub url: Option<String>,
    pub tools: Vec<FormaMcpTool>,
    pub agent_card: Option<AgentCard>,
    pub error: Option<String>,
}

impl FormaMcpContext {
    pub fn disabled() -> Self {
        Self::default()
    }

    pub fn is_available(&self) -> bool {
        self.url.is_some() && self.error.is_none()
    }

    pub fn summary(&self) -> String {
        match (&self.url, &self.error) {
            (None, _) => "Forma MCP: not configured.".to_string(),
            (Some(url), Some(error)) => format!("Forma MCP: {url}; unavailable: {error}"),
            (Some(url), None) => {
                let tools = self
                    .tools
                    .iter()
                    .take(8)
                    .map(|tool| tool.name.as_str())
                    .collect::<Vec<_>>()
                    .join(", ");
                let tools = if tools.is_empty() {
                    "no tools discovered".to_string()
                } else {
                    tools
                };
                let card = self
                    .agent_card
                    .as_ref()
                    .map(|card| format!("agent card: {} ({})", card.name, card.namespace_label()))
                    .unwrap_or_else(|| "agent card unavailable".to_string());
                format!("Forma MCP: {url}; tools: {tools}; {card}.")
            }
        }
    }
}

#[derive(Debug, Clone)]
pub struct AgentMemoryTurn {
    pub user_summary: String,
    pub response_summary: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Default)]
pub struct AgentMemory {
    turns: Vec<AgentMemoryTurn>,
}

impl AgentMemory {
    pub fn from_stored(turns: Vec<StoredMemoryTurn>) -> Self {
        Self {
            turns: turns
                .into_iter()
                .map(|turn| AgentMemoryTurn {
                    user_summary: turn.user_summary,
                    response_summary: turn.response_summary,
                    created_at: turn.created_at,
                })
                .collect(),
        }
    }

    pub fn remember(&mut self, input: &ChatInput, response: &str) {
        self.turns.push(AgentMemoryTurn {
            user_summary: compact_line(&input.body, 180),
            response_summary: compact_line(response, 220),
            created_at: input.created_at.clone(),
        });
        if self.turns.len() > AGENT_MEMORY_LIMIT {
            let overflow = self.turns.len() - AGENT_MEMORY_LIMIT;
            self.turns.drain(0..overflow);
        }
    }

    pub fn clear(&mut self) {
        self.turns.clear();
    }

    pub fn len(&self) -> usize {
        self.turns.len()
    }

    pub fn is_empty(&self) -> bool {
        self.turns.is_empty()
    }

    pub fn prompt_summary(&self) -> String {
        if self.turns.is_empty() {
            return "Agent memory: no prior turns in this session.".to_string();
        }
        let turns = self
            .turns
            .iter()
            .enumerate()
            .map(|(index, turn)| {
                format!(
                    "{}. [{}] user: {}; agent: {}",
                    index + 1,
                    turn.created_at,
                    turn.user_summary,
                    turn.response_summary
                )
            })
            .collect::<Vec<_>>()
            .join("\n");
        format!("Agent memory, newest session context:\n{turns}")
    }
}

#[derive(Debug, Clone)]
pub enum AgentJob {
    Analyze(ChatInput),
    Forget,
    Shutdown,
}

#[derive(Debug, Clone)]
pub struct AgentObservation {
    pub agent_id: String,
    pub agent_name: String,
    pub namespace: Option<String>,
    pub body: String,
}

#[derive(Debug, Clone)]
pub enum MasterJob {
    Start {
        input: ChatInput,
        agents: Vec<AgentCard>,
    },
    Synthesize {
        input: ChatInput,
        observations: Vec<AgentObservation>,
    },
    Forget,
    Shutdown,
}

#[derive(Debug, Clone)]
pub struct AgentResponse {
    pub stream_id: String,
    pub agent_id: String,
    pub agent_name: String,
    pub namespace: Option<String>,
    pub body: String,
    pub tags: Vec<String>,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub enum AgentOutput {
    MasterStarted {
        stream_id: String,
        created_at: String,
    },
    MasterNoteDelta {
        stream_id: String,
        body: String,
    },
    MasterNotesDone {
        stream_id: String,
    },
    MasterFinalStarted {
        stream_id: String,
    },
    MasterFinalDelta {
        stream_id: String,
        body: String,
    },
    MasterDone {
        stream_id: String,
    },
    MasterError {
        stream_id: String,
        body: String,
        created_at: String,
    },
    Started {
        stream_id: String,
        agent_id: String,
        agent_name: String,
        namespace: Option<String>,
        created_at: String,
    },
    Delta {
        stream_id: String,
        agent_id: String,
        body: String,
    },
    Done {
        stream_id: String,
        agent_id: String,
    },
    Error {
        stream_id: String,
        agent_id: String,
        agent_name: String,
        namespace: Option<String>,
        body: String,
        created_at: String,
    },
    Full(AgentResponse),
}

#[derive(Debug)]
pub struct AgentEvent {
    pub senders: Vec<Sender<AgentJob>>,
    pub master_sender: Sender<MasterJob>,
    pub responses: Receiver<AgentOutput>,
}

pub fn default_agent_cards() -> Vec<AgentCard> {
    vec![
        card(
            "product.overview",
            "product.overview",
            "Product Overview Agent",
            "Product intent, requirements, constraints, and top-level summary.",
            "Frames the user request and identifies missing context.",
        ),
        card(
            "product.electrical",
            "product.electrical",
            "Product Electrical Agent",
            "Components, nets, buses, pin mappings, power rails, and electrical checks.",
            "Looks for component, wiring, and power implications.",
        ),
        card(
            "product.bom",
            "product.bom",
            "Product BOM Agent",
            "Bill of materials, sourcing, quantities, substitutions, and cost rollups.",
            "Turns ideas into procurement and cost questions.",
        ),
        card(
            "product.mech",
            "product.mech",
            "Product Mechanical Agent",
            "Enclosure, CAD/fabrication sources, dimensions, placement, and mechanical constraints.",
            "Checks physical fit, assembly, materials, and fabrication assumptions.",
        ),
        card(
            "product.validation",
            "product.validation",
            "Product Validation Agent",
            "Circuit validation, safety checks, risk gates, and operation status.",
            "Highlights checks that should block or gate execution.",
        ),
        card(
            "product.assembly",
            "product.assembly",
            "Product Assembly Agent",
            "Build sequence, affected parts, danger flags, and physical workflow.",
            "Converts plans into builder-facing sequencing.",
        ),
        card(
            "fabricator",
            "product.fabricator",
            "Fabricator",
            "Fabrication planning from primitive material inputs.",
            "Maps primitives, constraints, and equipment into conceptual fabrication routes.",
        ),
    ]
}

fn card(agent_id: &str, namespace: &str, name: &str, domain: &str, summary: &str) -> AgentCard {
    AgentCard {
        agent_id: agent_id.to_string(),
        name: name.to_string(),
        namespace: Some(namespace.to_string()),
        domain: domain.to_string(),
        summary: summary.to_string(),
        capabilities: vec![LatticeCapability {
            id: format!("{namespace}.chat"),
            label: "Independent chat analysis".to_string(),
            description: summary.to_string(),
        }],
    }
}

pub fn spawn_agent_workers(
    cards: &[AgentCard],
    openai: OpenAiConfig,
    mcp: FormaMcpConfig,
    memory_store: Option<AgentMemoryStore>,
) -> AgentEvent {
    let (response_tx, response_rx) = mpsc::channel();
    let (master_tx, master_rx) = mpsc::channel();
    let mut senders = Vec::with_capacity(cards.len());

    {
        let output = response_tx.clone();
        let openai = openai.clone();
        let mcp = mcp.clone();
        let memory_store = memory_store.clone();
        thread::spawn(move || master_loop(master_rx, output, openai, mcp, memory_store));
    }

    for (index, card) in cards.iter().cloned().enumerate() {
        let (job_tx, job_rx) = mpsc::channel();
        let output = response_tx.clone();
        let openai = openai.clone();
        let mcp = mcp.clone();
        let memory_store = memory_store.clone();
        senders.push(job_tx);
        thread::spawn(move || agent_loop(card, index, job_rx, output, openai, mcp, memory_store));
    }

    AgentEvent {
        senders,
        master_sender: master_tx,
        responses: response_rx,
    }
}

fn master_loop(
    jobs: Receiver<MasterJob>,
    output: Sender<AgentOutput>,
    openai: OpenAiConfig,
    mcp: FormaMcpConfig,
    memory_store: Option<AgentMemoryStore>,
) {
    let mut memory = load_agent_memory(&memory_store, MASTER_AGENT_ID);
    while let Ok(job) = jobs.recv() {
        match job {
            MasterJob::Start { input, agents } => {
                let mcp_context = mcp_context_for(&mcp, None);
                let result = if openai.is_ready() {
                    stream_openai_master_notes(
                        &input,
                        &agents,
                        &openai,
                        &output,
                        &memory,
                        &mcp_context,
                    )
                } else {
                    stream_local_master_notes(&input, &agents, &output, &memory, &mcp_context)
                };
                if let Err(error) = result {
                    if should_retry_with_fallback(&error, &openai) {
                        let mut fallback = openai.clone();
                        fallback.model = fallback.fallback_model.clone();
                        if let Err(fallback_error) = stream_openai_master_notes(
                            &input,
                            &agents,
                            &fallback,
                            &output,
                            &memory,
                            &mcp_context,
                        ) {
                            send_master_error(&input, &output, fallback_error);
                        }
                    } else {
                        send_master_error(&input, &output, error);
                    }
                }
            }
            MasterJob::Synthesize {
                input,
                observations,
            } => {
                let mcp_context = mcp_context_for(&mcp, None);
                let result = if openai.is_ready() {
                    stream_openai_master_final(
                        &input,
                        &observations,
                        &openai,
                        &output,
                        &memory,
                        &mcp_context,
                    )
                } else {
                    stream_local_master_final(&input, &observations, &output, &memory, &mcp_context)
                };
                match result {
                    Ok(final_output) => remember_agent_turn(
                        &mut memory,
                        &memory_store,
                        MASTER_AGENT_ID,
                        MASTER_AGENT_NAME,
                        None,
                        &input,
                        &final_output,
                    ),
                    Err(error) => {
                        if should_retry_with_fallback(&error, &openai) {
                            let mut fallback = openai.clone();
                            fallback.model = fallback.fallback_model.clone();
                            match stream_openai_master_final(
                                &input,
                                &observations,
                                &fallback,
                                &output,
                                &memory,
                                &mcp_context,
                            ) {
                                Ok(final_output) => remember_agent_turn(
                                    &mut memory,
                                    &memory_store,
                                    MASTER_AGENT_ID,
                                    MASTER_AGENT_NAME,
                                    None,
                                    &input,
                                    &final_output,
                                ),
                                Err(fallback_error) => {
                                    send_master_error(&input, &output, fallback_error);
                                }
                            }
                        } else {
                            send_master_error(&input, &output, error);
                        }
                    }
                }
            }
            MasterJob::Forget => {
                memory.clear();
                if let Some(store) = &memory_store {
                    let _ = store.clear_agent(MASTER_AGENT_ID);
                }
            }
            MasterJob::Shutdown => break,
        }
    }
}

fn agent_loop(
    card: AgentCard,
    index: usize,
    jobs: Receiver<AgentJob>,
    output: Sender<AgentOutput>,
    openai: OpenAiConfig,
    mcp: FormaMcpConfig,
    memory_store: Option<AgentMemoryStore>,
) {
    let mut memory = load_agent_memory(&memory_store, &card.agent_id);
    while let Ok(job) = jobs.recv() {
        match job {
            AgentJob::Analyze(input) => {
                let mcp_context = mcp_context_for(&mcp, Some(&card));
                if openai.is_ready() {
                    match stream_openai_for_agent(
                        &card,
                        &input,
                        &openai,
                        &output,
                        &memory,
                        &mcp_context,
                    ) {
                        Ok(response) => remember_agent_turn(
                            &mut memory,
                            &memory_store,
                            &card.agent_id,
                            &card.name,
                            card.namespace.as_deref(),
                            &input,
                            &response,
                        ),
                        Err(error) => {
                            if should_retry_with_fallback(&error, &openai) {
                                let mut fallback = openai.clone();
                                fallback.model = fallback.fallback_model.clone();
                                match stream_openai_for_agent(
                                    &card,
                                    &input,
                                    &fallback,
                                    &output,
                                    &memory,
                                    &mcp_context,
                                ) {
                                    Ok(response) => remember_agent_turn(
                                        &mut memory,
                                        &memory_store,
                                        &card.agent_id,
                                        &card.name,
                                        card.namespace.as_deref(),
                                        &input,
                                        &response,
                                    ),
                                    Err(fallback_error) => {
                                        send_openai_error(&card, &input, &output, fallback_error);
                                    }
                                }
                            } else {
                                send_openai_error(&card, &input, &output, error);
                            }
                        }
                    }
                } else {
                    let delay = 80 + ((index as u64 * 47) % 220);
                    thread::sleep(Duration::from_millis(delay));
                    let response =
                        analyze_for_agent_with_context(&card, &input, &memory, &mcp_context);
                    remember_agent_turn(
                        &mut memory,
                        &memory_store,
                        &card.agent_id,
                        &card.name,
                        card.namespace.as_deref(),
                        &input,
                        &response.body,
                    );
                    let _ = output.send(AgentOutput::Full(response));
                }
            }
            AgentJob::Forget => {
                memory.clear();
                if let Some(store) = &memory_store {
                    let _ = store.clear_agent(&card.agent_id);
                }
            }
            AgentJob::Shutdown => break,
        }
    }
}

fn mcp_context_for(mcp: &FormaMcpConfig, card: Option<&AgentCard>) -> FormaMcpContext {
    let Some(url) = mcp.url.as_deref().filter(|value| !value.trim().is_empty()) else {
        return FormaMcpContext::disabled();
    };
    match fetch_agent_mcp_context(url, card) {
        Ok(context) => context,
        Err(error) => FormaMcpContext {
            url: Some(url.to_string()),
            tools: Vec::new(),
            agent_card: None,
            error: Some(error),
        },
    }
}

fn load_agent_memory(store: &Option<AgentMemoryStore>, agent_id: &str) -> AgentMemory {
    store
        .as_ref()
        .and_then(|store| store.load(agent_id, AGENT_MEMORY_LIMIT).ok())
        .map(AgentMemory::from_stored)
        .unwrap_or_default()
}

fn remember_agent_turn(
    memory: &mut AgentMemory,
    store: &Option<AgentMemoryStore>,
    agent_id: &str,
    agent_name: &str,
    namespace: Option<&str>,
    input: &ChatInput,
    response: &str,
) {
    memory.remember(input, response);
    if let Some(store) = store {
        let user_summary = compact_line(&input.body, 180);
        let response_summary = compact_line(response, 220);
        let _ = store.remember(
            agent_id,
            agent_name,
            namespace,
            &user_summary,
            &response_summary,
            &input.created_at,
        );
    }
}

fn send_openai_error(
    card: &AgentCard,
    input: &ChatInput,
    output: &Sender<AgentOutput>,
    error: String,
) {
    let stream_id = stream_id_for(card, input);
    let _ = output.send(AgentOutput::Error {
        stream_id,
        agent_id: card.agent_id.clone(),
        agent_name: card.name.clone(),
        namespace: card.namespace.clone(),
        body: format!("OpenAI stream failed: {error}"),
        created_at: now_string(),
    });
}

fn send_master_error(input: &ChatInput, output: &Sender<AgentOutput>, error: String) {
    let _ = output.send(AgentOutput::MasterError {
        stream_id: master_stream_id_for(input),
        body: format!("Master stream failed: {error}"),
        created_at: now_string(),
    });
}

fn should_retry_with_fallback(error: &str, config: &OpenAiConfig) -> bool {
    if config.model == config.fallback_model {
        return false;
    }
    let lower = error.to_lowercase();
    lower.contains("model")
        && (lower.contains("does not exist")
            || lower.contains("do not have access")
            || lower.contains("not have access"))
}

fn stream_local_master_notes(
    input: &ChatInput,
    agents: &[AgentCard],
    output: &Sender<AgentOutput>,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> Result<(), String> {
    let stream_id = master_stream_id_for(input);
    output
        .send(AgentOutput::MasterStarted {
            stream_id: stream_id.clone(),
            created_at: now_string(),
        })
        .map_err(|error| format!("could not start master stream: {error}"))?;

    let notes = local_master_notes(input, agents, memory, mcp_context);
    stream_chunks(&notes, 28, |chunk| {
        output
            .send(AgentOutput::MasterNoteDelta {
                stream_id: stream_id.clone(),
                body: chunk,
            })
            .map_err(|error| format!("could not send master note: {error}"))
    })?;

    output
        .send(AgentOutput::MasterNotesDone { stream_id })
        .map_err(|error| format!("could not finish master notes: {error}"))?;
    Ok(())
}

fn stream_local_master_final(
    input: &ChatInput,
    observations: &[AgentObservation],
    output: &Sender<AgentOutput>,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> Result<String, String> {
    let stream_id = master_stream_id_for(input);
    output
        .send(AgentOutput::MasterFinalStarted {
            stream_id: stream_id.clone(),
        })
        .map_err(|error| format!("could not start master final: {error}"))?;

    let final_output = local_master_final(input, observations, memory, mcp_context);
    stream_chunks(&final_output, 24, |chunk| {
        output
            .send(AgentOutput::MasterFinalDelta {
                stream_id: stream_id.clone(),
                body: chunk,
            })
            .map_err(|error| format!("could not send master final: {error}"))
    })?;

    output
        .send(AgentOutput::MasterDone { stream_id })
        .map_err(|error| format!("could not finish master final: {error}"))?;
    Ok(final_output)
}

fn stream_openai_master_notes(
    input: &ChatInput,
    agents: &[AgentCard],
    config: &OpenAiConfig,
    output: &Sender<AgentOutput>,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> Result<(), String> {
    let stream_id = master_stream_id_for(input);
    let agent_list = agents
        .iter()
        .map(|agent| format!("{} ({})", agent.name, agent.namespace_label()))
        .collect::<Vec<_>>()
        .join(", ");
    let prompt = format!(
        "{}\n\nAvailable namespace agents: {}",
        user_prompt(input, memory, mcp_context),
        agent_list
    );

    stream_openai_text(
        config,
        master_notes_prompt(),
        prompt,
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            move || {
                output
                    .send(AgentOutput::MasterStarted {
                        stream_id: stream_id.clone(),
                        created_at: now_string(),
                    })
                    .map_err(|error| format!("could not start master stream: {error}"))
            }
        },
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            move |delta| {
                output
                    .send(AgentOutput::MasterNoteDelta {
                        stream_id: stream_id.clone(),
                        body: delta,
                    })
                    .map_err(|error| format!("could not send master note delta: {error}"))
            }
        },
    )?;

    output
        .send(AgentOutput::MasterNotesDone { stream_id })
        .map_err(|error| format!("could not finish master notes: {error}"))?;
    Ok(())
}

fn stream_openai_master_final(
    input: &ChatInput,
    observations: &[AgentObservation],
    config: &OpenAiConfig,
    output: &Sender<AgentOutput>,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> Result<String, String> {
    let stream_id = master_stream_id_for(input);
    let observations = observations_prompt(observations);
    let prompt = format!(
        "{}\n\nIndependent namespace observations:\n{}",
        user_prompt(input, memory, mcp_context),
        observations
    );
    let captured = Arc::new(Mutex::new(String::new()));

    stream_openai_text(
        config,
        master_final_prompt(),
        prompt,
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            move || {
                output
                    .send(AgentOutput::MasterFinalStarted {
                        stream_id: stream_id.clone(),
                    })
                    .map_err(|error| format!("could not start master final: {error}"))
            }
        },
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            let captured = Arc::clone(&captured);
            move |delta| {
                if let Ok(mut captured) = captured.lock() {
                    captured.push_str(&delta);
                }
                output
                    .send(AgentOutput::MasterFinalDelta {
                        stream_id: stream_id.clone(),
                        body: delta,
                    })
                    .map_err(|error| format!("could not send master final delta: {error}"))
            }
        },
    )?;

    output
        .send(AgentOutput::MasterDone { stream_id })
        .map_err(|error| format!("could not finish master final: {error}"))?;
    Ok(captured
        .lock()
        .map(|captured| captured.clone())
        .unwrap_or_default())
}

pub fn analyze_for_agent(card: &AgentCard, input: &ChatInput) -> AgentResponse {
    analyze_for_agent_with_context(
        card,
        input,
        &AgentMemory::default(),
        &FormaMcpContext::disabled(),
    )
}

pub fn analyze_for_agent_with_context(
    card: &AgentCard,
    input: &ChatInput,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> AgentResponse {
    let namespace = card.namespace_label();
    let lower = input.body.to_lowercase();
    let source_note = match &input.kind {
        InputKind::Text => "text message".to_string(),
        InputKind::File { path, byte_len } => {
            format!("file `{}` ({} bytes)", path.display(), byte_len)
        }
    };

    let body = if namespace.contains("mech") {
        mechanical_reply(&input.user_name, &source_note, &lower)
    } else if namespace.contains("bom") {
        bom_reply(&input.user_name, &source_note, &lower)
    } else if namespace.contains("electrical") {
        electrical_reply(&input.user_name, &source_note, &lower)
    } else if namespace.contains("validation") {
        validation_reply(&input.user_name, &source_note, &lower)
    } else if namespace.contains("assembly") {
        assembly_reply(&input.user_name, &source_note, &lower)
    } else if namespace.contains("fabricator") || card.agent_id == "fabricator" {
        fabricator_reply(&input.user_name, &source_note, &lower)
    } else {
        overview_reply(&input.user_name, &source_note, &lower)
    };
    let body = with_context_notes(body, memory, mcp_context);

    AgentResponse {
        stream_id: stream_id_for(card, input),
        agent_id: card.agent_id.clone(),
        agent_name: card.name.clone(),
        namespace: card.namespace.clone(),
        body,
        tags: tags_for(namespace, &lower),
        created_at: now_string(),
    }
}

fn stream_openai_for_agent(
    card: &AgentCard,
    input: &ChatInput,
    config: &OpenAiConfig,
    output: &Sender<AgentOutput>,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> Result<String, String> {
    let stream_id = stream_id_for(card, input);
    let captured = Arc::new(Mutex::new(String::new()));
    stream_openai_text(
        config,
        agent_system_prompt(card, memory, mcp_context),
        user_prompt(input, memory, mcp_context),
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            let card = card.clone();
            move || {
                output
                    .send(AgentOutput::Started {
                        stream_id: stream_id.clone(),
                        agent_id: card.agent_id.clone(),
                        agent_name: card.name.clone(),
                        namespace: card.namespace.clone(),
                        created_at: now_string(),
                    })
                    .map_err(|error| format!("could not start stream: {error}"))
            }
        },
        {
            let stream_id = stream_id.clone();
            let output = output.clone();
            let agent_id = card.agent_id.clone();
            let captured = Arc::clone(&captured);
            move |delta| {
                if let Ok(mut captured) = captured.lock() {
                    captured.push_str(&delta);
                }
                output
                    .send(AgentOutput::Delta {
                        stream_id: stream_id.clone(),
                        agent_id: agent_id.clone(),
                        body: delta,
                    })
                    .map_err(|error| format!("could not send stream delta: {error}"))
            }
        },
    )?;

    output
        .send(AgentOutput::Done {
            stream_id,
            agent_id: card.agent_id.clone(),
        })
        .map_err(|error| format!("could not finish stream: {error}"))?;
    Ok(captured
        .lock()
        .map(|captured| captured.clone())
        .unwrap_or_default())
}

fn stream_openai_text<R, D>(
    config: &OpenAiConfig,
    instructions: String,
    input: String,
    mut on_ready: R,
    mut on_delta: D,
) -> Result<(), String>
where
    R: FnMut() -> Result<(), String>,
    D: FnMut(String) -> Result<(), String>,
{
    let request = serde_json::json!({
        "model": config.model,
        "stream": true,
        "store": false,
        "instructions": instructions,
        "input": input
    });

    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|error| format!("could not build OpenAI client: {error}"))?;
    let url = format!("{}/responses", config.base_url.trim_end_matches('/'));
    let api_key = config
        .api_key
        .as_ref()
        .ok_or_else(|| "OPENAI_API_KEY is not set".to_string())?;
    let mut response = client
        .post(url)
        .bearer_auth(api_key)
        .header(reqwest::header::ACCEPT, "text/event-stream")
        .json(&request)
        .send()
        .map_err(|error| format!("OpenAI request failed: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let text = response
            .text()
            .unwrap_or_else(|_| "<unreadable response body>".to_string());
        return Err(format!("OpenAI returned {status}: {text}"));
    }

    on_ready()?;

    let mut buffer = [0_u8; 4096];
    let mut pending = String::new();
    loop {
        let read = response
            .read(&mut buffer)
            .map_err(|error| format!("OpenAI stream read failed: {error}"))?;
        if read == 0 {
            break;
        }
        pending.push_str(&String::from_utf8_lossy(&buffer[..read]));
        while let Some(index) = pending.find('\n') {
            let line: String = pending.drain(..=index).collect();
            process_sse_text_line(line.trim(), &mut on_delta)?;
        }
    }
    Ok(())
}

fn process_sse_text_line<D>(line: &str, on_delta: &mut D) -> Result<(), String>
where
    D: FnMut(String) -> Result<(), String>,
{
    let Some(data) = line.strip_prefix("data:") else {
        return Ok(());
    };
    let data = data.trim();
    if data.is_empty() || data == "[DONE]" {
        return Ok(());
    }
    let value: serde_json::Value = serde_json::from_str(data)
        .map_err(|error| format!("could not parse OpenAI stream event: {error}: {data}"))?;
    let event_type = value
        .get("type")
        .and_then(|item| item.as_str())
        .unwrap_or_default();
    match event_type {
        "response.output_text.delta" | "response.refusal.delta" => {
            if let Some(delta) = value.get("delta").and_then(|item| item.as_str()) {
                on_delta(delta.to_string())?;
            }
        }
        "response.completed" => {}
        "error" | "response.failed" => {
            let message = value
                .pointer("/error/message")
                .or_else(|| value.pointer("/response/error/message"))
                .or_else(|| value.pointer("/message"))
                .and_then(|item| item.as_str())
                .unwrap_or("OpenAI stream reported an error");
            on_delta(format!("\n[error] {message}"))?;
        }
        _ => {}
    }
    Ok(())
}

fn agent_system_prompt(
    card: &AgentCard,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> String {
    format!(
        "You are {name}, an independent Forma Lattice namespace agent.\n\
         Namespace: {namespace}\n\
         Domain: {domain}\n\
         Summary: {summary}\n\
         {memory}\n\
         {mcp}\n\
         Act only from your namespace perspective. Be concise. Use memory only when it is relevant to the current request. Use Forma MCP context for handoff/tool suggestions, and explicitly name useful Forma MCP tools when they are relevant. Do not pretend other agents agree with you.",
        name = card.name,
        namespace = card.namespace_label(),
        domain = card.domain,
        summary = card.summary,
        memory = memory.prompt_summary(),
        mcp = mcp_context.summary(),
    )
}

fn user_prompt(
    input: &ChatInput,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> String {
    let source = match &input.kind {
        InputKind::Text => "text".to_string(),
        InputKind::File { path, byte_len } => {
            format!("file `{}` ({byte_len} bytes)", path.display())
        }
    };
    format!(
        "User: {}\nInput source: {}\n{}\n{}\n\nCurrent user input:\n{}",
        input.user_name,
        source,
        memory.prompt_summary(),
        mcp_context.summary(),
        input.body
    )
}

fn master_notes_prompt() -> String {
    "You are Forma Architect, the master coordination agent for a lattice of specialized Forma namespace agents.\n\
     Stream concise visible working notes only. These notes are user-facing coordination notes: routing, assumptions to check, risks to watch, and which namespace agents matter.\n\
     Do not reveal private chain-of-thought or hidden deliberation. Do not give the final answer in this phase.\n\
     Use 3 to 5 short bullets."
        .to_string()
}

fn master_final_prompt() -> String {
    "You are Forma Architect, the master coordination agent for Forma.\n\
     Produce the final synthesized output for the user from the request and the independent namespace observations.\n\
     Be direct and builder-facing. Preserve uncertainty, call out safety/review gates, and turn the agent observations into a clear next action.\n\
     Do not claim consensus where observations conflict or are incomplete."
        .to_string()
}

fn local_master_notes(
    input: &ChatInput,
    agents: &[AgentCard],
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> String {
    let source = source_label(input);
    let agent_names = agents
        .iter()
        .map(|agent| agent.namespace_label().to_string())
        .collect::<Vec<_>>()
        .join(", ");
    let lower = input.body.to_lowercase();
    let focus = if lower.contains("robot") || lower.contains("arm") {
        "load path, joints, actuator choice, repeatability, and material stiffness"
    } else if lower.contains("battery") || lower.contains("power") {
        "power budget, component limits, enclosure fit, and validation gates"
    } else if lower.contains("file") || matches!(&input.kind, InputKind::File { .. }) {
        "file intent, schema fit, affected namespaces, and missing build context"
    } else {
        "requirements, physical constraints, sourcing, assembly order, and validation"
    };

    format!(
        "- Routing the {source} through: {agent_names}.\n\
         - Primary coordination focus: {focus}.\n\
         - Memory available to Architect: {} prior synthesized turn(s).\n\
         - MCP bridge: {}\n\
         - I will let each namespace speak independently, then synthesize a single builder-facing answer.\n\
         - I will treat physical fabrication, power, and safety claims as review-gated until the relevant agents provide enough signal.\n"
        ,
        memory.len(),
        mcp_context.summary()
    )
}

fn local_master_final(
    input: &ChatInput,
    observations: &[AgentObservation],
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> String {
    let lower = input.body.to_lowercase();
    let material_hint = if lower.contains("cardboard") {
        "For a cardboard-like robot-arm material, start with stiffness coupons: layered corrugation, fiber direction, adhesive choice, thickness, humidity behavior, and joint crush resistance."
    } else if lower.contains("fabric") || lower.contains("fiber") || lower.contains("cellulose") {
        "For a fiber-based material, start with primitive characterization, binder choice, coupon tests, and a fabrication route before committing to geometry."
    } else {
        "Start by locking the project brief: goal, hard constraints, operating environment, load cases, available tools, budget, and review gates."
    };
    let strongest = observations
        .iter()
        .take(3)
        .map(|observation| {
            format!(
                "{}: {}",
                observation
                    .namespace
                    .as_deref()
                    .unwrap_or(observation.agent_id.as_str()),
                compact_line(&observation.body, 140)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let signal = if strongest.is_empty() {
        "No namespace observations were collected before synthesis.".to_string()
    } else {
        format!("Top namespace signals:\n{strongest}")
    };

    format!(
        "{}, final output: {}\n\n{}\n\nMemory used: {} prior Architect turn(s). Forma MCP: {}\n\nNext action: define the measurable target first, then ask Fabricator and Mechanical for material coupons and geometry limits, BOM for candidate materials, Assembly for build order, and Validation for gates before any physical build.",
        input.user_name,
        material_hint,
        signal,
        memory.len(),
        mcp_context.summary()
    )
}

fn observations_prompt(observations: &[AgentObservation]) -> String {
    if observations.is_empty() {
        return "No namespace observations were collected.".to_string();
    }
    observations
        .iter()
        .map(|observation| {
            format!(
                "- {} [{}]: {}",
                observation.agent_name,
                observation
                    .namespace
                    .as_deref()
                    .unwrap_or(observation.agent_id.as_str()),
                observation.body
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn source_label(input: &ChatInput) -> String {
    match &input.kind {
        InputKind::Text => "text message".to_string(),
        InputKind::File { path, byte_len } => {
            format!("file `{}` ({} bytes)", path.display(), byte_len)
        }
    }
}

fn compact_line(value: &str, max_chars: usize) -> String {
    let line = value.split_whitespace().collect::<Vec<_>>().join(" ");
    if line.chars().count() <= max_chars {
        return line;
    }
    let mut truncated: String = line.chars().take(max_chars.saturating_sub(3)).collect();
    truncated.push_str("...");
    truncated
}

fn with_context_notes(
    mut body: String,
    memory: &AgentMemory,
    mcp_context: &FormaMcpContext,
) -> String {
    let mut notes = Vec::new();
    if !memory.is_empty() {
        notes.push(format!(
            "Memory: carrying {} prior turn(s) for this agent.",
            memory.len()
        ));
    }
    if mcp_context.url.is_some() {
        notes.push(mcp_context.summary());
    }
    if !notes.is_empty() {
        body.push_str("\n\n");
        body.push_str(&notes.join("\n"));
    }
    body
}

fn stream_chunks<F>(text: &str, delay_ms: u64, mut on_chunk: F) -> Result<(), String>
where
    F: FnMut(String) -> Result<(), String>,
{
    let mut chunk = String::new();
    for piece in text.split_inclusive(' ') {
        chunk.push_str(piece);
        if chunk.len() >= 32 || chunk.contains('\n') {
            on_chunk(chunk.clone())?;
            chunk.clear();
            thread::sleep(Duration::from_millis(delay_ms));
        }
    }
    if !chunk.is_empty() {
        on_chunk(chunk)?;
    }
    Ok(())
}

fn master_stream_id_for(input: &ChatInput) -> String {
    format!("{}:{}", MASTER_AGENT_ID, input.created_at)
}

fn stream_id_for(card: &AgentCard, input: &ChatInput) -> String {
    format!("{}:{}", card.agent_id, input.created_at)
}

fn overview_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let missing = missing_terms(lower, &["goal", "budget", "timeline", "constraint"]);
    format!(
        "{user_name}, I scoped the {source_note}. I would turn this into a project brief first: goal, hard constraints, success criteria, and unknowns. Missing signals I want: {}.",
        missing
    )
}

fn electrical_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let focus = if lower.contains("battery") || lower.contains("power") {
        "power rails, current draw, charging/protection, and connector choice"
    } else if lower.contains("sensor") || lower.contains("motor") {
        "controller pins, interface buses, driver parts, and validation nets"
    } else {
        "component roles, pin mappings, nets, buses, and validation hooks"
    };
    format!("{user_name}, electrical read on the {source_note}: I would inspect {focus}. I need component candidates before wiring claims become trustworthy.")
}

fn bom_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let risk = if lower.contains("cheap") || lower.contains("budget") {
        "cost ceiling and substitution risk"
    } else if lower.contains("prototype") {
        "prototype availability, lead time, and minimum order quantity"
    } else {
        "unit cost, source confidence, quantity, and alternates"
    };
    format!("{user_name}, BOM read on the {source_note}: I would split this into buyable line items and track {risk}. No procurement step should proceed without source URLs and quantities.")
}

fn mechanical_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let concern = if lower.contains("water") || lower.contains("outdoor") {
        "sealing, cable ingress, fasteners, and service access"
    } else if lower.contains("wear") || lower.contains("portable") {
        "weight, mounting orientation, strain relief, and enclosure comfort"
    } else {
        "enclosure dimensions, mounting faces, clearances, and fabrication method"
    };
    format!("{user_name}, mechanical read on the {source_note}: I am watching {concern}. I would hand off exact component envelopes before CAD or fabrication estimates.")
}

fn validation_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let gate = if lower.contains("bio") || lower.contains("chemical") || lower.contains("heat") {
        "human review, safety data, thermal limits, and regulated-material checks"
    } else {
        "schema validity, electrical checks, fit checks, and assembly risk flags"
    };
    format!("{user_name}, validation read on the {source_note}: I would gate this on {gate}. I will mark any physical action as review-required until the dependent agents agree.")
}

fn assembly_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let sequence = if lower.contains("file") || lower.contains("stl") || lower.contains("cad") {
        "print/cut parts, inspect tolerances, mount electronics, route wires, then run validation"
    } else {
        "inventory, prep, mechanical fit, wiring, inspection, and functional test"
    };
    format!("{user_name}, assembly read on the {source_note}: the first safe build sequence is {sequence}. I need danger flags before turning this into builder steps.")
}

fn fabricator_reply(user_name: &str, source_note: &str, lower: &str) -> String {
    let route =
        if lower.contains("cellulose") || lower.contains("fiber") || lower.contains("biomass") {
            "bio-composite screening routes"
        } else if lower.contains("powder") || lower.contains("ceramic") || lower.contains("metal") {
            "functional-material formulation and coupon routes"
        } else {
            "primitive characterization before choosing a fabrication route"
        };
    format!("{user_name}, Fabricator read on the {source_note}: I would start with {route}. I will keep this conceptual and ask Forma for inventory, device discovery, simulation, and review gates.")
}

fn missing_terms(lower: &str, terms: &[&str]) -> String {
    let missing: Vec<&str> = terms
        .iter()
        .copied()
        .filter(|term| !lower.contains(term))
        .collect();
    if missing.is_empty() {
        "none obvious".to_string()
    } else {
        missing.join(", ")
    }
}

fn tags_for(namespace: &str, lower: &str) -> Vec<String> {
    let mut tags = vec![namespace.to_string()];
    for (needle, tag) in [
        ("battery", "power"),
        ("cost", "cost"),
        ("budget", "cost"),
        ("file", "file"),
        ("cad", "cad"),
        ("chemical", "safety"),
        ("bio", "safety"),
        ("prototype", "prototype"),
    ] {
        if lower.contains(needle) {
            tags.push(tag.to_string());
        }
    }
    tags
}

pub fn read_file_payload(path: impl AsRef<Path>) -> Result<(String, usize), String> {
    let path = path.as_ref();
    let bytes =
        fs::read(path).map_err(|error| format!("could not read `{}`: {error}", path.display()))?;
    let byte_len = bytes.len();
    let mut text = String::from_utf8_lossy(&bytes).to_string();
    if text.len() > FILE_PREVIEW_LIMIT {
        text.truncate(FILE_PREVIEW_LIMIT);
        text.push_str("\n\n[truncated preview]");
    }
    Ok((text, byte_len))
}

pub fn now_string() -> String {
    let milliseconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    milliseconds.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_cards_include_core_namespace_agents() {
        let ids: Vec<String> = default_agent_cards()
            .into_iter()
            .map(|card| card.namespace.unwrap_or(card.agent_id))
            .collect();
        assert!(ids.contains(&"product.mech".to_string()));
        assert!(ids.contains(&"product.bom".to_string()));
        assert!(ids.contains(&"product.fabricator".to_string()));
    }

    #[test]
    fn mechanical_agent_uses_mechanical_language() {
        let card = card(
            "product.mech",
            "product.mech",
            "Product Mechanical Agent",
            "",
            "",
        );
        let input = ChatInput {
            user_name: "Isayah".to_string(),
            body: "portable outdoor sensor".to_string(),
            kind: InputKind::Text,
            created_at: now_string(),
        };

        let response = analyze_for_agent(&card, &input);

        assert!(response.body.contains("mechanical read"));
        assert!(response.body.contains("sealing") || response.body.contains("weight"));
    }

    #[test]
    fn agent_memory_is_included_in_contextual_reply() {
        let card = card("fabricator", "product.fabricator", "Fabricator", "", "");
        let first = ChatInput {
            user_name: "Isayah".to_string(),
            body: "remember that the shoe needs to be waterproof".to_string(),
            kind: InputKind::Text,
            created_at: now_string(),
        };
        let second = ChatInput {
            user_name: "Isayah".to_string(),
            body: "now make the sole flexible".to_string(),
            kind: InputKind::Text,
            created_at: now_string(),
        };
        let mut memory = AgentMemory::default();
        memory.remember(&first, "Waterproof shoe constraint recorded.");

        let response = analyze_for_agent_with_context(
            &card,
            &second,
            &memory,
            &FormaMcpContext::disabled(),
        );

        assert!(response.body.contains("Memory: carrying 1 prior turn"));
    }

    #[test]
    fn mcp_context_summary_lists_tools_and_agent_card() {
        let context = FormaMcpContext {
            url: Some("http://127.0.0.1:8000/api/mcp".to_string()),
            tools: vec![FormaMcpTool {
                name: "blueprint.lattice.get_agent_card".to_string(),
                description: "Fetch an agent card".to_string(),
            }],
            agent_card: Some(card(
                "fabricator",
                "product.fabricator",
                "Fabricator",
                "",
                "",
            )),
            error: None,
        };

        let summary = context.summary();

        assert!(summary.contains("blueprint.lattice.get_agent_card"));
        assert!(summary.contains("Fabricator"));
    }
}
