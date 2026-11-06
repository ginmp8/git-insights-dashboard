# GitHub CLI: seleção de repositórios e Pull Requests

A aplicação usa o executável **gh** já instalado e autenticado no computador. Não há tela própria para inserir um token de acesso.

## Autenticação e descoberta

~~~sh
gh auth login
gh auth status
~~~

Na barra lateral, escolha **GitHub CLI · escolher da lista** e depois **Listar repositórios que posso acessar**. A consulta usa gh api /user/repos paginado, incluindo os vínculos de proprietário, colaborador e membro de organização permitidos pela conta. A lista mostra metadados; não clona o repositório.

Selecione os repositórios e clique em **Adicionar selecionados ao dashboard** para criar espelhos bare locais. São permitidos até **25 por ação**. A integração de descoberta suporta github.com, não hosts personalizados de GitHub Enterprise.

Os clones selecionados usam temporariamente gh auth git-credential como helper Git, sem gravar tokens em URLs ou alterar a configuração Git global. A aplicação não lê os tokens para armazená-los no catálogo.

## Pull Requests

A aba **Pull requests** possui o botão **Consultar PRs no GitHub (rede)**. Somente após o clique, o aplicativo consulta gh pr list para os repositórios elegíveis, exibindo estado, datas, autor, origem/destino e contagens informadas pela API.

Não há consulta de PRs em cada atualização visual do Streamlit. Os dados dependem da conectividade, das permissões e da autenticação do gh; problemas de SSO e API podem impedir a leitura mesmo quando o Git local está acessível.

## Operação offline

A análise Git funciona sem gh. A instalação inicial via pip, clones selecionados, refresh remoto e consultas GitHub são operações separadas. Para atualizar espelhos, use explicitamente **Fazer fetch dos espelhos**.

**Código de referência:** [gitinsights/github.py](../../gitinsights/github.py), [gitinsights/ui_repository_picker.py](../../gitinsights/ui_repository_picker.py) e [gitinsights/remote.py](../../gitinsights/remote.py).
