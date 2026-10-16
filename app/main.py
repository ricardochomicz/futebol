import os
import secrets

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.bot import handle
from app.database import transaction


class Message(BaseModel):
    group_id: str = Field(default="default", min_length=1, max_length=200)
    player_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    message_id: str | None = Field(default=None, min_length=1, max_length=200)


def create_app(database_path=None):
    api = FastAPI(title="Futebol Bot")
    api.state.database_path = database_path or os.getenv(
        "DATABASE_PATH", "data/futebol.db"
    )

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.post("/messages")
    def receive_message(message: Message, x_api_key: str = Header(default="")):
        key = os.getenv("BOT_API_KEY", "")
        if key and not secrets.compare_digest(key.encode(), x_api_key.encode()):
            raise HTTPException(status_code=401, detail="Chave inválida")
        admins = {p.strip() for p in os.getenv("ADMIN_IDS", "").split(",") if p.strip()}
                with transaction(api.state.database_path) as db:
            if message.message_id is not None:
                processed = db.execute(
                    """
                    SELECT player_id, text, reply
                    FROM processed_messages
                    WHERE group_id = ? AND message_id = ?
                    """,
                    (message.group_id, message.message_id),
                ).fetchone()

                if processed is not None:
                    if (
                        processed["player_id"] != message.player_id
                        or processed["text"] != message.text
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "ID de mensagem já utilizado "
                                "com outro remetente ou conteúdo"
                            ),
                        )

                    return {"reply": processed["reply"]}

            reply = handle(
                db,
                message,
                message.player_id in admins,
            )

            if message.message_id is not None:
                db.execute(
                    """
                    INSERT INTO processed_messages (
                        group_id,
                        message_id,
                        player_id,
                        text,
                        reply
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        message.group_id,
                        message.message_id,
                        message.player_id,
                        message.text,
                        reply,
                    ),
                )

        return {"reply": reply}

    return api


app = create_app()
