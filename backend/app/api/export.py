"""«Дані для ШІ»: Markdown export for budget planning in an ordinary AI chat."""
from datetime import datetime

import aiohttp
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.banking import family_bank_balances
from app.config import settings
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db
from app.services import ai_export

router = APIRouter(tags=["export"])


async def _send_document(chat_id: int, filename: str, text: str, caption: str) -> bool:
    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    form.add_field("caption", caption)
    form.add_field("document", text.encode(), filename=filename, content_type="text/markdown")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument", data=form) as r:
                return r.status == 200
    except Exception:
        return False


@router.post("/families/{family_id}/export/ai")
async def export_ai(family_id: int, send: bool = True, _: None = Depends(require_family),
                    actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    """Build the file; send it to the user's chat with the bot (Mini App can't save files on iOS). Text is returned too."""
    try:
        bank = await family_bank_balances(family_id, None, db)
    except Exception:
        bank = []
    text = ai_export.build(db, family_id, bank)
    filename = f"bimi-budget-{datetime.now():%Y-%m-%d}.md"
    tg_id = actor.user.tg_id if actor.user else None
    sent = bool(send and tg_id) and await _send_document(
        tg_id, filename, text, "🤖 Дані для ШІ: перешли цей файл у чат з Claude і попроси спланувати бюджет.")
    return {"sent": sent, "filename": filename, "text": text}
