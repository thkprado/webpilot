# WebPilot

[English](README.md) · **Português**

> A versão em inglês ([README.md](README.md)) é a referência e a que os agentes devem ler. Esta tradução existe para
> facilitar a leitura por pessoas; em caso de diferença, vale o inglês.

Permite que agentes de código (Claude Code, Codex, Gemini CLI/Antigravity, pi, Cursor ou qualquer coisa com um shell) controlem um navegador:

- **real**: o seu próprio navegador baseado em Chromium (Chrome, Edge, Brave, Vivaldi, Opera, ...), com as suas sessões e logins, por meio da extensão WebPilot.
- **temp**: um Chromium temporário com um perfil descartável (`--temp`).

As abas dos agentes no navegador real ficam num grupo de abas roxo chamado **WebPilot**. **Agentes: este arquivo é tudo o que vocês precisam. Leiam-no inteiro antes de usar o navegador.**

---

## 1. Instalação (uma vez, pelo usuário)

### Peça para a sua IA instalar

Você usa um assistente de código com IA (Claude Code, Codex, Gemini CLI/Antigravity, Cursor, ...)? Cole isto nele:

```text
Set up WebPilot on this machine for me: https://github.com/thkprado/webpilot - follow docs/AI_SETUP.md in that repository.
```

Ele verifica as suas ferramentas (Git, Python, uv, Node.js, um navegador baseado em Chromium), clona e compila a extensão, configura o daemon e
confere se está funcionando. A única coisa que ele não consegue fazer é clicar no seu navegador: ele passa o passo a passo
exato para carregar a extensão (o passo "Carregar sem compactação" abaixo). No fim, ele oferece apresentar o WebPilot aos seus agentes,
como skill (Claude Code, Codex, Antigravity, pi, Copilot CLI) ou como nota nas instruções deles, e pergunta antes de gravar qualquer um dos dois. Os passos que ele segue estão em [docs/AI_SETUP.md](docs/AI_SETUP.md) (em inglês).

### Ou faça você mesmo

`<webpilot>` representa a pasta onde você clonou este repositório, por exemplo `C:\src\webpilot` ou `~/src/webpilot`.

```powershell
cd <webpilot>                                           # a pasta onde você clonou este repositório
cd extension; npm install; npm run build; cd ..       # compila a extensão em extension/dist
uv sync
uv run webpilot setup                                   # cria o token e extension/dist/config.json
uv tool install --editable .                            # opcional: `webpilot` disponível em qualquer pasta
```

Abra a página de extensões do navegador (`chrome://extensions`; Edge: `edge://extensions`, Opera: `opera://extensions`), ative o **Modo do desenvolvedor**, clique em **Carregar sem compactação** e escolha `extension/dist`. O ícone da extensão mostra um selo:

| Selo | Significado |
|---|---|
| `ON` | conectado ao daemon |
| `OFF` | daemon não está rodando (ele inicia no primeiro comando `webpilot`) |
| `CFG` | rode `webpilot setup` de novo |
| `DUP` | outro perfil conectado já usa este nome de perfil; renomeie um deles (abaixo) |

Clique no ícone para abrir um popup com o estado da conexão e o nome deste perfil.

**Vários perfis ou navegadores.** Carregue `extension/dist` do mesmo jeito em cada perfil (ou navegador); todos compartilham um único daemon. Cada perfil recebe um nome aleatório (`profile-1a2b`). Para renomeá-lo, clique no ícone da extensão naquele perfil e edite o nome no popup, ou use `webpilot profile list` (mostra a aba ativa de cada um) e `webpilot profile rename profile-1a2b work`. Com um só perfil conectado nada muda. Com vários, os comandos precisam de `--profile NOME` (ou `-p`), `WEBPILOT_PROFILE=NOME`, ou `"profile": "NOME"` em `~/.webpilot/config.json` como padrão; caso contrário falham e listam os nomes conectados.

O daemon (`webpilot serve`) inicia automaticamente em segundo plano. Ele escuta apenas em `127.0.0.1`, exige o token de `~/.webpilot/config.json` e rejeita conexões vindas de páginas web.

Sem `uv tool install`, use `uv run --project <webpilot> webpilot ...`.

**Atualizando.** Rode `update.bat` (Windows) ou `./update.sh` em `<webpilot>`: ele para o daemon, baixa o código mais novo (`git pull --ff-only`), recompila a extensão, roda `uv sync` e reinstala o comando `webpilot` se você o instalou com `uv tool install`. Depois clique em recarregar no card do WebPilot na página de extensões do navegador. `--no-pull` pula o pull, para recompilar depois de mudar o código você mesmo.

### Tornando o WebPilot conhecido por outros agentes

Os agentes só usam o WebPilot se as instruções deles o mencionarem. Rode `uv tool install --editable .` primeiro (para que `webpilot` funcione em qualquer pasta; confira com `webpilot status`) e depois cole este trecho no arquivo de instruções de cada ferramenta, trocando `<webpilot>` pelo caminho absoluto da sua pasta do WebPilot. Ele só aponta para cá, então este README continua sendo a única fonte de verdade:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Chromium-based browser (Chrome, Edge, Brave, ...; logged-in sessions) or a temporary one (`--temp`).
Before first use in a session, read <webpilot>/README.md fully (sections 2+).
Real browser = the user's real accounts: never buy, send, delete, or change settings without asking.
```

| Ferramenta | Global (todos os projetos) | Por projeto |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md` |
| Codex CLI | `~/.codex/AGENTS.md` | `AGENTS.md` |
| Gemini CLI / Antigravity | `~/.gemini/GEMINI.md` | `GEMINI.md` ou `AGENTS.md` |
| pi | `~/.pi/agent/AGENTS.md` | `AGENTS.md` |
| Cursor | Settings → Rules → User Rules | `AGENTS.md` ou `.cursor/rules/webpilot.mdc` |
| Qualquer outra com shell | o system prompt / arquivo de regras dela | `AGENTS.md` |

As ferramentas que suportam Agent Skills podem receber uma skill `webpilot` no lugar, com o mesmo texto: ela só é carregada quando a tarefa precisa do navegador, em vez de entrar em toda sessão. O `webpilot skill` instala para você:

```bash
webpilot skill list                      # ferramentas, se estão nesta máquina, estado da skill
webpilot skill install claude pi         # as que você nomear; sem nome: pergunta uma a uma; --all: todas as encontradas
webpilot skill install --project agy     # a pasta de skills deste projeto em vez da global
webpilot skill uninstall copilot         # ou --all; só remove uma skill que ele mesmo gravou (--force para outras)
```

| Ferramenta (nome) | Skill global | Por projeto |
|---|---|---|
| Claude Code (`claude`) | `~/.claude/skills/webpilot/` | `.claude/skills/webpilot/` |
| Codex CLI (`codex`) | `~/.codex/skills/webpilot/` | `.codex/skills/webpilot/` |
| Antigravity IDE e agy CLI (`antigravity` ou `agy`) | `~/.gemini/config/skills/webpilot/` | `.agents/skills/webpilot/` |
| pi (`pi`) | `~/.pi/agent/skills/webpilot/` | `.pi/skills/webpilot/` |
| GitHub Copilot CLI (`copilot`) | `~/.copilot/skills/webpilot/` | `.github/skills/webpilot/` |

A skill aponta para o `README.md` deste clone. Rode `webpilot skill install` de novo depois de mover o clone; `webpilot skill list` mostra `outdated` quando uma skill instalada difere da atual. O Copilot CLI também lê `~/.claude/skills/`, então numa máquina com os dois basta um deles.

Sem `uv tool install`, troque `webpilot` no trecho por `uv run --project <webpilot> webpilot`.

## 2. Referência rápida para agentes

```bash
webpilot goto https://site.com -s        # navega + imprime o snapshot (-s)
webpilot snapshot                        # texto da página com refs: [e12 button "Send"]
webpilot snapshot -i                     # só elementos interativos (curto)
webpilot snapshot -S "main"              # só uma subárvore CSS
webpilot click e12                       # clica por ref | seletor CSS | text=Rótulo | text=Next|Próximo|›
webpilot click e12 -s                    # ...depois imprime um snapshot da página resultante
webpilot click e12 --wait-text "Step 2"  # ...depois espera o próximo estado (--wait-for SELETOR também funciona)
webpilot submit [e7] -s                  # envia o formulário em volta de e7 (ou o focado/primeiro)
webpilot type e7 "hello" --submit        # preenche e pressiona Enter
webpilot type "select#country" "Brazil"  # escolhe uma opção de <select> pelo texto
webpilot select e16 "billing"            # escolhe em um dropdown customizado (role=combobox, react-select) ou <select>
webpilot press Escape                    # teclas: Enter Tab Escape ArrowDown PageDown a Control+a ...
webpilot scroll down | up | top | bottom | e40
webpilot wait --text "Order confirmed" --timeout 20
webpilot wait --text "Loading" --gone    # espera até desaparecer
webpilot extract [URL]                   # JSON do parser do site, ou snapshot + dica se não houver parser
webpilot search "query" -n 5             # Google (padrão) | -e ddg ; imprime JSON com título/url/trecho
webpilot text -S article                 # innerText puro
webpilot html -S "#content" -o page.html # HTML bruto (grande! prefira snapshot/extract)
webpilot eval "document.title"           # JS na página; retorna JSON
webpilot eval "fetch('/api/x').then(r=>r.json())" --timeout 300   # promises são aguardadas (padrão 60 s)
webpilot eval "(t) => (document.querySelector('#body').value = t).length" --arg @notes.md   # dados como argumentos
webpilot fetch /api/items [-H "K: V"] [--timeout 120] [-o arquivo] [--raw]   # HTTP com a sessão da aba; saída JSON
webpilot screenshot [-o arquivo.png] [--full]   # imprime o caminho; abra a imagem para ver
webpilot tabs | tab new [URL] | tab use ID | tab close [ID] | tab info
webpilot back | forward | reload
webpilot captcha                         # clica em uma caixa "Não sou um robô" (sempre sob pedido)
webpilot --temp <comando>                # usa o navegador temporário (inicia automaticamente)
webpilot --tab ID <comando>              # age em uma aba específica uma vez
webpilot -p NOME <comando>               # usa este perfil do navegador (só necessário quando vários estão conectados)
webpilot profile list                    # perfis conectados e a aba ativa de cada um
webpilot status                          # estado do daemon / da extensão
```

Resultados estruturados são impressos como JSON. Snapshots são impressos como texto. Erros vão para o stderr com código de saída 1.

### Fluxo recomendado

1. Chegue à página com `goto URL -s`, ou com `search "..."` seguido de `goto`.
2. Se você só precisa de dados, use `extract`. Quando existe um parser, ele retorna um JSON compacto. Os parsers também casam com iframes: quando a própria página não tem nenhum, o primeiro iframe que tiver um é analisado (`"frame"` e `"page_url"` no resultado). Em fluxos repetidos (quizzes, assistentes), um parser pode retornar os alvos onde agir (`#answer_2`, `text=Next`), de modo que cada passo é `extract` + `click <alvo> --wait-text <próximo>` sem snapshot.
3. Se você precisa interagir, rode `snapshot -i` para ver as refs e depois `click`/`type` com elas. As refs (`e12`) valem até a página navegar; depois de uma navegação, tire um novo snapshot. Se a página renderiza um elemento de novo (AJAX), a ref é encontrada outra vez pelo tipo e pelo rótulo (`"reresolved": true` no resultado).
   **Iframes** (quizzes embutidos, formulários, widgets, até de outros domínios) aparecem inline entre `[iframe ...]` e `[/iframe]`, e as refs deles carregam o frame: `f11e3`. Use-as como qualquer ref. Seletores CSS e alvos `text=` (que também casam com `aria-label`), `html -S`/`text -S` e `wait --text`/`--wait-text` olham dentro dos iframes quando a página principal não tem correspondência. `eval` roda apenas na página principal.
4. As ações (`click`, `type`, `select`, `press`, `submit`) esperam até `--timeout` (5 s) o alvo aparecer e ficar habilitado. Depois esperam a página se acalmar: carregamento da página, nenhum XHR/fetch em andamento e nenhuma mudança no DOM por 0,5 s. `"changed": false` significa que a página não reagiu; `"busy": "dom"` (ou `"network"`) significa que a página nunca ficou quieta e a espera desistiu. Em fluxos passo a passo (quizzes, assistentes), use `click ... -s` ou `submit -s` para agir e ler o próximo passo em um único comando. Acrescente `--wait-text`/`--wait-for` quando o próximo passo tem um marcador conhecido; o comando sai com código 1 se o marcador nunca aparecer. Com um marcador, páginas que nunca ficam quietas (um relógio rodando) custam 1,5 s por ação em vez de 5 s; para um checkbox, o próprio estado `:checked` serve de marcador (`--wait-for "#opt:checked"`).
5. **Dropdowns customizados** (`role=combobox`, como o react-select): o snapshot os mostra como `[e16 combobox "How can we help?" value="I have an account or billing issue" expanded=false]`, com o valor que o campo exibe. Em uma lista aberta, as opções são marcadas ` selected` (o valor atual) e ` active` (aquela em que as setas estão). `select <ref> <texto>` escolhe em um comando. Ele digita o texto para filtrar quando o campo permite busca, vai até a opção com as setas e pressiona Enter, tudo com eventos sintéticos, e depois confere o que o campo mostra (`"option"` e `"value"` no resultado). Sai com código 1 quando nenhuma opção casa (o erro lista as opções) ou quando o campo não mostra a opção depois. Clicar no input e depois em uma opção, ou pressionar teclas em vários comandos, falha se o menu fechar no meio (ele fecha quando a janela do navegador perde o foco). Quando você faz `click` em uma opção de um combobox, o resultado diz se o campo agora a mostra: `"selected": true`, ou `"selected": false` com o `"value"` do campo e uma `"hint"` com o comando `select` a rodar no lugar.
6. Para páginas longas, restrinja a leitura com `snapshot -S <seletor>` ou `--max N` em vez de ler tudo.
7. Verificações visuais: `screenshot` e depois abra o PNG.
8. **Dados no `eval`: passe-os como argumentos, nunca cole no código.** Texto colado dentro de uma string JS quebra com aspas, crases e quebras de linha, e uma barra de escape perdida no caminho (um `\\n` que chega como quebra de linha de verdade) é um erro de sintaxe. Em vez disso, faça da expressão uma função e passe os valores: `eval "(t) => ..." --arg TEXTO` (repetível; `--arg @ARQUIVO` lê um arquivo, `@-` lê o stdin, `@@x` é o literal `@x`), `--args-json '[...]'` para outros valores JSON, ou `eval(fn, args=[...])` em Python. Os valores viajam como JSON, separados do código. Erros de sintaxe informam a linha, a coluna e um trecho com um cursor, com as quebras de linha mostradas como `⏎`:
   ```text
   error: SyntaxError: Invalid or unexpected token at line 2, column 24:
     …#release_body');⏎  return t.value.split('⏎')[0]; })()
                                              ^
   ```

### Regras para agentes

- **Navegador real = as contas reais do usuário.** Não compre nada, não envie mensagens, não apague dados, não mude configurações nem aceite termos sem confirmação explícita do usuário.
- Só opere as outras abas do usuário (`tab use`) quando for pedido. Novas abas vão para o grupo WebPilot.
- **Perfis do navegador são contas separadas**, possivelmente de pessoas diferentes. Se um comando falhar com "several browser profiles are connected", pergunte ao usuário qual perfil usar (`webpilot profile list` mostra os nomes); nunca escolha por conta própria. Depois de informado, passe `-p NOME` em todos os comandos (ou `Browser(profile=NOME)`) e não troque de perfil sem que peçam.
- Captcha: o `goto` não mexe em captchas, a menos que o usuário tenha ativado `"auto_captcha": true` em `~/.webpilot/config.json` (desativado por padrão); nesse caso ele clica automaticamente em caixas "I'm not a robot" (resultado no campo `captcha`). `webpilot captcha` clica em uma sob pedido. Se aparecer `challenge: true`, **pare e peça ao usuário** que resolva no navegador e depois continue. Nunca tente resolver desafios de imagem.
- Logins: no navegador real as sessões do usuário já existem. Se for preciso fazer login, peça ao usuário que entre; não digite senhas, a menos que o usuário as forneça para esse fim.
- `fetch` chama a API de um site com a sessão do usuário, a partir da página da aba atual (URLs relativas são resolvidas em relação a ela; outra origem só funciona se permitir CORS). Ele imprime `status`, `headers` e `body` (já interpretado quando é JSON) e sai com código 1 em erros HTTP. Métodos diferentes de GET/HEAD são recusados, a menos que você passe `--allow-write`, o que só pode ser feito depois que o usuário confirmar aquela requisição.
- Prefira `click`/`type` sem `--trusted`. Use `--trusted` (mouse/teclado reais pela API de depuração) só quando a página ignora o clique sintético. Ele mostra a barra "depurando este navegador" por cerca de 20 s. A entrada real se perde quando a janela do navegador está minimizada ou coberta por outras janelas, então `click --trusted`, `type --trusted`/`--submit` e `press` falham primeiro com um erro dizendo isso (a aba do agente pode estar em segundo plano de uma janela visível).

### API Python

Para laços e scripts, a API é mais rápida que muitas chamadas de CLI porque mantém uma conexão aberta:

```python
from webpilot import Browser

with Browser() as b:                    # Browser("temp") para o navegador temporário; Browser(profile="work")
    b.goto("https://news.ycombinator.com")
    data = b.extract()                  # {"parser": ..., "data": ...} ou {"snapshot": ...}
    snap = b.snapshot(interactive=True)["text"]
    b.click("text=More")
    results = b.search("python uv", n=5)["results"]
```

Métodos: `goto, back, forward, reload, snapshot, html, text, click, type, select, press, submit, scroll, wait, eval, fetch, screenshot, captcha, extract, search, tabs, new_tab, use_tab, close_tab, info, status`. `click`/`type`/`select`/`press`/`submit` aceitam `timeout=`, `wait_text=`, `wait_selector=` e `wait_timeout=`. `eval(expression, timeout=60, args=None)` aguarda promises por até `timeout` segundos; com `args` (uma lista de valores JSON), `expression` precisa ser uma função e é chamada com eles, e só o número e o tamanho deles vão para o log da sessão. `fetch(url, method="GET", headers=None, data=None, json=None, timeout=120, allow_write=False, raw=False)` retorna `{"status", "statusText", "url", "headers", "body"}`; `body` é JSON interpretado (a menos que `raw`), texto, ou bytes para conteúdo binário.

Rode scripts com `uv run --project <webpilot> python script.py`.

### APIs de sites com a sessão do navegador

Quando um site em que o usuário está logado tem uma API JSON (dashboards, painéis de administração), chame-a com `fetch` em vez de ler páginas: abra o site uma vez e depois use URLs relativas. Exemplo com o Grafana consultando o Loki pelo proxy de datasource dele:

```python
from urllib.parse import urlencode
from webpilot import Browser

with Browser() as b:
    b.goto("https://grafana.example.com/")
    ds = b.fetch("/api/datasources")["body"]          # [{"uid", "type", "name", ...}]
    loki = next(d["uid"] for d in ds if d["type"] == "loki")
    q = urlencode({"query": '{app="api"} |~ "conex.o recusada"', "limit": 5000,
                   "start": "2026-10-05T00:00:00Z", "end": "2026-10-05T06:00:00Z"})
    res = b.fetch(f"/api/datasources/proxy/uid/{loki}/loki/api/v1/query_range?{q}", timeout=300)
    streams = res["body"]["data"]["result"]
```

Pela CLI: `webpilot fetch /api/datasources`. Limites do Loki que vale conhecer:

- `limit` acima de `max_entries_limit_per_query` (normalmente 5000) é rejeitado: divida intervalos longos em janelas menores.
- Uma consulta retorna no máximo 500 séries: restrinja o seletor de labels ou agregue.
- Linhas de log escritas em JSON trazem os acentos escapados (`ç`), então uma regex com `ç`/`ã` nunca casa: use `.` no lugar (`conex.o`).

## 3. Parsers de sites (faça isso para sites que você visita com frequência)

Um parser transforma o HTML de um site em um JSON compacto, para que você não precise ler a página inteira de novo. O `extract` usa um automaticamente sempre que a URL casa.

**Quando escrever um:** o mesmo site é lido duas ou mais vezes, ou o `reflect-data` sugere.

**Onde:** `parsers_user/<nome>.py`. Ele é encontrado automaticamente e tem precedência sobre os parsers embutidos. Os parsers embutidos ficam em `src/webpilot/parsers/` (google, duckduckgo), com os fixtures em `tests/fixtures/`.

`parsers_user/` é local de cada usuário e não é versionado (está no `.gitignore`): os fixtures são páginas salvas, e as notas e os scripts refletem a sua própria navegação. Para começar um, copie o exemplo: `cp -r examples/parsers_user parsers_user` (um parser do Hacker News com o fixture, o `NOTES.md` e o `scripts/hn_top.py`).

**Modelo:**

```python
"""Product page on loja.example.com."""
from selectolax.lexbor import LexborHTMLParser

NAME = "loja_example"
MATCH = [r"^https://(www\.)?loja\.example\.com/p/"]   # regexes contra a URL

def parse(html: str, url: str) -> dict:
    tree = LexborHTMLParser(html)
    def txt(sel):
        n = tree.css_first(sel)
        return n.text(separator=" ", strip=True) if n else None
    return {
        "title": txt("h1"),
        "price": txt("[data-testid=price]"),
        "items": [li.text(strip=True) for li in tree.css("ul.specs li")],
    }
```

**Passos:**

1. Na página alvo, veja a estrutura: `webpilot snapshot`, ou `webpilot html -S <container> -o tmp.html` e leia o arquivo.
2. Salve um fixture com `webpilot parser fixture <NOME>`. Isso grava `parsers_user/fixtures/<NOME>/*.html` com a URL na primeira linha. Para conteúdo dentro de um iframe, acrescente `--frame <texto na URL dele>`; depois que o parser existe, o iframe que o `MATCH` dele seleciona é salvo automaticamente.
3. Escreva o parser. Prefira seletores estáveis: `id`, `data-*`, `aria-*` e tags semânticas. Evite nomes de classe CSS aleatórios.
4. Teste com `webpilot parser test <NOME> --show` (`uv run pytest` também testa todos os fixtures).
5. Use com `webpilot extract`.

Regras: parsers são puros. Recebem HTML e retornam um dict ou uma lista, sem acesso à rede e sem navegador. Retorne `{}` ou `[]` quando não encontrar nada; o `reflect-data` sinaliza isso como uma possível mudança de layout. `webpilot parser list` mostra os parsers, seus padrões, fixtures e erros de carregamento.

Escreva notas sobre os sites (fluxos, particularidades, onde clicar) em `parsers_user/NOTES.md`.

## 4. Reflexão (fim da sessão)

Toda ação é registrada em `~/.webpilot/sessions/<data>.jsonl`. O texto digitado não é registrado, só o tamanho dele.

```bash
webpilot reflect-data              # sessão de hoje; --days 7, --session NOME, --json
```

Ele relata domínios lidos sem parser, fluxos interativos repetidos (snapshots tirados só para achar refs antes de clicar; o conteúdo de iframes conta para o domínio do iframe), falhas de parser, resultados vazios de parser, saídas grandes, erros repetidos e comandos lentos, cada um com uma sugestão. O procedimento completo está em `docs/reflect.md`. No Claude Code, use `/reflect` neste projeto.

## 5. Referência

| Item | Local |
|---|---|
| Config/token | `~/.webpilot/config.json` (`port`, `auto_captcha` (padrão `false`), `blocked_domains`, `profile`); rode `webpilot setup` de novo depois de editar |
| Log do daemon | `~/.webpilot/daemon.log` |
| Screenshots | `~/.webpilot/screenshots/` |
| Navegador temporário | Chromium do Playwright; perfil em `%TEMP%\webpilot-temp-*`, apagado por `webpilot temp stop` (ou `webpilot stop`, que também para o daemon); `webpilot temp start --headless` para modo headless. Ele inicia com a detecção de oclusão do Chromium desligada, então uma janela coberta por outras ainda recebe entrada real; uma minimizada não |

- `blocked_domains` (por exemplo `["mybank.example.com"]`) impede que o agente navegue para esses domínios e seus subdomínios, ou opere neles, no navegador real. Maiúsculas, um `*.` no início e um ponto no final não fazem diferença.
- Variáveis de ambiente: `WEBPILOT_MODE=temp`, `WEBPILOT_SESSION=nome`, `WEBPILOT_PROFILE=nome`, `WEBPILOT_HEADLESS=1`, `WEBPILOT_PORT`, `WEBPILOT_DIR`, `WEBPILOT_PARSERS_DIR`.

### Solução de problemas

| Erro | O que fazer |
|---|---|
| "extension (real browser) is not connected" | O navegador precisa estar aberto com a extensão carregada; confira o selo e o `webpilot status`. Depois de ficar ocioso, a primeira conexão pode levar até 30 s. |
| "several browser profiles are connected" | Pergunte ao usuário qual perfil usar e depois acrescente `-p NOME`. O usuário pode definir um padrão com `"profile"` em `~/.webpilot/config.json`. |
| "browser profile 'X' is not connected" | A janela do navegador daquele perfil está fechada ou a extensão dele está desligada; o erro lista os nomes conectados. |
| "could not run script in this tab" | Página restrita (`chrome://`, `edge://`, a loja de extensões, PDF). Navegue para uma página normal. |
| `fetch`: "open the site first" | `fetch` roda a partir da página da aba atual: faça `goto` no site e repita. |
| `fetch`: "C:/Program Files/Git/... is a Windows path" | O Git Bash reescreveu a URL relativa. Coloque `MSYS_NO_PATHCONV=1` antes do comando, ou passe a URL completa. |
| "ref eN not found" / "ref eN (...) is gone" | A página navegou ou o elemento sumiu; rode `snapshot` de novo. |
| Ação retornou `"changed": false` | O clique não fez nada: tente `--trusted`, `submit` ou outro elemento. |
| Opção de dropdown clicada (`"changed": true`, `"selected": false`) ou escolhida com teclas, mas nada foi escolhido | Use `select <ref do combobox> <texto>` (a `hint` no resultado traz o comando): um comando só, então o menu não pode fechar no meio. "not a combobox": mire o input com `role=combobox` (ou um elemento em volta dele). "no list of options opened": o campo não é um dropdown no estilo listbox; tente `click` e depois `snapshot -i`. |
| "ref eN (option ...) is gone" depois de abrir um dropdown | O menu fechou entre os comandos (ele fecha quando a janela do navegador perde o foco). Use `select <ref do combobox> <texto>`. |
| "the browser window is minimized or covered, so real input would be lost" | Vindo de `--trusted`, `type --submit` ou `press`. Peça ao usuário que traga a janela do navegador para a frente, ou use `click`/`type` sem `--trusted`, `submit` em vez de `--submit`, ou `select`. |
| O snapshot depois de uma ação ainda mostra "Loading..." | Acrescente `--wait-text`/`--wait-for` com algo do próximo estado, ou `wait --text "Loading" --gone`. |
| O Google mostrou "unusual traffic" | Peça ao usuário que resolva o captcha, ou use `search -e ddg`. |
| Console da extensão: "WebSocket connection to 'ws://127.0.0.1:8765/' failed: ... ERR_CONNECTION_REFUSED" | Normal enquanto o daemon não está rodando: a extensão tenta de novo a cada poucos segundos, para conectar assim que o daemon iniciar. Para silenciar, desligue a extensão na página de extensões do navegador e ligue de novo antes de usar o WebPilot. |
| Você mudou o código da extensão | Rode `npm run build` em `extension/` e depois clique em recarregar no card dela na página de extensões do navegador. |

## 6. Arquitetura

```
agent ──shell──> webpilot CLI / lib Python ──WebSocket──> daemon (127.0.0.1:8765)
                                                             │  só token + origem da extensão
                                    ┌────────────────────────┴──────────────────┐
                           extensão no seu navegador (real)         extensão no Chromium (temp)
                           chrome.scripting / chrome.debugger       mesmo código, mode=temp
```

- `extension/src/background.ts`: ponte WebSocket, abas, navegação, entrada confiável (CDP via `chrome.debugger`), captcha.
- `extension/src/page.ts`: injetado na página; snapshot com refs, click/type/select, detecção de captcha.
- `extension/src/popup.ts` + `popup.html`: popup da barra de ferramentas com o estado da conexão e o nome do perfil.
- `src/webpilot/`: `server.py` (daemon), `client.py` (API), `cli.py`, `registry.py` (parsers), `search.py`, `session_log.py`, `reflect.py`, `temp_browser.py`.

## 7. Segurança e uso responsável

O WebPilot dá a um programa (e à IA por trás dele) o controle de um navegador, então trate-o como um acesso remoto à sua máquina:

- No modo **real**, o agente age com as suas sessões logadas: e-mail, banco, ferramentas de trabalho. Use `blocked_domains` para os sites que ele nunca deve tocar, e prefira `--temp` (perfil descartável) quando você não precisar das suas contas.
- A extensão pede permissões amplas (`<all_urls>`, `debugger`, `scripting`, `webRequest`, `tabs`). Carregue-a só a partir de uma compilação feita por você mesmo a partir deste código-fonte, em um perfil de navegador que você controla.
- O daemon local escuta apenas em `127.0.0.1` e exige o token de `~/.webpilot/config.json`. Mantenha esse arquivo privado; quem puder lê-lo consegue controlar o seu navegador.
- Os logs de sessão em `~/.webpilot/sessions/` registram URLs e comandos (o texto digitado só é registrado pelo tamanho). Os fixtures de parser salvos podem conter conteúdo de páginas; nunca faça commit de páginas de um navegador logado.
- Você é responsável por respeitar os termos de serviço dos sites que automatiza. O WebPilot não resolve captchas de imagem, e o clique automático na caixa é opcional (opt-in).
- O software é fornecido "como está", sem garantia (veja `LICENSE`). Revise o que um agente vai fazer antes de permitir compras, mensagens, exclusões ou mudanças de configuração.

Relate vulnerabilidades como descrito em `SECURITY.md`.

## Licença

[MIT](LICENSE)
