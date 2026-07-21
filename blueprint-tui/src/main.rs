use blueprint_tui::{run_tui, AppConfig, OpenAiConfig};
use clap::Parser;
use std::env;
use std::path::PathBuf;

#[derive(Debug, Parser)]
#[command(name = "blueprint-tui")]
#[command(about = "Terminal chatbot for Forma Lattice namespace agents.")]
struct Cli {
    /// User name to skip the startup name prompt.
    #[arg(long)]
    name: Option<String>,

    /// Optional Forma MCP HTTP endpoint, for example http://127.0.0.1:8000/api/mcp.
    #[arg(long)]
    mcp_url: Option<String>,

    /// Optional file to submit after the user name is known.
    #[arg(long)]
    file: Option<PathBuf>,

    /// Stream each namespace agent through OpenAI instead of offline local replies.
    #[arg(long)]
    openai: bool,

    /// OpenAI model to use when --openai is set. Defaults to OPENAI_MODEL from .env, then gpt-4o-mini.
    #[arg(long)]
    openai_model: Option<String>,

    /// OpenAI-compatible base URL.
    #[arg(long, default_value = "https://api.openai.com/v1")]
    openai_base_url: String,

    /// Fallback OpenAI model used when the configured model is unavailable.
    #[arg(long)]
    openai_fallback_model: Option<String>,

    /// Local SQLite DB path for TUI jobs and persistent agent memory.
    #[arg(long)]
    sqlite_path: Option<PathBuf>,

    /// Disable local SQLite persistence.
    #[arg(long)]
    no_sqlite: bool,
}

fn main() {
    let _ = dotenvy::dotenv();
    let cli = Cli::parse();
    let openai_model = cli
        .openai_model
        .or_else(|| env::var("OPENAI_MODEL").ok())
        .or_else(|| env::var("OPENAI_STREAM_MODEL").ok())
        .unwrap_or_else(|| "gpt-4o-mini".to_string());
    let openai_fallback_model = cli
        .openai_fallback_model
        .or_else(|| env::var("OPENAI_FALLBACK_MODEL").ok())
        .unwrap_or_else(|| "gpt-4o-mini".to_string());
    let sqlite_path = if cli.no_sqlite {
        None
    } else {
        cli.sqlite_path
            .or_else(|| env::var("BLUEPRINT_TUI_DB_PATH").ok().map(PathBuf::from))
            .or_else(|| Some(PathBuf::from("blueprint_tui.db")))
    };
    if let Err(error) = run_tui(AppConfig {
        user_name: cli.name,
        mcp_url: cli.mcp_url,
        initial_file: cli.file,
        sqlite_path,
        openai: OpenAiConfig {
            enabled: cli.openai,
            api_key: env::var("OPENAI_API_KEY").ok(),
            model: openai_model,
            fallback_model: openai_fallback_model,
            base_url: cli.openai_base_url,
        },
    }) {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
