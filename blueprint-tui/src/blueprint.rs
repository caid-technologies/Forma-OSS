use crate::agents::{AgentCard, FormaMcpContext, FormaMcpTool};
use reqwest::blocking::Client;
use serde_json::{json, Value};
use std::time::Duration;

pub fn fetch_lattice_agents(mcp_url: &str) -> Result<Vec<AgentCard>, String> {
    let client = Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .map_err(|error| format!("could not build HTTP client: {error}"))?;

    let payload = json!({
        "jsonrpc": "2.0",
        "id": "blueprint-tui-lattice",
        "method": "tools/call",
        "params": {
            "name": "blueprint.lattice.list_agents",
            "arguments": {}
        }
    });

    let response: Value = client
        .post(mcp_url)
        .json(&payload)
        .send()
        .map_err(|error| format!("could not reach Forma MCP at {mcp_url}: {error}"))?
        .json()
        .map_err(|error| format!("Forma MCP returned invalid JSON: {error}"))?;

    if let Some(error) = response.get("error") {
        return Err(format!("Forma MCP error: {error}"));
    }

    let agents = response
        .pointer("/result/structuredContent/agents")
        .cloned()
        .ok_or_else(|| "Forma MCP response did not include Lattice agents".to_string())?;

    serde_json::from_value(agents)
        .map_err(|error| format!("could not parse Lattice agent cards: {error}"))
}

pub fn fetch_agent_mcp_context(
    mcp_url: &str,
    card: Option<&AgentCard>,
) -> Result<FormaMcpContext, String> {
    let tools = fetch_mcp_tools(mcp_url)?;
    let agent_card = match card {
        Some(card)
            if tools
                .iter()
                .any(|tool| tool.name == "blueprint.lattice.get_agent_card") =>
        {
            fetch_mcp_agent_card(mcp_url, &card.agent_id).ok()
        }
        _ => None,
    };

    Ok(FormaMcpContext {
        url: Some(mcp_url.to_string()),
        tools,
        agent_card,
        error: None,
    })
}

pub fn fetch_mcp_tools(mcp_url: &str) -> Result<Vec<FormaMcpTool>, String> {
    let payload = json!({
        "jsonrpc": "2.0",
        "id": "blueprint-tui-tools",
        "method": "tools/list",
        "params": {}
    });
    let response = post_mcp_json_rpc(mcp_url, payload)?;
    if let Some(error) = response.get("error") {
        return Err(format!("Forma MCP error: {error}"));
    }
    let tools = response
        .pointer("/result/tools")
        .cloned()
        .ok_or_else(|| "Forma MCP response did not include tools".to_string())?;
    serde_json::from_value(tools)
        .map_err(|error| format!("could not parse Forma MCP tools: {error}"))
}

pub fn fetch_mcp_agent_card(mcp_url: &str, agent_id: &str) -> Result<AgentCard, String> {
    let payload = json!({
        "jsonrpc": "2.0",
        "id": format!("blueprint-tui-card-{agent_id}"),
        "method": "tools/call",
        "params": {
            "name": "blueprint.lattice.get_agent_card",
            "arguments": {"agent_id": agent_id}
        }
    });
    let response = post_mcp_json_rpc(mcp_url, payload)?;
    if let Some(error) = response.get("error") {
        return Err(format!("Forma MCP error: {error}"));
    }
    let card = response
        .pointer("/result/structuredContent/agent")
        .cloned()
        .ok_or_else(|| "Forma MCP response did not include an agent card".to_string())?;
    serde_json::from_value(card)
        .map_err(|error| format!("could not parse Forma MCP agent card: {error}"))
}

fn post_mcp_json_rpc(mcp_url: &str, payload: Value) -> Result<Value, String> {
    let client = Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|error| format!("could not build HTTP client: {error}"))?;

    client
        .post(mcp_url)
        .json(&payload)
        .send()
        .map_err(|error| format!("could not reach Forma MCP at {mcp_url}: {error}"))?
        .json()
        .map_err(|error| format!("Forma MCP returned invalid JSON: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_lattice_agent_shape() {
        let value = json!({
            "agent_id": "product.bom",
            "namespace": "product.bom",
            "name": "Product BOM Agent",
            "domain": "Bill of materials",
            "summary": "Costs and sourcing",
            "capabilities": [{"id": "product.bom.update", "label": "BOM"}]
        });

        let card: AgentCard = serde_json::from_value(value).unwrap();

        assert_eq!(card.agent_id, "product.bom");
        assert_eq!(card.namespace.as_deref(), Some("product.bom"));
    }
}
