def configure_launcher(data):
    if data.get("game","").upper()!="010056B015FE8000": raise ValueError("Wrong launcher title")
    rows=data.get("settings")
    if not isinstance(rows,list): raise ValueError("Invalid launcher")
    # Native Shared Shell mapping supports all individual buttons; do not add
    # a competing DM_PAD_MAP env row that can override the user's saved map.
    rows=[r for r in rows if r.get("env") not in ("DM_FPS","DM_FPS_TARGET","DM_PAD_MAP","DM_NIER_TRANSLATION")]
    rows.extend([
      {"env":"DM_FPS_TARGET","kind":"choice","section":"Game","label":"Taxa de quadros","note":"O perfil NieR 1.0.3 suporta alvo 30/60 FPS; desempenho no iPhone depende da cena.","default":"30","options":[["30","30 FPS"],["60","60 FPS"]],"level":"basic"},
      {"env":"DM_NIER_TRANSLATION","kind":"choice","section":"Game","label":"Tradução PT-BR","note":"Tradução integrada ao RomFS; créditos M.I.L. Traduções / TriboGame. Não é um seletor de idioma.","default":"pt-BR","options":[["pt-BR","Português do Brasil (integrada)"]],"level":"basic"}
    ])
    data["settings"]=rows
    return data
