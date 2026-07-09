use assert_cmd::Command;
use predicates::prelude::*;
use serde_json::Value;

#[test]
fn emit_prints_one_jsonl_event() {
    let output = Command::cargo_bin("blueprint-edge")
        .expect("binary should build")
        .args([
            "emit",
            "--source-type",
            "unit",
            "--name",
            "demo",
            "--kind",
            "unit.event",
            "--payload",
            r#"{"value":42}"#,
        ])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();

    let text = String::from_utf8(output).expect("stdout should be utf8");
    let parsed: Value =
        serde_json::from_str(text.trim()).expect("stdout should be one JSON object");
    assert_eq!(parsed["kind"], "unit.event");
    assert_eq!(parsed["source"]["source_type"], "unit");
    assert_eq!(parsed["payload"]["value"], 42);
}

#[test]
fn stdin_prints_one_event_per_input_line() {
    Command::cargo_bin("blueprint-edge")
        .expect("binary should build")
        .args(["stdin", "--name", "unit-lines"])
        .write_stdin("first\nsecond\n")
        .assert()
        .success()
        .stdout(predicate::str::contains("\"line\":\"first\""))
        .stdout(predicate::str::contains("\"line\":\"second\""));
}

#[test]
fn mcp_command_responds_to_framed_tools_list() {
    let body = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;
    let frame = format!("Content-Length: {}\r\n\r\n{}", body.len(), body);

    Command::cargo_bin("blueprint-edge")
        .expect("binary should build")
        .args(["mcp"])
        .write_stdin(frame)
        .assert()
        .success()
        .stdout(predicate::str::contains("Content-Length:"))
        .stdout(predicate::str::contains("edge.config.get"));
}
