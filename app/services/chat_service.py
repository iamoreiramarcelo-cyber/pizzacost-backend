import logging
import json
import base64
from openai import OpenAI
from app.config import get_settings
from app.utils.cost_calculator import calculate_pizza_cost, calculate_profit_margin
from app.utils.unit_conversion import calculate_ingredient_cost

logger = logging.getLogger("pizzacost.chat")


def _get_client():
    settings = get_settings()
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _build_system_prompt(db, user_id: str) -> str:
    """Build system prompt with user's real data."""
    # Fetch all user data
    insumos = db.table("insumos").select("*").eq("user_id", user_id).execute().data or []
    tamanhos = db.table("tamanhos").select("*").eq("user_id", user_id).execute().data or []
    bordas = db.table("bordas").select("*").eq("user_id", user_id).execute().data or []
    pizzas = db.table("pizzas").select("*").eq("user_id", user_id).execute().data or []
    combos = db.table("combos").select("*").eq("user_id", user_id).execute().data or []

    insumos_text = "\n".join([
        f"- {i['nome']}: R${i['preco']:.2f} por {i['quantidade_comprada']}{i['unidade']} (custo unitario: R${i['custo_unitario']:.4f}/{i['unidade']})"
        + (f" | Estoque: {i.get('quantidade_estoque', 0)}{i['unidade']}" if i.get('quantidade_estoque') else "")
        for i in insumos
    ]) or "Nenhum insumo cadastrado."

    tamanhos_text = "\n".join([
        f"- {t['nome']}: embalagem R${t['custo_embalagem']:.2f}, massa R${t['custo_massa']:.2f}"
        for t in tamanhos
    ]) or "Nenhum tamanho cadastrado."

    # Calculate pizza costs
    insumos_map = {i['id']: i for i in insumos}
    pizzas_text_parts = []
    for p in pizzas:
        tamanho = next((t for t in tamanhos if t['id'] == p.get('tamanho_id')), None)
        borda = next((b for b in bordas if b['id'] == p.get('border_id')), None) if p.get('border_id') else None

        cost = calculate_pizza_cost(
            pizza_ingredientes=p.get('ingredientes', []),
            custo_adicionais=p.get('custo_adicionais', 0),
            tamanho=tamanho or {},
            borda=borda,
            insumos_map=insumos_map
        )
        margin = calculate_profit_margin(cost, p.get('preco_venda', 0))
        margin_text = f", margem {margin:.1f}%" if margin is not None else ""

        pizzas_text_parts.append(
            f"- {p['nome']}: custo R${cost:.2f}, venda R${p.get('preco_venda', 0):.2f}{margin_text}"
        )

    pizzas_text = "\n".join(pizzas_text_parts) or "Nenhum sabor cadastrado."

    return f"""Voce e o assistente de custos do PizzaCost Pro, um sistema para pizzarias brasileiras.
Voce ajuda o dono da pizzaria a entender custos, margens e tomar decisoes de precificacao.

DADOS ATUAIS DA PIZZARIA:

INSUMOS CADASTRADOS:
{insumos_text}

TAMANHOS:
{tamanhos_text}

SABORES (com custos calculados):
{pizzas_text}

REGRAS:
- Sempre responda em portugues brasileiro, de forma direta e pratica
- Use os dados reais acima para calculos — nunca invente precos
- Quando o usuario perguntar custos, calcule com base nos insumos cadastrados
- Para simular cenarios ("e se X subir 20%?"), recalcule os custos afetados
- Se o usuario pedir para criar um sabor, calcule o custo estimado com os insumos disponiveis
- Para notas fiscais/cupons, extraia os itens e compare com os insumos cadastrados
- Formate valores monetarios como R$ X,XX
- Seja conciso — respostas curtas e uteis, sem enrolacao
"""


def chat(db, user_id: str, message: str, image_base64: str = None) -> str:
    """Process a chat message, optionally with an image (receipt)."""
    client = _get_client()
    system_prompt = _build_system_prompt(db, user_id)

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    # Get recent chat history (last 10 messages)
    history = db.table("chat_messages").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute().data or []
    for msg in reversed(history):
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Build user message
    if image_base64:
        # Vision request for receipt scanning
        user_content = [
            {"type": "text", "text": message or "Analise esta nota fiscal e extraia os itens com nome, quantidade, unidade e preco. Retorne em formato JSON: {\"items\": [{\"name\": \"...\", \"quantity\": ..., \"unit\": \"...\", \"price\": ...}]}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": message})

    # Call OpenAI
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500,
            temperature=0.3,
        )
        assistant_message = response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        assistant_message = "Desculpe, houve um erro ao processar sua mensagem. Tente novamente."

    # Save messages to history
    try:
        db.table("chat_messages").insert({"user_id": user_id, "role": "user", "content": message or "[imagem]"}).execute()
        db.table("chat_messages").insert({"user_id": user_id, "role": "assistant", "content": assistant_message}).execute()
    except Exception as e:
        logger.warning(f"Failed to save chat history: {e}")

    return assistant_message


def process_receipt(db, user_id: str, image_base64: str) -> dict:
    """Process a receipt image: extract items, match with insumos, update prices."""
    client = _get_client()

    # Extract items from receipt
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Voce e um extrator de dados de notas fiscais brasileiras. Extraia TODOS os itens visiveis."},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extraia todos os itens desta nota fiscal/cupom. Para cada item retorne: nome do produto, quantidade, unidade (kg, g, L, ml, un, pct, cx), preco total em reais. Retorne APENAS JSON valido: {\"items\": [{\"name\": \"...\", \"quantity\": ..., \"unit\": \"...\", \"price\": ...}]}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]}
            ],
            max_tokens=2000,
            temperature=0,
        )
        raw = response.choices[0].message.content
        # Extract JSON from response
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        extracted = json.loads(raw.strip())
    except Exception as e:
        logger.error(f"Receipt extraction failed: {e}")
        return {"error": "Nao consegui ler a nota fiscal. Tente uma foto mais nitida.", "items": []}

    items = extracted.get("items", [])
    if not items:
        return {"error": "Nenhum item encontrado na nota.", "items": []}

    # Match with existing insumos
    insumos = db.table("insumos").select("*").eq("user_id", user_id).execute().data or []

    matched = []
    unmatched = []

    for item in items:
        item_name = (item.get("name") or "").lower().strip()
        best_match = None
        best_score = 0

        for insumo in insumos:
            insumo_name = insumo["nome"].lower().strip()
            # Simple fuzzy match: check if one contains the other
            if item_name in insumo_name or insumo_name in item_name:
                score = len(insumo_name) / max(len(item_name), 1)
                if score > best_score:
                    best_score = score
                    best_match = insumo
            # Also check first word match
            elif item_name.split()[0] == insumo_name.split()[0] if item_name and insumo_name else False:
                score = 0.5
                if score > best_score:
                    best_score = score
                    best_match = insumo

        if best_match and best_score > 0.3:
            matched.append({
                "receipt_item": item,
                "insumo": best_match,
                "confidence": best_score
            })
        else:
            unmatched.append(item)

    # Auto-update matched insumos
    updated = []
    for m in matched:
        insumo = m["insumo"]
        receipt = m["receipt_item"]
        new_price = receipt.get("price", insumo["preco"])
        new_qty = receipt.get("quantity", insumo["quantidade_comprada"])

        if new_price and new_qty and new_qty > 0:
            new_custo = new_price / new_qty
            try:
                db.table("insumos").update({
                    "preco": new_price,
                    "quantidade_comprada": new_qty,
                    "custo_unitario": new_custo,
                }).eq("id", insumo["id"]).execute()

                # Update stock if feature active
                if insumo.get("quantidade_estoque") is not None:
                    new_stock = (insumo.get("quantidade_estoque") or 0) + new_qty
                    db.table("insumos").update({
                        "quantidade_estoque": new_stock,
                        "ultima_atualizacao_estoque": "now()"
                    }).eq("id", insumo["id"]).execute()

                    db.table("stock_movements").insert({
                        "user_id": user_id,
                        "insumo_id": insumo["id"],
                        "tipo": "compra_nota",
                        "quantidade": new_qty,
                        "observacao": f"Nota fiscal: {receipt.get('name', '')}"
                    }).execute()

                updated.append({
                    "nome": insumo["nome"],
                    "preco_antigo": insumo["preco"],
                    "preco_novo": new_price,
                    "quantidade": new_qty
                })
            except Exception as e:
                logger.warning(f"Failed to update insumo {insumo['id']}: {e}")

    return {
        "updated": updated,
        "unmatched": unmatched,
        "total_extracted": len(items),
        "total_matched": len(matched),
        "total_unmatched": len(unmatched)
    }


def analyze_menu(db, user_id: str) -> dict:
    """Analyze all flavors for margin optimization."""
    insumos = db.table("insumos").select("*").eq("user_id", user_id).execute().data or []
    tamanhos = db.table("tamanhos").select("*").eq("user_id", user_id).execute().data or []
    bordas = db.table("bordas").select("*").eq("user_id", user_id).execute().data or []
    pizzas = db.table("pizzas").select("*").eq("user_id", user_id).execute().data or []

    if not pizzas:
        return {"error": "Nenhum sabor cadastrado para analisar."}

    insumos_map = {i['id']: i for i in insumos}

    analysis = []
    for p in pizzas:
        tamanho = next((t for t in tamanhos if t['id'] == p.get('tamanho_id')), None)
        borda = next((b for b in bordas if b['id'] == p.get('border_id')), None) if p.get('border_id') else None

        cost = calculate_pizza_cost(p.get('ingredientes', []), p.get('custo_adicionais', 0), tamanho or {}, borda, insumos_map)
        selling = p.get('preco_venda', 0)
        margin = calculate_profit_margin(cost, selling)

        category = "prejuizo" if (margin is not None and margin < 0) else \
                   "margem_baixa" if (margin is not None and margin < 25) else \
                   "margem_boa" if (margin is not None and margin < 60) else "margem_alta"

        analysis.append({
            "id": p["id"],
            "nome": p["nome"],
            "custo": round(cost, 2),
            "preco_venda": selling,
            "margem": round(margin, 1) if margin is not None else None,
            "categoria": category,
            "sugestao_preco": round(cost / 0.65, 2) if cost > 0 else 0  # Target 35% margin
        })

    negative = [a for a in analysis if a["categoria"] == "prejuizo"]
    low = [a for a in analysis if a["categoria"] == "margem_baixa"]
    avg_margin = sum(a["margem"] for a in analysis if a["margem"] is not None) / len(analysis) if analysis else 0

    # Generate AI summary
    try:
        client = _get_client()
        summary_prompt = f"""Analise estes dados de cardapio de uma pizzaria e gere um resumo executivo curto (3-4 frases):

Total sabores: {len(analysis)}
Com prejuizo: {len(negative)} ({', '.join(a['nome'] for a in negative) or 'nenhum'})
Margem baixa (<25%): {len(low)} ({', '.join(a['nome'] for a in low) or 'nenhum'})
Margem media: {avg_margin:.1f}%

Sabores com pior margem: {json.dumps([{'nome': a['nome'], 'margem': a['margem'], 'custo': a['custo'], 'venda': a['preco_venda']} for a in sorted(analysis, key=lambda x: x['margem'] or 999)[:3]], ensure_ascii=False)}

Diga o que esta bom, o que precisa melhorar, e uma acao concreta. Seja direto e pratico."""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=300,
            temperature=0.3
        )
        ai_summary = resp.choices[0].message.content
    except Exception as e:
        logger.warning(f"AI summary failed: {e}")
        ai_summary = None

    result = {
        "total_flavors": len(analysis),
        "negative_margin_count": len(negative),
        "low_margin_count": len(low),
        "average_margin": round(avg_margin, 1),
        "flavors": analysis,
        "ai_summary": ai_summary
    }

    # Save snapshot
    try:
        db.table("menu_analysis").insert({
            "user_id": user_id,
            "total_flavors": len(analysis),
            "negative_margin_count": len(negative),
            "low_margin_count": len(low),
            "average_margin": round(avg_margin, 1),
            "insights": {"flavors": analysis},
            "ai_summary": ai_summary
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to save menu analysis: {e}")

    return result


def generate_shopping_list(db, user_id: str, planned: list) -> dict:
    """Generate shopping list from planned production.
    planned: [{"flavor_id": "...", "quantity": 50}, ...]
    """
    insumos = db.table("insumos").select("*").eq("user_id", user_id).execute().data or []
    tamanhos = db.table("tamanhos").select("*").eq("user_id", user_id).execute().data or []
    bordas = db.table("bordas").select("*").eq("user_id", user_id).execute().data or []
    pizzas = db.table("pizzas").select("*").eq("user_id", user_id).execute().data or []

    insumos_map = {i['id']: i for i in insumos}
    pizzas_map = {p['id']: p for p in pizzas}

    # Aggregate ingredients needed
    needs = {}  # insumo_id -> total quantity needed (in base unit)
    packaging_needs = {}  # tamanho_id -> count

    for plan in planned:
        pizza = pizzas_map.get(plan.get("flavor_id"))
        if not pizza:
            continue
        qty = plan.get("quantity", 0)

        # Ingredients
        for ing in pizza.get("ingredientes", []):
            insumo_id = ing.get("insumoId") or ing.get("insumo_id")
            ing_qty = ing.get("quantidade", 0)
            if insumo_id:
                needs[insumo_id] = needs.get(insumo_id, 0) + (ing_qty * qty)

        # Border ingredients
        if pizza.get("border_id"):
            borda = next((b for b in bordas if b['id'] == pizza['border_id']), None)
            if borda:
                for ing in borda.get("ingredientes", []):
                    insumo_id = ing.get("insumoId") or ing.get("insumo_id")
                    ing_qty = ing.get("quantidade", 0)
                    if insumo_id:
                        needs[insumo_id] = needs.get(insumo_id, 0) + (ing_qty * qty)

        # Packaging
        tamanho_id = pizza.get("tamanho_id")
        if tamanho_id:
            packaging_needs[tamanho_id] = packaging_needs.get(tamanho_id, 0) + qty

    # Build shopping list
    items = []
    total_cost = 0

    for insumo_id, needed_qty in needs.items():
        insumo = insumos_map.get(insumo_id)
        if not insumo:
            continue

        stock = insumo.get("quantidade_estoque", 0) or 0
        to_buy = max(0, needed_qty - stock)
        cost = to_buy * insumo.get("custo_unitario", 0)
        total_cost += cost

        items.append({
            "insumo_id": insumo_id,
            "nome": insumo["nome"],
            "unidade": insumo["unidade"],
            "necessario": round(needed_qty, 2),
            "em_estoque": round(stock, 2),
            "comprar": round(to_buy, 2),
            "custo_estimado": round(cost, 2)
        })

    # Add packaging
    for tam_id, count in packaging_needs.items():
        tam = next((t for t in tamanhos if t['id'] == tam_id), None)
        if tam:
            items.append({
                "nome": f"Embalagem {tam['nome']}",
                "unidade": "un",
                "necessario": count,
                "em_estoque": 0,
                "comprar": count,
                "custo_estimado": round(count * tam.get("custo_embalagem", 0), 2)
            })
            total_cost += count * tam.get("custo_embalagem", 0)

    return {
        "items": sorted(items, key=lambda x: x["custo_estimado"], reverse=True),
        "total_estimated_cost": round(total_cost, 2),
        "planned_production": planned
    }


def get_stock_overview(db, user_id: str) -> dict:
    """Get stock overview with alerts and capacity."""
    insumos = db.table("insumos").select("*").eq("user_id", user_id).execute().data or []
    pizzas = db.table("pizzas").select("*").eq("user_id", user_id).execute().data or []

    alerts = []
    overview = []

    for i in insumos:
        stock = i.get("quantidade_estoque", 0) or 0
        minimum = i.get("estoque_minimo", 0) or 0

        status = "ok"
        if minimum > 0 and stock <= minimum:
            status = "critico"
            alerts.append({"insumo": i["nome"], "estoque": stock, "minimo": minimum, "unidade": i["unidade"]})
        elif minimum > 0 and stock <= minimum * 1.5:
            status = "baixo"

        overview.append({
            "id": i["id"],
            "nome": i["nome"],
            "unidade": i["unidade"],
            "estoque": round(stock, 2),
            "minimo": round(minimum, 2),
            "status": status
        })

    # Calculate capacity (how many of each pizza can be made)
    capacity = []
    for p in pizzas:
        min_pizzas = float('inf')
        limiting = None
        for ing in p.get("ingredientes", []):
            insumo_id = ing.get("insumoId") or ing.get("insumo_id")
            ing_qty = ing.get("quantidade", 0)
            insumo = next((i for i in insumos if i["id"] == insumo_id), None)
            if insumo and ing_qty > 0:
                stock = insumo.get("quantidade_estoque", 0) or 0
                possible = stock / ing_qty
                if possible < min_pizzas:
                    min_pizzas = possible
                    limiting = insumo["nome"]

        if min_pizzas != float('inf'):
            capacity.append({
                "sabor": p["nome"],
                "pode_fazer": int(min_pizzas),
                "limitado_por": limiting
            })

    return {
        "overview": overview,
        "alerts": alerts,
        "capacity": sorted(capacity, key=lambda x: x["pode_fazer"])
    }
