use iced::widget::{Button, Column, Container, Row, Scrollable, Text};
use iced::{Element, Length, Sandbox, Settings};
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
}

#[derive(Debug, Clone)]
enum Message {
    LoadTopStories,
    LoadNewStories,
    OpenStory(String),
}

impl Sandbox for HNBrowser {
    type Message = Message;

    fn new() -> Self {
        Self {
            stories: vec![
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
            ],
            tab: Tab::Top,
        }
    }

    fn title(&self) -> String {
        String::from("zzview - Hacker News Browser")
    }

    fn update(&mut self, message: Message) {
        match message {
            Message::LoadTopStories => {
                self.tab = Tab::Top;
                // Top stories already loaded on init
            }
            Message::LoadNewStories => {
                self.tab = Tab::New;
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
            }
            Message::OpenStory(url) => {
                let _ = Command::new("open")
                    .arg(&url)
                    .output()
                    .or_else(|_| Command::new("xdg-open").arg(&url).output())
                    .or_else(|_| Command::new("cmd").args(&["/C", "start", &url]).output());
            }
        }
    }

    fn view(&self) -> Element<Message> {
        let header = Column::new()
            .push(Text::new("zzview").size(32))
            .push(Text::new("Hacker News Browser").size(14))
            .spacing(4);

        let top_btn = Button::new(Text::new("Top Stories").size(13))
            .on_press(Message::LoadTopStories)
            .padding(6);

        let new_btn = Button::new(Text::new("Newest").size(13))
            .on_press(Message::LoadNewStories)
            .padding(6);

        let tab_row = Row::new().push(top_btn).push(new_btn).spacing(8).padding(10);

        let mut story_list = Column::new().spacing(6);

        for story in &self.stories {
            let score_text = format!(
                "{}. {} pts | {} comments",
                story.rank, story.score, story.comments
            );

            let title_row = if let Some(ref url) = story.url {
                let url_clone = url.clone();
                Button::new(
                    Column::new()
                        .push(Text::new(&story.title).size(13))
                        .push(Text::new(score_text).size(11))
                        .spacing(2),
                )
                .on_press(Message::OpenStory(url_clone))
                .padding(6)
                .into()
            } else {
                Column::new()
                    .push(Text::new(&story.title).size(13))
                    .push(Text::new(score_text).size(11))
                    .spacing(2)
                    .into()
            };

            story_list = story_list.push(title_row);
        }

        let content = Column::new()
            .push(header)
            .push(tab_row)
            .push(Scrollable::new(story_list).height(Length::Fill))
            .spacing(10)
            .padding(14);

        Container::new(content)
            .width(Length::Fill)
            .height(Length::Fill)
            .into()
    }
}

fn main() -> iced::Result {
    HNBrowser::run(Settings::default())
}
