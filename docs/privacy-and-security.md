# Privacidade, rede e armazenamento

O processamento de commits, autores, arquivos e branches é local. O dashboard não contém telemetria própria nem envia o código para análise externa. A instalação de bibliotecas e as integrações Git remotas têm suas próprias conexões de rede.

## Operações de rede

| Operação | Rede |
|---|---|
| Consultar repositórios Git já disponíveis localmente | Não |
| Recalcular métricas, inspecionar diffs, exportar JSON/CSV | Não |
| Listar repositórios disponíveis pela conta gh | Sim, ao clicar |
| Clonar repositórios selecionados ou informar URL Git remota | Sim, ao clicar |
| Atualizar espelhos Git com fetch | Sim, ao clicar |
| Consultar Pull Requests via gh | Sim, ao clicar |
| Instalar dependências via pip | Sim, conforme o índice configurado |

Não há sincronização automática dos espelhos por simples rerenderização da tela. O aplicativo usa gh como helper de credenciais temporário quando necessário para os clones selecionados; não grava tokens nas URLs nem altera a configuração Git global.

## Onde os dados ficam

Por padrão, o catálogo JSON, os espelhos Git e os dados de demonstração ficam em .git-insights-data/, dentro do diretório da aplicação. É possível alterar esse local com GIT_INSIGHTS_HOME. Remover um item do catálogo não apaga o repositório correspondente do disco.

Repositórios privados importados permanecem como **cópias locais potencialmente sensíveis**. Proteja o diretório com permissões do sistema operacional e não compartilhe backups ou exports inadvertidamente.

## Exposição do servidor

O Streamlit é configurado para escutar em 127.0.0.1:8501 e desabilita o envio de estatísticas de uso do Streamlit. O dashboard **não tem autenticação de usuários**: não publique sua interface em uma rede aberta, nem a execute em uma máquina compartilhada sem isolamento apropriado.

A integração foi desenvolvida para github.com; domínios personalizados de GitHub Enterprise não fazem parte desta versão. Consulte a implementação em [gitinsights/remote.py](../gitinsights/remote.py), [gitinsights/github.py](../gitinsights/github.py) e [gitinsights/catalog.py](../gitinsights/catalog.py).
