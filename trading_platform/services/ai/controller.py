"""
AI Controller: consume snapshot stream from Redis, build context, call LLM router, send response.
Designed to be run as background task; receives get_redis and send_ai_response callback from app.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.streams import STREAM_AI_SNAPSHOTS, REDIS_KEY_AI_SNAPSHOT_BLOB


async def run_controller(get_redis, get_or_build_context, route_multimodal, send_ai_response):
    """Loop: xread STREAM_AI_SNAPSHOTS -> get blob + context + few-shot -> route_multimodal -> send_ai_response."""
    r = await get_redis()
    last_id = "$"
    while True:
        try:
            result = await r.xread({STREAM_AI_SNAPSHOTS: last_id}, count=1, block=5000)
            if not result:
                continue
            for _stream, messages in result:
                for msg_id, fields in messages:
                    last_id = msg_id
                    payload_str = (fields or {}).get("payload")
                    if not payload_str:
                        continue
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    exchange = payload.get("exchange", "")
                    symbol = payload.get("symbol", "")
                    ts = payload.get("ts", 0)
                    blob_key = payload.get("blobKey") or REDIS_KEY_AI_SNAPSHOT_BLOB.format(
                        exchange=exchange, symbol=symbol, ts=ts
                    )
                    image_base64 = await r.get(blob_key)
                    context = await get_or_build_context(r, exchange, symbol)
                    graph_parts = []
                    try:
                        from services.graph.graphrag import (
                            query_similar_situations,
                            query_by_price_level,
                            query_chain_events_to_price,
                        )
                        graph_parts.append(query_similar_situations(exchange, symbol, limit=10))
                        graph_parts.append(query_chain_events_to_price(exchange, symbol, limit=5))
                        try:
                            from shared.streams import REDIS_KEY_TRADES
                            trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
                            last_trade_raw = await r.lrange(trades_key, -1, -1)
                            if last_trade_raw:
                                lt = json.loads(last_trade_raw[0])
                                price = float(lt.get("price", 0))
                                if price > 0:
                                    graph_parts.append(query_by_price_level(exchange, symbol, price, limit=5))
                        except Exception:
                            pass
                        graph_ctx = "\n\n".join(p for p in graph_parts if p)
                    except Exception:
                        graph_ctx = ""
                    try:
                        from services.ai.experience_replay import search_few_shot
                        few_shot = await search_few_shot(exchange, symbol, limit=3)
                        if few_shot:
                            prefix = "Previous successful cases:\n" + "\n".join(
                                s["summary_text"] for s in few_shot
                            ) + "\n\n---\nCurrent context:\n"
                            context = prefix + context
                    except Exception:
                        pass
                    text = ""
                    try:
                        from services.ai.router import (
                            route_cognitive_analyst,
                            route_multimodal,
                            has_doubt_or_revision,
                        )
                        text = await route_cognitive_analyst(
                            context,
                            graph_context=graph_ctx or None,
                        )
                        if text and has_doubt_or_revision(text):
                            follow_up = await route_cognitive_analyst(
                                f"Проверь гипотезу. Твой предыдущий вывод:\n{text[:1500]}\n\nПерепроверь на спуфинг и аномалии, затем дай итоговую рекомендацию.",
                                graph_context=graph_ctx or None,
                            )
                            if follow_up:
                                text = follow_up
                    except Exception:
                        pass
                    if not text:
                        cached_name = None
                        try:
                            from services.ai.context_caching import get_or_refresh_cache_name
                            cached_name = await get_or_refresh_cache_name(r, exchange=exchange, symbol=symbol)
                        except Exception:
                            pass
                        try:
                            text = await route_multimodal(context, image_base64, cached_content_name=cached_name)
                        except Exception as e:
                            err_msg = str(e)
                            if "openrouter_not_configured" in err_msg:
                                text = "[AI error] openrouter_not_configured"
                            else:
                                text = f"[AI error] {e!s}"
                    await send_ai_response(exchange, symbol, text)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ai_controller] {e}")
            await asyncio.sleep(2)
