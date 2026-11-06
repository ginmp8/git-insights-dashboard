# Projetos e repositórios

## Organização

Um projeto agrega vários repositórios Git, por exemplo backend, frontend e infraestrutura. O cadastro local é persistido em um catálogo JSON; o histórico é lido diretamente do Git, sem alterar o diretório de trabalho dos projetos.

## Formas de adicionar

**Pasta local:** selecione o caminho para um repositório já existente no computador.

**GitHub CLI:** instale gh e autentique uma vez com gh auth login. Na barra lateral, abra **Adicionar repositório → GitHub CLI · escolher da lista**, clique em **Listar repositórios que posso acessar**, filtre por proprietário/visibilidade e selecione os desejados. O comando consulta os repositórios que a conta autenticada pode acessar por propriedade, colaboração ou participação em organizações, até o limite da API/configuração. É possível adicionar **até 25 por lote**.

**URL manual:** existe como alternativa avançada para repositórios em github.com.

A listagem usa gh api com paginação; **não clona nada**. Somente **Adicionar selecionados ao dashboard** inicia clones Git bare na pasta de espelhos local. O fluxo não pede confirmação repetida por repositório porque o clique de adicionar é a autorização da operação.

## Atualizar e remover

- **Recalcular dados locais** limpa o cache de leitura; não consulta a rede.
- **Fazer fetch dos espelhos** busca novas referências remotas sob comando explícito.
- **Remover somente do catálogo** desvincula a entrada; não exclui a cópia do disco.

## Limites e cuidados

A descoberta GitHub é limitada a 5.000 repositórios por padrão na integração, e o seletor limita clones a 25 por ação. Repositórios grandes ou privados podem consumir disco; avalie antes de selecionar muitos.

Os clones do GitHub CLI utilizam o mecanismo local de credenciais do gh; a aplicação não precisa receber tokens digitados pelo usuário. Consulte [Privacidade](../privacy-and-security.md) e [Integração GitHub](github-integration.md).

**Código de referência:** [catálogo](../../gitinsights/catalog.py), [clones/fetch](../../gitinsights/remote.py) e [seletor](../../gitinsights/ui_repository_picker.py).
