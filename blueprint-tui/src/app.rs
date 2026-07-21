use crate::agents::{
    default_agent_cards, now_string, read_file_payload, spawn_agent_workers, AgentCard, AgentEvent,
    AgentJob, AgentObservation, AgentOutput, FormaMcpConfig, ChatInput, InputKind, MasterJob,
    OpenAiConfig, MASTER_AGENT_ID, MASTER_AGENT_NAME,
};
use crate::blueprint::fetch_lattice_agents;
use crate::storage::SqliteStore;
use crate::ui::draw;
use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyModifiers};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use std::collections::{BTreeMap, BTreeSet};
use std::io;
use std::path::PathBuf;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub user_name: Option<String>,
    pub mcp_url: Option<String>,
    pub initial_file: Option<PathBuf>,
    pub openai: OpenAiConfig,
    pub sqlite_path: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputMode {
    Name,
    Chat,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TranscriptRole {
    System,
    User,
    Agent,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollFocus {
    Chat,
    Architect,
    Agents,
}

impl ScrollFocus {
    pub fn label(self) -> &'static str {
        match self {
            Self::Chat => "chat",
            Self::Architect => "architect",
            Self::Agents => "agents",
        }
    }
}

#[derive(Debug, Clone)]
pub struct TranscriptItem {
    pub stream_id: Option<String>,
    pub role: TranscriptRole,
    pub author: String,
    pub namespace: Option<String>,
    pub body: String,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub struct AgentState {
    pub card: AgentCard,
    pub status: String,
    pub last_message: String,
}

#[derive(Debug, Clone)]
struct ActiveMasterRequest {
    input: ChatInput,
    pending_agents: BTreeSet<String>,
    observations: BTreeMap<String, AgentObservation>,
    synthesis_requested: bool,
}

pub struct ChatApp {
    pub mode: InputMode,
    pub user_name: String,
    pub input: String,
    pub transcript: Vec<TranscriptItem>,
    pub chat_focus_agent_id: Option<String>,
    pub scroll_focus: ScrollFocus,
    pub chat_scroll_from_bottom: usize,
    pub architect_scroll: usize,
    pub master_status: String,
    pub master_notes: String,
    pub master_final: String,
    pub master_stream_id: Option<String>,
    pub agent_states: BTreeMap<String, AgentState>,
    pub agent_senders: Vec<std::sync::mpsc::Sender<AgentJob>>,
    pub master_sender: std::sync::mpsc::Sender<MasterJob>,
    pub responses: std::sync::mpsc::Receiver<AgentOutput>,
    pub should_quit: bool,
    pub status: String,
    pub sqlite_store: Option<SqliteStore>,
    pending_initial_file: Option<PathBuf>,
    active_master: Option<ActiveMasterRequest>,
}

impl ChatApp {
    pub fn new(config: AppConfig) -> Self {
        let mut status = if config.openai.is_ready() {
            format!("OpenAI streaming enabled ({})", config.openai.model)
        } else if config.openai.enabled {
            "OpenAI streaming requested but OPENAI_API_KEY is missing; offline agents loaded"
                .to_string()
        } else {
            "offline Lattice agents loaded".to_string()
        };
        let cards = match config.mcp_url.as_deref() {
            Some(url) => match fetch_lattice_agents(url) {
                Ok(cards) if !cards.is_empty() => {
                    let stream_note = if config.openai.is_ready() {
                        format!("; streaming {}", config.openai.model)
                    } else {
                        String::new()
                    };
                    status = format!(
                        "loaded {} Lattice agents from {url}{stream_note}",
                        cards.len()
                    );
                    cards
                }
                Ok(_) => {
                    status = format!("Forma MCP at {url} returned no agents; using defaults");
                    default_agent_cards()
                }
                Err(error) => {
                    status = format!("{error}; using defaults");
                    default_agent_cards()
                }
            },
            None => default_agent_cards(),
        };

        let sqlite_store =
            config
                .sqlite_path
                .as_ref()
                .and_then(|path| match SqliteStore::open(path) {
                    Ok(store) => {
                        status = format!("{status}; sqlite {}", store.path().display());
                        Some(store)
                    }
                    Err(error) => {
                        status = format!("{status}; sqlite disabled: {error}");
                        None
                    }
                });
        let memory_store = sqlite_store.as_ref().map(SqliteStore::memory_store);

        let AgentEvent {
            senders,
            master_sender,
            responses,
        } = spawn_agent_workers(
            &cards,
            config.openai.clone(),
            FormaMcpConfig {
                url: config.mcp_url.clone(),
            },
            memory_store,
        );
        let agent_states = cards
            .into_iter()
            .map(|card| {
                let key = card.agent_id.clone();
                (
                    key,
                    AgentState {
                        card,
                        status: "ready".to_string(),
                        last_message: String::new(),
                    },
                )
            })
            .collect();

        let user_name = config.user_name.unwrap_or_default();
        let mode = if user_name.is_empty() {
            InputMode::Name
        } else {
            InputMode::Chat
        };

        let mut app = Self {
            mode,
            user_name,
            input: String::new(),
            transcript: Vec::new(),
            chat_focus_agent_id: None,
            scroll_focus: ScrollFocus::Chat,
            chat_scroll_from_bottom: 0,
            architect_scroll: 0,
            master_status: "ready".to_string(),
            master_notes: String::new(),
            master_final: String::new(),
            master_stream_id: None,
            agent_states,
            agent_senders: senders,
            master_sender,
            responses,
            should_quit: false,
            status,
            sqlite_store,
            pending_initial_file: config.initial_file,
            active_master: None,
        };
        app.push_system("Welcome to Forma TUI. Enter a short name, or type a prompt to start. The Forma Architect will synthesize the final output. Use /file path/to/file to submit a file.");
        if app.mode == InputMode::Chat {
            app.submit_pending_initial_file();
        }
        app
    }

    pub fn handle_key(&mut self, key: KeyEvent) {
        if key.modifiers.contains(KeyModifiers::CONTROL)
            && matches!(key.code, KeyCode::Char('q') | KeyCode::Char('c'))
        {
            self.should_quit = true;
            return;
        }

        match key.code {
            KeyCode::Enter => self.submit_input(),
            KeyCode::F(2) if self.mode == InputMode::Chat => self.cycle_scroll_focus(),
            KeyCode::Char('f')
                if self.mode == InputMode::Chat
                    && key.modifiers.contains(KeyModifiers::CONTROL) =>
            {
                self.cycle_scroll_focus();
            }
            KeyCode::Tab if self.mode == InputMode::Chat => self.focus_next_agent(),
            KeyCode::BackTab if self.mode == InputMode::Chat => self.focus_previous_agent(),
            KeyCode::Up if self.mode == InputMode::Chat => self.scroll_up(1),
            KeyCode::Down if self.mode == InputMode::Chat => self.scroll_down(1),
            KeyCode::PageUp if self.mode == InputMode::Chat => self.scroll_up(8),
            KeyCode::PageDown if self.mode == InputMode::Chat => self.scroll_down(8),
            KeyCode::Home if self.mode == InputMode::Chat => self.scroll_to_top(),
            KeyCode::End if self.mode == InputMode::Chat => self.scroll_to_bottom(),
            KeyCode::Backspace => {
                self.input.pop();
            }
            KeyCode::Esc => self.input.clear(),
            KeyCode::Char(char) => self.input.push(char),
            _ => {}
        }
    }

    pub fn drain_agent_responses(&mut self) {
        while let Ok(event) = self.responses.try_recv() {
            match event {
                AgentOutput::MasterStarted {
                    stream_id,
                    created_at: _,
                } => {
                    if !self.accepts_master_stream(&stream_id) {
                        continue;
                    }
                    self.master_stream_id = Some(stream_id);
                    self.master_status = "routing".to_string();
                    self.master_notes.clear();
                    self.master_final.clear();
                }
                AgentOutput::MasterNoteDelta { stream_id, body } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "routing".to_string();
                        self.master_notes.push_str(&body);
                    }
                }
                AgentOutput::MasterNotesDone { stream_id } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "waiting for agents".to_string();
                        if self.master_notes.trim().is_empty() {
                            self.master_notes.push_str("[no working notes returned]");
                        }
                    }
                }
                AgentOutput::MasterFinalStarted { stream_id } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "synthesizing final".to_string();
                        self.master_final.clear();
                    }
                }
                AgentOutput::MasterFinalDelta { stream_id, body } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "synthesizing final".to_string();
                        self.master_final.push_str(&body);
                    }
                }
                AgentOutput::MasterDone { stream_id } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "final ready".to_string();
                        if self.master_final.trim().is_empty() {
                            self.master_final.push_str("[no final output returned]");
                        }
                        if let Some((_, job_id)) = stream_id.rsplit_once(':') {
                            self.record_agent_response(
                                job_id,
                                MASTER_AGENT_ID,
                                MASTER_AGENT_NAME,
                                None,
                                &self.master_final,
                                "succeeded",
                            );
                            self.set_job_status(job_id, "succeeded");
                        }
                    }
                }
                AgentOutput::MasterError {
                    stream_id,
                    body,
                    created_at: _,
                } => {
                    if self.accepts_master_stream(&stream_id) {
                        self.master_status = "error".to_string();
                        if self.master_notes.trim().is_empty() {
                            self.master_notes
                                .push_str("Master Agent could not stream notes.");
                        }
                        if let Some((_, job_id)) = stream_id.rsplit_once(':') {
                            self.record_agent_response(
                                job_id,
                                MASTER_AGENT_ID,
                                MASTER_AGENT_NAME,
                                None,
                                &body,
                                "failed",
                            );
                            self.set_job_status(job_id, "failed");
                        }
                        self.master_final = body;
                    }
                }
                AgentOutput::Started {
                    stream_id,
                    agent_id,
                    agent_name,
                    namespace,
                    created_at,
                } => {
                    if let Some(state) = self.agent_states.get_mut(&agent_id) {
                        state.status = "streaming".to_string();
                        state.last_message.clear();
                    }
                    self.transcript.push(TranscriptItem {
                        stream_id: Some(stream_id),
                        role: TranscriptRole::Agent,
                        author: agent_name,
                        namespace,
                        body: String::new(),
                        created_at,
                    });
                }
                AgentOutput::Delta {
                    stream_id,
                    agent_id,
                    body,
                } => {
                    if let Some(state) = self.agent_states.get_mut(&agent_id) {
                        state.status = "streaming".to_string();
                        state.last_message.push_str(&body);
                    }
                    if let Some(item) = self
                        .transcript
                        .iter_mut()
                        .find(|item| item.stream_id.as_deref() == Some(stream_id.as_str()))
                    {
                        item.body.push_str(&body);
                    }
                }
                AgentOutput::Done {
                    stream_id,
                    agent_id,
                } => {
                    if let Some(state) = self.agent_states.get_mut(&agent_id) {
                        state.status = "responded".to_string();
                    }
                    if let Some(item) = self
                        .transcript
                        .iter_mut()
                        .find(|item| item.stream_id.as_deref() == Some(stream_id.as_str()))
                    {
                        if item.body.trim().is_empty() {
                            item.body.push_str("[no text returned]");
                        }
                    }
                    if let Some(item) = self
                        .transcript
                        .iter()
                        .find(|item| item.stream_id.as_deref() == Some(stream_id.as_str()))
                    {
                        self.record_agent_response(
                            job_id_from_stream(&stream_id),
                            &agent_id,
                            &item.author,
                            item.namespace.as_deref(),
                            &item.body,
                            "succeeded",
                        );
                    }
                    self.record_completed_agent(&stream_id, &agent_id);
                }
                AgentOutput::Error {
                    stream_id,
                    agent_id,
                    agent_name,
                    namespace,
                    body,
                    created_at,
                } => {
                    if let Some(state) = self.agent_states.get_mut(&agent_id) {
                        state.status = "error".to_string();
                        state.last_message = body.clone();
                    }
                    let observation = AgentObservation {
                        agent_id: agent_id.clone(),
                        agent_name: agent_name.clone(),
                        namespace: namespace.clone(),
                        body: body.clone(),
                    };
                    self.transcript.push(TranscriptItem {
                        stream_id: Some(stream_id.clone()),
                        role: TranscriptRole::Agent,
                        author: agent_name,
                        namespace,
                        body,
                        created_at,
                    });
                    self.record_agent_response(
                        job_id_from_stream(&stream_id),
                        &observation.agent_id,
                        &observation.agent_name,
                        observation.namespace.as_deref(),
                        &observation.body,
                        "failed",
                    );
                    self.record_agent_observation(&stream_id, observation);
                }
                AgentOutput::Full(response) => {
                    let observation = AgentObservation {
                        agent_id: response.agent_id.clone(),
                        agent_name: response.agent_name.clone(),
                        namespace: response.namespace.clone(),
                        body: response.body.clone(),
                    };
                    let stream_id = response.stream_id.clone();
                    if let Some(state) = self.agent_states.get_mut(&response.agent_id) {
                        state.status = "responded".to_string();
                        state.last_message = response.body.clone();
                    }
                    self.transcript.push(TranscriptItem {
                        stream_id: Some(response.stream_id),
                        role: TranscriptRole::Agent,
                        author: response.agent_name,
                        namespace: response.namespace,
                        body: response.body,
                        created_at: response.created_at,
                    });
                    self.record_agent_response(
                        job_id_from_stream(&stream_id),
                        &observation.agent_id,
                        &observation.agent_name,
                        observation.namespace.as_deref(),
                        &observation.body,
                        "succeeded",
                    );
                    self.record_agent_observation(&stream_id, observation);
                }
            }
        }
    }

    fn submit_input(&mut self) {
        let value = self.input.trim().to_string();
        self.input.clear();
        if value.is_empty() {
            return;
        }

        if self.mode == InputMode::Name {
            if value.starts_with('/') || Self::looks_like_first_prompt(&value) {
                self.user_name = Self::default_user_name();
                self.mode = InputMode::Chat;
                self.push_system(&format!(
                    "Using {} as your name. Agents are ready.",
                    self.user_name
                ));
                self.submit_pending_initial_file();
                self.submit_chat_value(value);
                return;
            }

            self.user_name = value;
            self.mode = InputMode::Chat;
            self.push_system(&format!("Hi, {}. Agents are ready.", self.user_name));
            self.submit_pending_initial_file();
            return;
        }

        self.submit_chat_value(value);
    }

    fn submit_chat_value(&mut self, value: String) {
        match value.as_str() {
            "/quit" | "/q" => {
                self.should_quit = true;
            }
            "/clear" => {
                self.transcript.clear();
                self.push_system("Transcript cleared.");
            }
            "/forget" => self.forget_agent_memory(),
            "/agent" => self.set_agent_focus("all"),
            "/agents" => self.push_agent_summary(),
            "/help" => self.push_system(
                "Commands: /agent all|next|prev|name, /scroll chat|architect|agents, /file path, /forget, /agents, /clear, /quit. F2 changes scroll port. Press Ctrl-Q to exit.",
            ),
            _ if value.starts_with("/agent ") => {
                let query = value.trim_start_matches("/agent ").trim();
                self.set_agent_focus(query);
            }
            _ if value.starts_with("/scroll ") => {
                let query = value.trim_start_matches("/scroll ").trim();
                self.set_scroll_focus(query);
            }
            _ if value.starts_with("/file ") => {
                let path = value.trim_start_matches("/file ").trim();
                self.submit_file(PathBuf::from(path));
            }
            _ => self.submit_text(value),
        }
    }

    fn looks_like_first_prompt(value: &str) -> bool {
        let lower = value.to_lowercase();
        value.split_whitespace().count() >= 3
            || value.ends_with(['?', '.', '!'])
            || lower.starts_with("build ")
            || lower.starts_with("make ")
            || lower.starts_with("create ")
            || lower.starts_with("can ")
            || lower.starts_with("hi,")
            || lower.starts_with("hello,")
    }

    fn default_user_name() -> String {
        std::env::var("USER")
            .or_else(|_| std::env::var("USERNAME"))
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "User".to_string())
    }

    fn submit_text(&mut self, body: String) {
        self.chat_scroll_from_bottom = 0;
        let input = ChatInput {
            user_name: self.user_name.clone(),
            body: body.clone(),
            kind: InputKind::Text,
            created_at: now_string(),
        };
        self.transcript.push(TranscriptItem {
            stream_id: None,
            role: TranscriptRole::User,
            author: self.user_name.clone(),
            namespace: None,
            body,
            created_at: input.created_at.clone(),
        });
        self.record_job(&input);
        self.broadcast(input);
    }

    fn submit_file(&mut self, path: PathBuf) {
        match read_file_payload(&path) {
            Ok((preview, byte_len)) => {
                self.chat_scroll_from_bottom = 0;
                let body = format!("Uploaded `{}` ({} bytes)", path.display(), byte_len);
                let input = ChatInput {
                    user_name: self.user_name.clone(),
                    body: preview,
                    kind: InputKind::File { path, byte_len },
                    created_at: now_string(),
                };
                self.transcript.push(TranscriptItem {
                    stream_id: None,
                    role: TranscriptRole::User,
                    author: self.user_name.clone(),
                    namespace: None,
                    body,
                    created_at: input.created_at.clone(),
                });
                self.record_job(&input);
                self.broadcast(input);
            }
            Err(error) => self.push_system(&error),
        }
    }

    fn broadcast(&mut self, input: ChatInput) {
        for state in self.agent_states.values_mut() {
            state.status = "thinking".to_string();
        }
        self.master_status = "routing".to_string();
        self.master_notes.clear();
        self.master_final.clear();
        self.master_stream_id = Some(format!("{}:{}", MASTER_AGENT_ID, input.created_at));

        let agents = self
            .agent_states
            .values()
            .map(|state| state.card.clone())
            .collect::<Vec<_>>();
        self.active_master = Some(ActiveMasterRequest {
            input: input.clone(),
            pending_agents: self.agent_states.keys().cloned().collect(),
            observations: BTreeMap::new(),
            synthesis_requested: false,
        });
        let _ = self.master_sender.send(MasterJob::Start {
            input: input.clone(),
            agents,
        });
        for sender in &self.agent_senders {
            let _ = sender.send(AgentJob::Analyze(input.clone()));
        }
        self.request_master_synthesis_if_ready();
    }

    fn record_job(&self, input: &ChatInput) {
        let Some(store) = &self.sqlite_store else {
            return;
        };
        let (kind, source_path, byte_len) = match &input.kind {
            InputKind::Text => ("text", None, None),
            InputKind::File { path, byte_len } => {
                ("file", Some(path.display().to_string()), Some(*byte_len))
            }
        };
        let _ = store.record_job(
            &input.created_at,
            &input.user_name,
            kind,
            source_path.as_deref(),
            byte_len,
            &input.body,
            &input.created_at,
        );
    }

    fn record_agent_response(
        &self,
        job_id: &str,
        agent_id: &str,
        agent_name: &str,
        namespace: Option<&str>,
        body: &str,
        status: &str,
    ) {
        let Some(store) = &self.sqlite_store else {
            return;
        };
        let _ = store.record_agent_response(
            job_id,
            agent_id,
            agent_name,
            namespace,
            body,
            status,
            &now_string(),
        );
    }

    fn set_job_status(&self, job_id: &str, status: &str) {
        if let Some(store) = &self.sqlite_store {
            let _ = store.set_job_status(job_id, status, &now_string());
        }
    }

    pub fn scroll_focus_label(&self) -> &'static str {
        self.scroll_focus.label()
    }

    pub fn chat_focus_label(&self) -> String {
        match self.chat_focus_agent_id.as_deref() {
            Some(agent_id) => self
                .agent_states
                .get(agent_id)
                .map(|state| state.card.name.clone())
                .unwrap_or_else(|| agent_id.to_string()),
            None => "all agents".to_string(),
        }
    }

    pub fn transcript_item_visible(&self, item: &TranscriptItem) -> bool {
        let Some(focused_agent_id) = self.chat_focus_agent_id.as_deref() else {
            return true;
        };
        if item.role != TranscriptRole::Agent {
            return true;
        }
        if item
            .stream_id
            .as_deref()
            .and_then(|stream_id| stream_id.split_once(':'))
            .is_some_and(|(agent_id, _)| agent_id == focused_agent_id)
        {
            return true;
        }
        self.agent_states
            .get(focused_agent_id)
            .and_then(|state| state.card.namespace.as_deref())
            .zip(item.namespace.as_deref())
            .is_some_and(|(focused, item_namespace)| focused == item_namespace)
    }

    pub fn agent_is_focused(&self, agent_id: &str) -> bool {
        self.chat_focus_agent_id.as_deref() == Some(agent_id)
    }

    fn set_agent_focus(&mut self, query: &str) {
        let query = query.trim();
        if query.is_empty()
            || query.eq_ignore_ascii_case("all")
            || query.eq_ignore_ascii_case("none")
        {
            self.chat_focus_agent_id = None;
            self.chat_scroll_from_bottom = 0;
            self.status = "chat focus: all agents".to_string();
            return;
        }
        if query.eq_ignore_ascii_case("next") {
            self.focus_next_agent();
            return;
        }
        if query.eq_ignore_ascii_case("prev") || query.eq_ignore_ascii_case("previous") {
            self.focus_previous_agent();
            return;
        }

        let lower = query.to_lowercase();
        let exact = self.agent_states.iter().find_map(|(agent_id, state)| {
            let namespace = state.card.namespace_label();
            if agent_id.eq_ignore_ascii_case(query)
                || namespace.eq_ignore_ascii_case(query)
                || state.card.name.eq_ignore_ascii_case(query)
            {
                Some(agent_id.clone())
            } else {
                None
            }
        });
        let fuzzy = exact.or_else(|| {
            self.agent_states.iter().find_map(|(agent_id, state)| {
                let namespace = state.card.namespace_label().to_lowercase();
                let name = state.card.name.to_lowercase();
                if agent_id.to_lowercase().contains(&lower)
                    || namespace.contains(&lower)
                    || name.contains(&lower)
                {
                    Some(agent_id.clone())
                } else {
                    None
                }
            })
        });

        if let Some(agent_id) = fuzzy {
            self.chat_focus_agent_id = Some(agent_id);
            self.chat_scroll_from_bottom = 0;
            self.status = format!("chat focus: {}", self.chat_focus_label());
        } else {
            self.push_system(&format!("No agent matched `{query}`."));
        }
    }

    fn focus_next_agent(&mut self) {
        self.move_agent_focus(1);
    }

    fn focus_previous_agent(&mut self) {
        self.move_agent_focus(-1);
    }

    fn move_agent_focus(&mut self, direction: isize) {
        let focus_ids = self.agent_focus_ids();
        if focus_ids.is_empty() {
            self.chat_focus_agent_id = None;
            return;
        }
        let current_index = focus_ids
            .iter()
            .position(|agent_id| agent_id.as_deref() == self.chat_focus_agent_id.as_deref())
            .unwrap_or(0) as isize;
        let len = focus_ids.len() as isize;
        let next_index = (current_index + direction).rem_euclid(len) as usize;
        self.chat_focus_agent_id = focus_ids[next_index].clone();
        self.chat_scroll_from_bottom = 0;
        self.status = format!("chat focus: {}", self.chat_focus_label());
    }

    fn agent_focus_ids(&self) -> Vec<Option<String>> {
        std::iter::once(None)
            .chain(self.agent_states.keys().cloned().map(Some))
            .collect()
    }

    fn cycle_scroll_focus(&mut self) {
        self.scroll_focus = match self.scroll_focus {
            ScrollFocus::Chat => ScrollFocus::Architect,
            ScrollFocus::Architect => ScrollFocus::Agents,
            ScrollFocus::Agents => ScrollFocus::Chat,
        };
        self.status = format!("scroll port: {}", self.scroll_focus_label());
    }

    fn set_scroll_focus(&mut self, query: &str) {
        let focus = match query.trim().to_lowercase().as_str() {
            "" | "next" => {
                self.cycle_scroll_focus();
                return;
            }
            "chat" | "transcript" => Some(ScrollFocus::Chat),
            "architect" | "master" | "blueprint" => Some(ScrollFocus::Architect),
            "agents" | "agent" | "list" => Some(ScrollFocus::Agents),
            _ => None,
        };

        if let Some(focus) = focus {
            self.scroll_focus = focus;
            self.status = format!("scroll port: {}", self.scroll_focus_label());
        } else {
            self.push_system(&format!("No scroll port matched `{query}`."));
        }
    }

    fn scroll_up(&mut self, amount: usize) {
        match self.scroll_focus {
            ScrollFocus::Chat => {
                self.chat_scroll_from_bottom = self.chat_scroll_from_bottom.saturating_add(amount);
                self.status = "scrolling chat".to_string();
            }
            ScrollFocus::Architect => {
                self.architect_scroll = self.architect_scroll.saturating_sub(amount);
                self.status = "scrolling architect".to_string();
            }
            ScrollFocus::Agents => {
                for _ in 0..amount.max(1) {
                    self.focus_previous_agent();
                }
                self.status = format!("scrolling agents: {}", self.chat_focus_label());
            }
        }
    }

    fn scroll_down(&mut self, amount: usize) {
        match self.scroll_focus {
            ScrollFocus::Chat => {
                self.chat_scroll_from_bottom = self.chat_scroll_from_bottom.saturating_sub(amount);
                self.status = "scrolling chat".to_string();
            }
            ScrollFocus::Architect => {
                self.architect_scroll = self.architect_scroll.saturating_add(amount);
                self.status = "scrolling architect".to_string();
            }
            ScrollFocus::Agents => {
                for _ in 0..amount.max(1) {
                    self.focus_next_agent();
                }
                self.status = format!("scrolling agents: {}", self.chat_focus_label());
            }
        }
    }

    fn scroll_to_top(&mut self) {
        match self.scroll_focus {
            ScrollFocus::Chat => {
                self.chat_scroll_from_bottom = usize::MAX;
                self.status = "chat scrolled to top".to_string();
            }
            ScrollFocus::Architect => {
                self.architect_scroll = 0;
                self.status = "architect scrolled to top".to_string();
            }
            ScrollFocus::Agents => {
                self.chat_focus_agent_id = None;
                self.chat_scroll_from_bottom = 0;
                self.status = "agents scrolled to top".to_string();
            }
        }
    }

    fn scroll_to_bottom(&mut self) {
        match self.scroll_focus {
            ScrollFocus::Chat => {
                self.chat_scroll_from_bottom = 0;
                self.status = "chat scrolled to bottom".to_string();
            }
            ScrollFocus::Architect => {
                self.architect_scroll = usize::MAX;
                self.status = "architect scrolled to bottom".to_string();
            }
            ScrollFocus::Agents => {
                self.chat_focus_agent_id = self.agent_states.keys().next_back().cloned();
                self.chat_scroll_from_bottom = 0;
                self.status = format!("agents scrolled to bottom: {}", self.chat_focus_label());
            }
        }
    }

    fn accepts_master_stream(&self, stream_id: &str) -> bool {
        self.master_stream_id
            .as_ref()
            .map_or(true, |active| active == stream_id)
    }

    fn record_completed_agent(&mut self, stream_id: &str, agent_id: &str) {
        if !self.stream_matches_active_request(stream_id) {
            return;
        }
        let observation = {
            let Some(state) = self.agent_states.get(agent_id) else {
                return;
            };
            let Some(item) = self
                .transcript
                .iter()
                .find(|item| item.stream_id.as_deref() == Some(stream_id))
            else {
                return;
            };
            AgentObservation {
                agent_id: agent_id.to_string(),
                agent_name: state.card.name.clone(),
                namespace: state.card.namespace.clone(),
                body: item.body.clone(),
            }
        };

        self.record_agent_observation(stream_id, observation);
    }

    fn record_agent_observation(&mut self, stream_id: &str, observation: AgentObservation) {
        if !self.stream_matches_active_request(stream_id) {
            return;
        }
        let Some(active) = self.active_master.as_mut() else {
            return;
        };
        if active.pending_agents.remove(&observation.agent_id) {
            active
                .observations
                .insert(observation.agent_id.clone(), observation);
        }
        self.request_master_synthesis_if_ready();
    }

    fn request_master_synthesis_if_ready(&mut self) {
        let request = {
            let Some(active) = self.active_master.as_mut() else {
                return;
            };
            if !active.pending_agents.is_empty() || active.synthesis_requested {
                return;
            }
            active.synthesis_requested = true;
            Some((
                active.input.clone(),
                active.observations.values().cloned().collect::<Vec<_>>(),
            ))
        };

        if let Some((input, observations)) = request {
            let _ = self.master_sender.send(MasterJob::Synthesize {
                input,
                observations,
            });
        }
    }

    fn stream_matches_active_request(&self, stream_id: &str) -> bool {
        let Some(active) = self.active_master.as_ref() else {
            return false;
        };
        match stream_id.rsplit_once(':') {
            Some((_, created_at)) => created_at == active.input.created_at,
            None => false,
        }
    }

    fn push_agent_summary(&mut self) {
        let summary = self
            .agent_states
            .values()
            .map(|state| format!("{} ({})", state.card.name, state.card.namespace_label()))
            .collect::<Vec<_>>()
            .join(", ");
        self.push_system(&format!("{MASTER_AGENT_NAME} plus agents: {summary}"));
    }

    fn forget_agent_memory(&mut self) {
        let _ = self.master_sender.send(MasterJob::Forget);
        for sender in &self.agent_senders {
            let _ = sender.send(AgentJob::Forget);
        }
        if let Some(store) = &self.sqlite_store {
            let _ = store.clear_all_memory();
        }
        self.push_system("Agent memory cleared for this TUI session.");
    }

    fn push_system(&mut self, body: &str) {
        self.transcript.push(TranscriptItem {
            stream_id: None,
            role: TranscriptRole::System,
            author: "system".to_string(),
            namespace: None,
            body: body.to_string(),
            created_at: now_string(),
        });
    }

    fn submit_pending_initial_file(&mut self) {
        if let Some(path) = self.pending_initial_file.take() {
            self.submit_file(path);
        }
    }
}

impl Drop for ChatApp {
    fn drop(&mut self) {
        let _ = self.master_sender.send(MasterJob::Shutdown);
        for sender in &self.agent_senders {
            let _ = sender.send(AgentJob::Shutdown);
        }
    }
}

pub fn run_tui(config: AppConfig) -> Result<(), String> {
    enable_raw_mode().map_err(|error| format!("could not enable raw mode: {error}"))?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)
        .map_err(|error| format!("could not enter alternate screen: {error}"))?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal =
        Terminal::new(backend).map_err(|error| format!("terminal error: {error}"))?;

    let mut app = ChatApp::new(config);
    let result = run_loop(&mut terminal, &mut app);

    disable_raw_mode().map_err(|error| format!("could not disable raw mode: {error}"))?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)
        .map_err(|error| format!("could not leave alternate screen: {error}"))?;
    terminal
        .show_cursor()
        .map_err(|error| format!("could not show cursor: {error}"))?;

    result
}

fn run_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut ChatApp,
) -> Result<(), String> {
    while !app.should_quit {
        app.drain_agent_responses();
        terminal
            .draw(|frame| draw(frame, app))
            .map_err(|error| error.to_string())?;

        if event::poll(Duration::from_millis(80)).map_err(|error| error.to_string())? {
            if let Event::Key(key) = event::read().map_err(|error| error.to_string())? {
                app.handle_key(key);
            }
        }
    }
    Ok(())
}

fn job_id_from_stream(stream_id: &str) -> &str {
    stream_id
        .rsplit_once(':')
        .map(|(_, job_id)| job_id)
        .unwrap_or(stream_id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn name_mode_switches_to_chat() {
        let mut app = ChatApp::new(AppConfig {
            user_name: None,
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.input = "Isayah".to_string();
        app.submit_input();

        assert_eq!(app.mode, InputMode::Chat);
        assert_eq!(app.user_name, "Isayah");
    }

    #[test]
    fn first_prompt_in_name_mode_is_submitted_as_text() {
        let mut app = ChatApp::new(AppConfig {
            user_name: None,
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.input = "Hi, can you build a shoe.".to_string();
        app.submit_input();

        assert_eq!(app.mode, InputMode::Chat);
        assert_ne!(app.user_name, "Hi, can you build a shoe.");
        assert!(app.transcript.iter().any(|item| {
            item.role == TranscriptRole::User && item.body == "Hi, can you build a shoe."
        }));
    }

    #[test]
    fn first_command_in_name_mode_runs_as_command() {
        let mut app = ChatApp::new(AppConfig {
            user_name: None,
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.input = "/agents".to_string();
        app.submit_input();

        assert_eq!(app.mode, InputMode::Chat);
        assert_ne!(app.user_name, "/agents");
        assert!(app.transcript.last().unwrap().body.contains("product.mech"));
    }

    #[test]
    fn slash_agents_adds_summary() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.input = "/agents".to_string();
        app.submit_input();

        assert!(app.transcript.last().unwrap().body.contains("product.mech"));
    }

    #[test]
    fn slash_forget_clears_agent_memory() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.input = "/forget".to_string();
        app.submit_input();

        assert!(app
            .transcript
            .last()
            .unwrap()
            .body
            .contains("Agent memory cleared"));
    }

    #[test]
    fn sqlite_persists_agent_memory_from_tui_run() {
        let path = std::env::temp_dir().join(format!(
            "blueprint-tui-app-test-{}-{}.db",
            std::process::id(),
            now_string()
        ));
        let _ = std::fs::remove_file(&path);
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: Some(path.clone()),
        });

        app.submit_text("build a primitive material sample".to_string());
        for _ in 0..40 {
            app.drain_agent_responses();
            if app
                .agent_states
                .values()
                .all(|state| state.status == "responded")
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }

        let memory = SqliteStore::open(&path)
            .unwrap()
            .memory_store()
            .load("fabricator", 8)
            .unwrap();
        assert_eq!(memory.len(), 1);
        assert!(memory[0].user_summary.contains("primitive material"));

        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("db-wal"));
        let _ = std::fs::remove_file(path.with_extension("db-shm"));
    }

    #[test]
    fn master_synthesizes_after_agents_finish() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.submit_text("build me a cardboard like material for a robot arm".to_string());
        for _ in 0..80 {
            app.drain_agent_responses();
            if app.master_status == "final ready" {
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }

        assert!(app.master_notes.contains("Routing"));
        assert!(app.master_final.contains("final output"));
        assert!(app.master_final.contains("Top namespace signals"));
    }

    #[test]
    fn slash_agent_focus_filters_transcript() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        app.submit_text("build a waterproof shoe".to_string());
        for _ in 0..40 {
            app.drain_agent_responses();
            if app
                .agent_states
                .values()
                .all(|state| state.status == "responded")
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }

        app.input = "/agent product.bom".to_string();
        app.submit_input();

        assert_eq!(app.chat_focus_agent_id.as_deref(), Some("product.bom"));
        assert_eq!(app.chat_focus_label(), "Product BOM Agent");
        let visible_agent_authors = app
            .transcript
            .iter()
            .filter(|item| item.role == TranscriptRole::Agent)
            .filter(|item| app.transcript_item_visible(item))
            .map(|item| item.author.as_str())
            .collect::<Vec<_>>();
        assert_eq!(visible_agent_authors, vec!["Product BOM Agent"]);
    }

    #[test]
    fn tab_focus_cycles_agents() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        assert_eq!(app.chat_focus_agent_id, None);
        app.focus_next_agent();
        assert_eq!(app.chat_focus_agent_id.as_deref(), Some("fabricator"));
        app.focus_previous_agent();
        assert_eq!(app.chat_focus_agent_id, None);
    }

    #[test]
    fn scroll_port_keys_scroll_active_panel() {
        let mut app = ChatApp::new(AppConfig {
            user_name: Some("Isayah".to_string()),
            mcp_url: None,
            initial_file: None,
            openai: OpenAiConfig::offline(),
            sqlite_path: None,
        });

        assert_eq!(app.scroll_focus, ScrollFocus::Chat);
        app.handle_key(KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE));
        assert_eq!(app.chat_scroll_from_bottom, 8);
        app.handle_key(KeyEvent::new(KeyCode::PageDown, KeyModifiers::NONE));
        assert_eq!(app.chat_scroll_from_bottom, 0);

        app.handle_key(KeyEvent::new(KeyCode::F(2), KeyModifiers::NONE));
        assert_eq!(app.scroll_focus, ScrollFocus::Architect);
        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
        assert_eq!(app.architect_scroll, 1);
        app.handle_key(KeyEvent::new(KeyCode::Up, KeyModifiers::NONE));
        assert_eq!(app.architect_scroll, 0);

        app.input = "/scroll agents".to_string();
        app.submit_input();
        assert_eq!(app.scroll_focus, ScrollFocus::Agents);
    }
}
