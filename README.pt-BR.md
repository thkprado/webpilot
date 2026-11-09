# WebPilot

[English](README.md) · **Português**

> A versão em inglês ([README.md](README.md)) é a referência. Esta tradução existe para facilitar a leitura por
> pessoas; em caso de diferença, vale o inglês.

Permite que agentes de código (Claude Code, Codex, Gemini CLI/Antigravity, pi, Cursor ou qualquer coisa com um shell) controlem um navegador:

- **real**: o seu próprio navegador baseado em Chromium (Chrome, Edge, Brave, Vivaldi, Opera, ...), com as suas sessões e logins, por meio da extensão WebPilot.
- **temp**: um Chromium temporário com um perfil descartável (`--temp`).

As abas dos agentes no navegador real ficam num grupo de abas roxo chamado **WebPilot**. **Agentes: leiam [docs/agent.md](docs/agent.md) inteiro antes de usar o navegador; este README é para pessoas.**

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

Os agentes só usam o WebPilot se as instruções deles o mencionarem. Rode `uv tool install --editable .` primeiro (para que `webpilot` funcione em qualquer pasta; confira com `webpilot status`) e depois cole este trecho no arquivo de instruções de cada ferramenta, trocando `<webpilot>` pelo caminho absoluto da sua pasta do WebPilot. Ele só aponta para o guia dos agentes, então [docs/agent.md](docs/agent.md) continua sendo a única fonte de verdade:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Chromium-based browser (Chrome, Edge, Brave, ...; logged-in sessions) or a temporary one (`--temp`).
Before first use in a session, read <webpilot>/docs/agent.md fully.
On a site you may have used before, first check its site notes and `webpilot script` (see the guide).
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

A skill aponta para o `docs/agent.md` deste clone. Rode `webpilot skill install` de novo depois de mover o clone; `webpilot skill list` mostra `outdated` quando uma skill instalada difere da atual. O Copilot CLI também lê `~/.claude/skills/`, então numa máquina com os dois basta um deles.

Sem `uv tool install`, troque `webpilot` no trecho por `uv run --project <webpilot> webpilot`.

## 2. Como os agentes usam

Os agentes rodam comandos `webpilot` no shell deles (ou num script Python) e leem os resultados:

```bash
webpilot goto https://news.ycombinator.com -s     # abre uma página e mostra um snapshot com refs: [e12 link "More"]
webpilot click e12 -s                             # age numa ref e lê a página seguinte
webpilot select e16 "billing"                     # escolhe num dropdown
webpilot extract                                  # o JSON compacto de um parser do site, quando houver
webpilot --temp search "python uv" -n 5           # o mesmo, num navegador descartável
```

O que os agentes leem fica em `docs/`, em inglês:

| Arquivo | Quando ler |
|---|---|
| [docs/agent.md](docs/agent.md) | em toda sessão, antes do primeiro uso: comandos, fluxo, regras |
| [docs/python-api.md](docs/python-api.md) | antes de escrever um script (`webpilot.Browser`) ou chamar a API de um site com a sessão |
| [docs/parsers.md](docs/parsers.md) | antes de escrever um parser de site, notas do site ou um script |
| [docs/troubleshooting.md](docs/troubleshooting.md) | quando um erro não diz o que fazer |
| [docs/reflect.md](docs/reflect.md) | no fim de uma sessão |

As regras do guia impedem os agentes de agir nas suas contas sem perguntar: nada de compras, mensagens, exclusões,
mudanças de configuração ou escritas HTTP sem a sua confirmação; as suas outras abas só quando pedido; com vários
perfis de navegador, eles perguntam qual usar; param diante de desafios de captcha e pedem que você faça login em
vez de digitar senhas.

## 3. Parsers, notas e scripts de sites

Os agentes ficam mais rápidos nos sites que usam com frequência escrevendo, em geral durante a reflexão de fim de
sessão:

- **parsers** (`parsers_user/<nome>.py`): transformam o HTML de um site em JSON compacto, usado pelo `extract`;
- **notas do site** (`parsers_user/NOTES.md`): fluxos e particularidades, uma seção `##` por domínio;
- **scripts** (`parsers_user/scripts/<nome>.py`): fluxos repetidos com `webpilot script <nome>`.

`parsers_user/` é local de cada usuário e não é versionado (está no `.gitignore`): fixtures são páginas salvas, e
notas e scripts refletem a sua própria navegação. Para começar pelo exemplo (um parser do Hacker News com o fixture
dele, notas e `scripts/hn_top.py`): `cp -r examples/parsers_user parsers_user`. `WEBPILOT_PARSERS_DIR` acrescenta
outra pasta, procurada primeiro. Detalhes: [docs/parsers.md](docs/parsers.md) (em inglês).

## 4. Reflexão (fim da sessão)

Toda ação é registrada em `~/.webpilot/sessions/<data>.jsonl`. O texto digitado não é registrado, só o tamanho dele.

```bash
webpilot reflect-data              # sessão de hoje; --days 7, --session NOME, --json
```

Ele relata domínios lidos sem parser, fluxos interativos repetidos (snapshots tirados só para achar refs antes de clicar; o conteúdo de iframes conta para o domínio do iframe), falhas de parser, resultados vazios de parser, saídas grandes, erros repetidos e comandos lentos, cada um com uma sugestão. O procedimento completo está em `docs/reflect.md`. Neste projeto, use `/reflect` no Claude Code, ou a skill `reflect` no Antigravity (`.agents/skills/`) e no Copilot CLI (`.github/skills/`).

## 5. Referência

| Item | Local |
|---|---|
| Config/token | `~/.webpilot/config.json` (`port`, `auto_captcha` (padrão `false`), `blocked_domains`, `profile`); rode `webpilot setup` de novo depois de editar |
| Log do daemon | `~/.webpilot/daemon.log` |
| Screenshots | `~/.webpilot/screenshots/` |
| Navegador temporário | Chromium do Playwright; perfil em `%TEMP%\webpilot-temp-*`, apagado por `webpilot temp stop` (ou `webpilot stop`, que também para o daemon); `webpilot temp start --headless` para modo headless. Ele inicia com a detecção de oclusão do Chromium desligada, então uma janela coberta por outras ainda recebe entrada real; uma minimizada não |

- `auto_captcha: true` faz o `goto` clicar sozinho nas caixas "I'm not a robot" (resultado no campo `captcha`); desligado por padrão. Desafios de imagem nunca são resolvidos: o agente pede a você.
- `blocked_domains` (por exemplo `["mybank.example.com"]`) impede que o agente navegue para esses domínios e seus subdomínios, ou opere neles, no navegador real. Maiúsculas, um `*.` no início e um ponto no final não fazem diferença.
- Variáveis de ambiente: `WEBPILOT_MODE=temp`, `WEBPILOT_SESSION=nome`, `WEBPILOT_PROFILE=nome`, `WEBPILOT_HEADLESS=1`, `WEBPILOT_PORT`, `WEBPILOT_DIR`, `WEBPILOT_PARSERS_DIR`.

### Solução de problemas

Os erros dizem o que fazer em seguida; [docs/troubleshooting.md](docs/troubleshooting.md) (em inglês) cobre o resto (o selo da extensão está explicado na Instalação, acima). Para pessoas:

| Sintoma | O que fazer |
|---|---|
| Console da extensão: "WebSocket connection to 'ws://127.0.0.1:8765/' failed: ... ERR_CONNECTION_REFUSED" | Normal enquanto o daemon não está rodando: a extensão tenta de novo a cada poucos segundos, para conectar assim que o daemon iniciar. Para silenciar, desligue a extensão na página de extensões do navegador e ligue de novo antes de usar o WebPilot. |
| Depois de o navegador ficar ocioso, o primeiro comando demora | A extensão reconecta primeiro; isso pode levar até 30 s. |
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
