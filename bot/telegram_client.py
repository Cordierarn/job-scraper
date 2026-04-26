from __future__ import annotations

import os
import time
import requests

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram limit is 4096 — leave headroom for safety


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, *, disable_preview: bool = True) -> bool:
        if not self.configured():
            print(f"[telegram] non configuré — message ignoré:\n{text[:200]}")
            return False
        # Chunk long messages on blank lines.
        for chunk in chunk_text(text, MAX_LEN):
            r = requests.post(
                API.format(token=self.token, method="sendMessage"),
                data={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true" if disable_preview else "false",
                },
                timeout=20,
            )
            if r.status_code != 200:
                print(f"[telegram] erreur {r.status_code}: {r.text[:200]}")
                return False
            time.sleep(0.4)  # respect rate limit (~30 msg/sec, but be polite)
        return True


def chunk_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            # Paragraph itself too big → hard split.
            while len(paragraph) > limit:
                chunks.append(paragraph[:limit])
                paragraph = paragraph[limit:]
        current += paragraph + "\n\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks
