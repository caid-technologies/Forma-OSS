use rusqlite::{params, Connection, OptionalExtension};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct SqliteStore {
    path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct AgentMemoryStore {
    path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredMemoryTurn {
    pub user_summary: String,
    pub response_summary: String,
    pub created_at: String,
}

impl SqliteStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let store = Self {
            path: path.as_ref().to_path_buf(),
        };
        store.init()?;
        Ok(store)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn memory_store(&self) -> AgentMemoryStore {
        AgentMemoryStore {
            path: self.path.clone(),
        }
    }

    pub fn init(&self) -> Result<(), String> {
        if let Some(parent) = self
            .path
            .parent()
            .filter(|path| !path.as_os_str().is_empty())
        {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("could not create SQLite directory: {error}"))?;
        }
        let conn = self.connect()?;
        apply_pragmas(&conn)?;
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS tui_jobs (
                job_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL,
                input_kind TEXT NOT NULL,
                source_path TEXT,
                byte_len INTEGER,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tui_agent_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                namespace TEXT,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tui_agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                namespace TEXT,
                user_summary TEXT NOT NULL,
                response_summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tui_jobs_status ON tui_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_tui_jobs_created_at ON tui_jobs(created_at);
            CREATE INDEX IF NOT EXISTS idx_tui_agent_responses_job ON tui_agent_responses(job_id);
            CREATE INDEX IF NOT EXISTS idx_tui_agent_memory_agent ON tui_agent_memory(agent_id, id);
            ",
        )
        .map_err(|error| format!("could not initialize SQLite schema: {error}"))?;
        Ok(())
    }

    pub fn record_job(
        &self,
        job_id: &str,
        user_name: &str,
        input_kind: &str,
        source_path: Option<&str>,
        byte_len: Option<usize>,
        body: &str,
        created_at: &str,
    ) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute(
            "
            INSERT OR REPLACE INTO tui_jobs (
                job_id, user_name, input_kind, source_path, byte_len, body, status, created_at, updated_at
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'running', ?7, ?7)
            ",
            params![
                job_id,
                user_name,
                input_kind,
                source_path,
                byte_len.map(|value| value as i64),
                body,
                created_at
            ],
        )
        .map_err(|error| format!("could not record SQLite job: {error}"))?;
        Ok(())
    }

    pub fn set_job_status(
        &self,
        job_id: &str,
        status: &str,
        updated_at: &str,
    ) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute(
            "UPDATE tui_jobs SET status = ?1, updated_at = ?2 WHERE job_id = ?3",
            params![status, updated_at, job_id],
        )
        .map_err(|error| format!("could not update SQLite job status: {error}"))?;
        Ok(())
    }

    pub fn record_agent_response(
        &self,
        job_id: &str,
        agent_id: &str,
        agent_name: &str,
        namespace: Option<&str>,
        body: &str,
        status: &str,
        created_at: &str,
    ) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute(
            "
            INSERT INTO tui_agent_responses (
                job_id, agent_id, agent_name, namespace, body, status, created_at
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
            ",
            params![job_id, agent_id, agent_name, namespace, body, status, created_at],
        )
        .map_err(|error| format!("could not record SQLite agent response: {error}"))?;
        Ok(())
    }

    pub fn clear_all_memory(&self) -> Result<(), String> {
        self.memory_store().clear_all()
    }

    fn connect(&self) -> Result<Connection, String> {
        Connection::open(&self.path).map_err(|error| {
            format!(
                "could not open SQLite DB `{}`: {error}",
                self.path.display()
            )
        })
    }
}

impl AgentMemoryStore {
    pub fn load(&self, agent_id: &str, limit: usize) -> Result<Vec<StoredMemoryTurn>, String> {
        let conn = self.connect()?;
        let mut statement = conn
            .prepare(
                "
                SELECT user_summary, response_summary, created_at
                FROM tui_agent_memory
                WHERE agent_id = ?1
                ORDER BY id DESC
                LIMIT ?2
                ",
            )
            .map_err(|error| format!("could not prepare SQLite memory load: {error}"))?;
        let rows = statement
            .query_map(params![agent_id, limit as i64], |row| {
                Ok(StoredMemoryTurn {
                    user_summary: row.get(0)?,
                    response_summary: row.get(1)?,
                    created_at: row.get(2)?,
                })
            })
            .map_err(|error| format!("could not query SQLite memory: {error}"))?;

        let mut turns = rows
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| format!("could not read SQLite memory row: {error}"))?;
        turns.reverse();
        Ok(turns)
    }

    pub fn remember(
        &self,
        agent_id: &str,
        agent_name: &str,
        namespace: Option<&str>,
        user_summary: &str,
        response_summary: &str,
        created_at: &str,
    ) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute(
            "
            INSERT INTO tui_agent_memory (
                agent_id, agent_name, namespace, user_summary, response_summary, created_at
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ",
            params![
                agent_id,
                agent_name,
                namespace,
                user_summary,
                response_summary,
                created_at
            ],
        )
        .map_err(|error| format!("could not persist SQLite agent memory: {error}"))?;

        let cutoff_id: Option<i64> = conn
            .query_row(
                "
                SELECT id
                FROM tui_agent_memory
                WHERE agent_id = ?1
                ORDER BY id DESC
                LIMIT 1 OFFSET 7
                ",
                params![agent_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|error| format!("could not trim SQLite memory: {error}"))?;
        if let Some(cutoff_id) = cutoff_id {
            conn.execute(
                "DELETE FROM tui_agent_memory WHERE agent_id = ?1 AND id < ?2",
                params![agent_id, cutoff_id],
            )
            .map_err(|error| format!("could not delete old SQLite memory: {error}"))?;
        }
        Ok(())
    }

    pub fn clear_agent(&self, agent_id: &str) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute(
            "DELETE FROM tui_agent_memory WHERE agent_id = ?1",
            params![agent_id],
        )
        .map_err(|error| format!("could not clear SQLite agent memory: {error}"))?;
        Ok(())
    }

    pub fn clear_all(&self) -> Result<(), String> {
        let conn = self.connect()?;
        conn.execute("DELETE FROM tui_agent_memory", [])
            .map_err(|error| format!("could not clear SQLite memory: {error}"))?;
        Ok(())
    }

    fn connect(&self) -> Result<Connection, String> {
        let conn = Connection::open(&self.path).map_err(|error| {
            format!(
                "could not open SQLite DB `{}` for memory: {error}",
                self.path.display()
            )
        })?;
        apply_pragmas(&conn)?;
        Ok(conn)
    }
}

fn apply_pragmas(conn: &Connection) -> Result<(), String> {
    conn.pragma_update(None, "journal_mode", "WAL")
        .map_err(|error| format!("could not enable SQLite WAL mode: {error}"))?;
    conn.pragma_update(None, "synchronous", "NORMAL")
        .map_err(|error| format!("could not set SQLite synchronous mode: {error}"))?;
    conn.busy_timeout(std::time::Duration::from_secs(5))
        .map_err(|error| format!("could not set SQLite busy timeout: {error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sqlite_memory_round_trips_and_trims() {
        let path =
            std::env::temp_dir().join(format!("blueprint-tui-test-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let store = SqliteStore::open(&path).unwrap();
        let memory = store.memory_store();

        for index in 0..10 {
            memory
                .remember(
                    "fabricator",
                    "Fabricator",
                    Some("product.fabricator"),
                    &format!("user {index}"),
                    &format!("agent {index}"),
                    &format!("time-{index}"),
                )
                .unwrap();
        }

        let turns = memory.load("fabricator", 8).unwrap();
        assert_eq!(turns.len(), 8);
        assert_eq!(turns.first().unwrap().user_summary, "user 2");
        assert_eq!(turns.last().unwrap().response_summary, "agent 9");

        let _ = std::fs::remove_file(&path);
    }
}
