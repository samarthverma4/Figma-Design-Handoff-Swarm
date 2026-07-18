"""Real Slack delivery via chat.postMessage.

post_summary formats the swarm's extracted specs into Slack blocks and posts to
the configured channel, returning the real message ts + permalink as proof.
Token is never logged.
"""
from __future__ import annotations

from typing import Any

from .errors import AuthError, FigmaAPIError
from .http_client import HttpClient

SLACK_API = "https://slack.com/api"


class SlackClient:
    def __init__(self, bot_token: str, http: HttpClient):
        self._token = bot_token
        self._http = http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json; charset=utf-8"}

    async def post_summary(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """payload: {text, blocks?}. Returns {message_id, channel, permalink, ok}."""
        body = {
            "channel": channel_id,
            "text": payload.get("text", "Design handoff summary"),
        }
        if payload.get("blocks"):
            body["blocks"] = payload["blocks"]

        data = await self._http.request_json(
            "POST", f"{SLACK_API}/chat.postMessage",
            tool="post_summary", headers=self._headers(), json_body=body,
        )
        # Slack returns HTTP 200 even on logical failure — inspect ok.
        if not data.get("ok"):
            err = data.get("error", "unknown_error")
            if err in ("invalid_auth", "not_authed", "token_revoked", "account_inactive"):
                raise AuthError(f"Slack auth failed: {err}", tool="post_summary", status=200)
            raise FigmaAPIError(f"Slack post failed: {err}", tool="post_summary", status=200)

        ts = data.get("ts")
        channel = data.get("channel")
        permalink = await self._permalink(channel, ts)
        return {"ok": True, "message_id": ts, "channel": channel, "permalink": permalink}

    async def _permalink(self, channel: str | None, ts: str | None) -> str | None:
        if not channel or not ts:
            return None
        try:
            data = await self._http.request_json(
                "GET", f"{SLACK_API}/chat.getPermalink",
                tool="post_summary", headers=self._headers(),
                params={"channel": channel, "message_ts": ts},
            )
            return data.get("permalink") if data.get("ok") else None
        except Exception:  # noqa: BLE001 — permalink is best-effort proof, not critical
            return None


def build_slack_payload(summary: dict[str, Any]) -> dict[str, Any]:
    """Format a developer-readable Slack message from the swarm summary.

    summary keys: file_name, current_version, changed_frames[list of names],
    specs[list], asset (dict|None), skipped_frames[list of names].
    """
    file_name = summary.get("file_name", "Figma file")
    version = summary.get("current_version", "?")
    changed = summary.get("changed_frames", [])
    skipped = summary.get("skipped_frames", [])
    specs = summary.get("specs", [])
    asset = summary.get("asset")

    header = f"*Design handoff · {file_name}* (v{version})"
    changed_line = (
        f":large_purple_circle: *{len(changed)} changed frame(s):* " + ", ".join(changed)
        if changed else ":white_check_mark: No changed frames."
    )

    spec_lines = []
    for s in specs[:10]:
        name = s.get("name", "frame")
        colors = ", ".join(c.get("hex", "") for c in (s.get("colors") or [])[:3])
        typ = ", ".join(
            f"{t.get('family')} {t.get('weight')}/{t.get('size')}"
            for t in (s.get("typography") or [])[:2]
        )
        spacing = s.get("spacing", {})
        gap = spacing.get("item_spacing")
        spec_lines.append(f"• *{name}* — colors: {colors or '—'} · type: {typ or '—'} · gap: {gap if gap is not None else '—'}")

    asset_line = ""
    if asset:
        dims = asset.get("dimensions", "")
        asset_line = f":framed_picture: Asset: `{asset.get('filename')}` {dims} — {asset.get('url', '')}"

    skipped_line = f"_Skipped (unchanged): {', '.join(skipped)}_" if skipped else ""

    text_parts = [header, changed_line, *spec_lines, asset_line, skipped_line, "→ *Ready for implementation*"]
    text = "\n".join(p for p in text_parts if p)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": changed_line}},
    ]
    if spec_lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(spec_lines)}})
    if asset_line:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": asset_line}})
    if skipped_line:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": skipped_line}]})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "→ *Ready for implementation*"}})

    return {"text": text, "blocks": blocks}
