use crate::app::{ChatApp, InputMode, ScrollFocus, TranscriptRole};
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

pub fn draw(frame: &mut Frame, app: &ChatApp) {
    let root = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(8),
            Constraint::Length(3),
            Constraint::Length(1),
        ])
        .split(frame.area());

    let title = Paragraph::new(vec![Line::from(vec![
        Span::styled(
            "Blueprint TUI",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw("  Architect synthesis with independent namespace agents"),
    ])])
    .block(Block::default().borders(Borders::ALL).title("status"));
    frame.render_widget(title, root[0]);

    let body = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(62), Constraint::Percentage(38)])
        .split(root[1]);

    let side = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(48), Constraint::Percentage(52)])
        .split(body[1]);

    let chat_width = body[0].width.saturating_sub(2).max(1) as usize;
    let chat_height = body[0].height.saturating_sub(2) as usize;
    let mut transcript_lines = Vec::new();

    for item in app
        .transcript
        .iter()
        .filter(|item| app.transcript_item_visible(item))
        .rev()
        .take(200)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
    {
        let style = match item.role {
            TranscriptRole::System => Style::default().fg(Color::DarkGray),
            TranscriptRole::User => Style::default().fg(Color::Green),
            TranscriptRole::Agent => Style::default().fg(Color::White),
        };
        let namespace = item
            .namespace
            .as_ref()
            .map(|value| format!(" [{value}]"))
            .unwrap_or_default();
        transcript_lines.push(Line::from(vec![
            Span::styled(
                format!("{}{}", item.author, namespace),
                style.add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!(" @{}", item.created_at),
                Style::default().fg(Color::DarkGray),
            ),
        ]));
        push_wrapped_lines(&mut transcript_lines, &item.body, style, chat_width);
        transcript_lines.push(Line::from(""));
    }

    let chat_scroll = app.chat_scroll_from_bottom;
    transcript_lines = tail_window(transcript_lines, chat_height, chat_scroll);

    let transcript = Paragraph::new(transcript_lines)
        .block(Block::default().borders(Borders::ALL).title(format!(
            "chat: {}{}",
            app.chat_focus_label(),
            scroll_title_marker(app.scroll_focus == ScrollFocus::Chat)
        )))
        .wrap(Wrap { trim: false });
    frame.render_widget(transcript, body[0]);

    let notes = if app.master_notes.trim().is_empty() {
        "waiting for a prompt".to_string()
    } else {
        app.master_notes.clone()
    };
    let final_output = if app.master_final.trim().is_empty() {
        "final output appears after the namespace agents finish".to_string()
    } else {
        app.master_final.clone()
    };
    let master_width = side[0].width.saturating_sub(2).max(1) as usize;
    let master_height = side[0].height.saturating_sub(2) as usize;
    let mut master_lines = vec![Line::from(vec![
        Span::styled("status: ", Style::default().fg(Color::DarkGray)),
        Span::styled(app.master_status.clone(), Style::default().fg(Color::Green)),
    ])];
    master_lines.push(Line::from(""));
    master_lines.push(Line::from(Span::styled(
        "working notes",
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));
    push_wrapped_lines(
        &mut master_lines,
        &notes,
        Style::default().fg(Color::White),
        master_width,
    );
    master_lines.push(Line::from(""));
    master_lines.push(Line::from(Span::styled(
        "final output",
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));
    push_wrapped_lines(
        &mut master_lines,
        &final_output,
        Style::default().fg(Color::White),
        master_width,
    );
    master_lines = top_window(master_lines, master_height, app.architect_scroll);
    let master =
        Paragraph::new(master_lines).block(Block::default().borders(Borders::ALL).title(format!(
            "Blueprint Architect{}",
            scroll_title_marker(app.scroll_focus == ScrollFocus::Architect)
        )));
    frame.render_widget(master, side[0]);

    let mut agents: Vec<ListItem> = Vec::new();
    let all_focused = app.chat_focus_agent_id.is_none();
    let all_style = if all_focused {
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(Color::DarkGray)
    };
    agents.push(ListItem::new(vec![
        Line::from(vec![
            Span::styled(if all_focused { "> " } else { "  " }, all_style),
            Span::styled("All Agents", all_style),
        ]),
        Line::from(Span::styled(
            "combined transcript",
            Style::default().fg(Color::DarkGray),
        )),
        Line::from(""),
    ]));

    agents.extend(
        app.agent_states
            .values()
            .map(|state| {
                let focused = app.agent_is_focused(&state.card.agent_id);
                let color = match state.status.as_str() {
                    "thinking" => Color::Yellow,
                    "streaming" => Color::Cyan,
                    "responded" => Color::Green,
                    "error" => Color::Red,
                    _ => Color::Blue,
                };
                let last = if state.last_message.is_empty() {
                    state.card.summary.clone()
                } else {
                    truncate(&state.last_message, 160)
                };
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled(
                            if focused { "> " } else { "  " },
                            Style::default().fg(if focused {
                                Color::Yellow
                            } else {
                                Color::DarkGray
                            }),
                        ),
                        Span::styled(
                            state.card.name.clone(),
                            Style::default()
                                .fg(if focused { Color::Yellow } else { Color::Cyan })
                                .add_modifier(Modifier::BOLD),
                        ),
                        Span::raw(" "),
                        Span::styled(state.status.clone(), Style::default().fg(color)),
                    ]),
                    Line::from(Span::styled(
                        state.card.namespace_label().to_string(),
                        Style::default().fg(Color::Magenta),
                    )),
                    Line::from(Span::raw(last)),
                    Line::from(""),
                ])
            })
            .collect::<Vec<_>>(),
    );

    let selected_agent_index = app
        .chat_focus_agent_id
        .as_deref()
        .and_then(|focused_agent_id| {
            app.agent_states
                .keys()
                .position(|agent_id| agent_id == focused_agent_id)
                .map(|index| index + 1)
        })
        .unwrap_or(0);
    let mut agents_state = ListState::default().with_selected(Some(selected_agent_index));
    let agents = List::new(agents)
        .block(Block::default().borders(Borders::ALL).title(format!(
            "agents{}",
            scroll_title_marker(app.scroll_focus == ScrollFocus::Agents)
        )))
        .scroll_padding(1);
    frame.render_stateful_widget(agents, side[1], &mut agents_state);

    let prompt = match app.mode {
        InputMode::Name => "name or first prompt",
        InputMode::Chat => "message | F2 scroll port | Up/Down scroll | Tab agent | /quit",
    };
    let input = Paragraph::new(app.input.as_str())
        .block(Block::default().borders(Borders::ALL).title(prompt))
        .wrap(Wrap { trim: false });
    frame.render_widget(input, root[2]);

    let cursor_x = root[2].x + app.input.len() as u16 + 1;
    let cursor_y = root[2].y + 1;
    frame.set_cursor_position((cursor_x.min(root[2].right().saturating_sub(2)), cursor_y));

    let footer = Paragraph::new(format!(
        "{} | scroll port: {} | PgUp/PgDn Home/End | Ctrl-Q exits",
        app.status,
        app.scroll_focus_label()
    ))
    .style(Style::default().fg(Color::DarkGray));
    frame.render_widget(footer, root[3]);
}

fn truncate(value: &str, max_chars: usize) -> String {
    if value.chars().count() <= max_chars {
        return value.to_string();
    }
    let mut truncated: String = value.chars().take(max_chars.saturating_sub(3)).collect();
    truncated.push_str("...");
    truncated
}

fn push_wrapped_lines(lines: &mut Vec<Line<'static>>, value: &str, style: Style, width: usize) {
    for raw_line in value.split('\n') {
        if raw_line.is_empty() {
            lines.push(Line::from(""));
            continue;
        }

        let mut line = String::new();
        for character in raw_line.chars() {
            line.push(character);
            if line.chars().count() >= width {
                lines.push(Line::from(Span::styled(line.clone(), style)));
                line.clear();
            }
        }
        if !line.is_empty() {
            lines.push(Line::from(Span::styled(line, style)));
        }
    }
}

fn tail_window(
    lines: Vec<Line<'static>>,
    height: usize,
    scroll_from_bottom: usize,
) -> Vec<Line<'static>> {
    if height == 0 || lines.is_empty() {
        return Vec::new();
    }
    let max_scroll = lines.len().saturating_sub(height);
    let scroll = scroll_from_bottom.min(max_scroll);
    let end = lines.len().saturating_sub(scroll);
    let start = end.saturating_sub(height);
    lines.into_iter().skip(start).take(end - start).collect()
}

fn top_window(lines: Vec<Line<'static>>, height: usize, scroll: usize) -> Vec<Line<'static>> {
    if height == 0 || lines.is_empty() {
        return Vec::new();
    }
    let max_scroll = lines.len().saturating_sub(height);
    let start = scroll.min(max_scroll);
    lines.into_iter().skip(start).take(height).collect()
}

fn scroll_title_marker(active: bool) -> &'static str {
    if active {
        " [scroll]"
    } else {
        ""
    }
}
