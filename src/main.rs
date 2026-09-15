// zzview - Cross-platform Hacker News browser
// Built with iced 0.12 (GUI) + reqwest (HTTP) + tokio (async runtime)

use iced::widget::{Button, Column, Container, Row, Scrollable, Text};
use iced::{Alignment, Element, Length, Sandbox, Settings};

use serde_json::Value;
use std::process::Command;

#[derive(Clone, Debug)]
struct Story {
    id: u64,
    rank: usize,
    title: String,
    score: u32,
    comments: u32,
    url: Option<String>,
}

#[derive(Clone, Debug)]
enum Tab {
    Top,
    New,
}

struct HNBrowser {
    stories: Vec<Story>,
    tab: Tab,
    loading: bool,
}

#[derive(Debug, Clone)]
enum Message {
    LoadTopStories,
    LoadNewStories,
    StoriesLoaded(Vec<Story>),
    OpenStory(String),
}

impl Sandbox for HNBrowser {
    type Message = Message;

    fn new() -> Self {
        Self {
            stories: Vec::new(),
            tab: Tab::Top,
            loading: false,
        }
    }

    fn title(&self) -> String {
        String::from("zzview - Hacker News Browser")
    }

    fn update(&mut self, message: Message) {
        match message {
            Message::LoadTopStories => {
                self.tab = Tab::Top;
                self.loading = true;
                std::thread::spawn(|| {
                    if let Ok(stories) = fetch_stories("topstories") {
                        // In a real app, we'd use a channel to send this back
                        // For now, just print to verify the fetch works
                    }
                });
                // Mock data for demo
                self.stories = vec![
                    Story {
                        id: 41234567,
                        rank: 1,
                        title: "Show HN: Cross-Platform Desktop App with Rust".to_string(),
                        score: 842,
                        comments: 156,
                        url: Some("https://github.com".to_string()),
                    },
                    Story {
                        id: 41234566,
                        rank: 2,
                        title: "Understanding WebAssembly in 2026".to_string(),
                        score: 721,
                        comments: 234,
                        url: Some("https://example.com".to_string()),
                    },
                    Story {
                        id: 41234565,
                        rank: 3,
                        title: "The Future of AI Compilers".to_string(),
                        score: 612,
                        comments: 178,
                        url: Some("https://example.com".to_string()),
                    },
                    Story {
                        id: 41234564,
                        rank: 4,
                        title: "Rust Ownership: The Good Parts".to_string(),
                        score: 543,
                        comments: 92,
                        url: Some("https://example.com".to_string()),
                    },
                    Story {
                        id: 41234563,
                        rank: 5,
                        title: "Why Node.js Developers Migrate to Rust".to_string(),
                        score: 498,
                        comments: 145,
                        url: Some("https://example.com".to_string()),
                    },
                ];
                self.loading = false;
            }
            Message::LoadNewStories => {
                self.tab = Tab::New;
                self.loading = true;
                // Mock data for demo
                self.stories = vec![
                    Story {
                        id: 41235001,
                        rank: 1,
                        title: "Just launched: zzview HN browser".to_string(),
                        score: 12,
                        comments: 3,
                        url: Some("https://example.com".to_string()),
                    },
                    Story {
                        id: 41234998,
                        rank: 2,
                        title: "Ask HN: Best Rust frameworks for 2026?".to_string(),
                        score: 8,
                        comments: 5,
                        url: Some("https://example.com".to_string()),
                    },
                    Story {
                        id: 41234997,
                        rank: 3,
                        title: "Show HN: My first Electron app replacement".to_string(),
                        score: 5,
                        comments: 2,
                        url: Some("https://example.com".to_string()),
                    },
                ];
                self.loading = false;
            }
            Message::StoriesLoaded(stories) => {
                self.stories = stories;
                self.loading = false;
            }
            Message::OpenStory(url) => {
                let _ = Command::new("open")
                    .arg(&url)
                    .output()
                    .or_else(|_| {
                        Command::new("xdg-open")
                            .arg(&url)
                            .output()
                    })
                    .or_else(|_| {
                        Command::new("cmd")
                            .args(&["/C", "start", &url])
                            .output()
                    });
            }
        }
    }

    fn view(&self) -> Element<Message> {
        let header = Column::new()
            .push(Text::new("zzview").size(36))
            .push(Text::new("Hacker News Browser").size(16))
            .spacing(4);

        let top_btn = Button::new(Text::new("Top Stories").size(14))
            .on_press(Message::LoadTopStories)
            .padding(8);

        let new_btn = Button::new(Text::new("Newest").size(14))
            .on_press(Message::LoadNewStories)
            .padding(8);

        let tab_row = Row::new()
            .push(top_btn)
            .push(new_btn)
            .spacing(10)
            .padding(10);

        let mut story_list = Column::new().spacing(8);

        if self.stories.is_empty() {
            story_list = story_list.push(Text::new("Click 'Top Stories' or 'Newest' to load..."));
        } else {
            for story in &self.stories {
                let rank_text = format!("{}. ", story.rank);
                let score_text = format!("[{} pts | {} comments]", story.score, story.comments);

                let title = if let Some(ref url) = story.url {
                    let url_clone = url.clone();
                    Button::new(
                        Text::new(format!("{}{}\n{}", rank_text, story.title, score_text))
                            .size(14),
                    )
                    .on_press(Message::OpenStory(url_clone))
                    .padding(8)
                    .into()
                } else {
                    Text::new(format!("{}{}\n{}", rank_text, story.title, score_text))
                        .size(14)
                        .into()
                };

                story_list = story_list.push(title);
            }
        }

        let content = Column::new()
            .push(header)
            .push(tab_row)
            .push(Scrollable::new(story_list).height(Length::Fill))
            .spacing(12)
            .padding(16);

        Container::new(content)
            .width(Length::Fill)
            .height(Length::Fill)
            .center_x()
            .into()
    }
}

fn fetch_stories(story_type: &str) -> Result<Vec<Story>, Box<dyn std::error::Error>> {
    // This would make real HTTP requests in an async context
    // For now, just a placeholder
    Ok(Vec::new())
}

fn main() -> iced::Result {
    HNBrowser::run(Settings::default())
}
